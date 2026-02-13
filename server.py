# server.py
# Backend API that connects scraper + neighborhood fetcher + scorer

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re
import json
import time
import math

app = Flask(__name__)
CORS(app)


# ============================================
# USER SETTINGS
# ============================================
USER_SETTINGS = {
    "budget_cap": 2500,
    "ideal_bedrooms": 2,
    "ideal_bathrooms": 2,
    "ideal_sqft": 1000,
    "market_avg_rent": 1750,
    "necessities": ["covered_parking", "dishwasher", "in_unit_laundry", "ac"],
    "nice_to_haves": ["pool", "sauna_hot_tub", "gym", "package_lockers"],
    "commute_target": {"lat": 44.9258, "lon": -93.4083, "name": "Hopkins, MN"}
}

AMENITY_KEYWORDS = {
    "covered_parking": ["covered parking", "garage parking", "indoor parking", "heated parking", "parking garage", "underground parking"],
    "dishwasher": ["dishwasher"],
    "in_unit_laundry": ["in-unit laundry", "in unit laundry", "washer/dryer", "washer and dryer",
                         "in-home laundry", "w/d in unit", "washer & dryer", "in unit washer",
                         "full-size washer", "in-unit washer"],
    "ac": ["air conditioning", "a/c", "central air", "climate control", "air-conditioning"],
    "pool": ["pool", "swimming"],
    "sauna_hot_tub": ["sauna", "hot tub", "spa", "steam room"],
    "gym": ["gym", "fitness center", "fitness room", "exercise room", "workout"],
    "package_lockers": ["package locker", "parcel locker", "package room", "mailroom", "package concierge"]
}


# ============================================
# SCRAPER - Extract data from apartment URLs
# ============================================

def scrape_apartment(url):
    """
    Scrapes apartment listing data from a URL.
    Supports apartments.com and generic apartment sites.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            return {"error": f"Could not access page (status {response.status_code})", "scraped": False}

        soup = BeautifulSoup(response.text, "html.parser")
        page_text = soup.get_text(separator=" ").lower()

        # Extract what we can
        data = {
            "scraped": True,
            "url": url,
            "name": extract_text(soup, [
                "h1.propertyName", "h1[data-testid='property-name']",
                ".community-name", "h1", "title"
            ]),
            "address": extract_text(soup, [
                ".propertyAddress", "[data-testid='property-address']",
                ".community-address", ".property-address"
            ]),
            "raw_amenities": extract_amenities_list(soup),
            "classified_amenities": [],
            "floor_plans_raw": extract_floor_plans_raw(soup),
            "tour_3d": extract_tour(soup),
            "all_prices": extract_prices(soup),
            "page_text_snippet": page_text[:3000]
        }

        # Classify amenities
        data["classified_amenities"] = classify_amenities(data["raw_amenities"], page_text)

        return data

    except Exception as e:
        return {"error": str(e), "scraped": False}


def extract_text(soup, selectors):
    """Try multiple CSS selectors, return first match."""
    for sel in selectors:
        el = soup.select_one(sel)
        if el and el.text.strip():
            text = el.text.strip()
            # Clean up excessive whitespace
            text = re.sub(r'\s+', ' ', text)
            if len(text) < 200:
                return text
    return None


def extract_amenities_list(soup):
    """Pull all amenity-like text from the page."""
    amenities = []
    selectors = [
        ".amenity", ".amenityCard", "[data-testid='amenity']",
        ".spec li", ".propertyFeatures li", ".amenity-group li",
        ".unique-amenity", ".community-amenity li",
        ".amenities li", ".amenity-list li"
    ]
    for sel in selectors:
        for el in soup.select(sel):
            text = el.get_text(separator=" ").strip()
            if text and len(text) < 150:
                amenities.append(text)

    return list(set(amenities))


def classify_amenities(raw_list, page_text=""):
    """Match raw amenity strings to our system categories."""
    classified = []
    combined_text = " ".join(raw_list).lower() + " " + page_text.lower()

    for key, keywords in AMENITY_KEYWORDS.items():
        if any(kw in combined_text for kw in keywords):
            classified.append(key)

    return list(set(classified))


def extract_floor_plans_raw(soup):
    """Extract floor plan text blocks."""
    plans = []
    selectors = [
        ".pricingGridItem", ".floor-plan-card",
        "[data-testid='floor-plan']", ".floorplan",
        ".pricing-grid-item", ".unit-type"
    ]
    for sel in selectors:
        for el in soup.select(sel):
            text = el.get_text(separator=" ").strip()
            if text and len(text) < 500:
                plans.append(text[:300])

    return plans[:20]


def extract_tour(soup):
    """Find 3D tour links."""
    tour_patterns = ["matterport", "tour.realync", "3dtour", "virtual-tour", "virtualtour", "my.tour"]

    for link in soup.find_all("a", href=True):
        if any(p in link["href"].lower() for p in tour_patterns):
            return link["href"]

    for iframe in soup.find_all("iframe", src=True):
        if any(p in iframe["src"].lower() for p in tour_patterns):
            return iframe["src"]

    return None


def extract_prices(soup):
    """Find all price-like values on the page."""
    text = soup.get_text()
    prices = re.findall(r'\$[\d,]+', text)
    # Filter to reasonable rent range
    valid = []
    for p in prices:
        val = int(p.replace("$", "").replace(",", ""))
        if 500 <= val <= 10000:
            valid.append(val)
    return sorted(set(valid))


# ============================================
# NEIGHBORHOOD DATA via OpenStreetMap
# ============================================

def geocode(address):
    """Convert address to coordinates using Nominatim."""
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1},
            headers={"User-Agent": "apartment-scorer-app"},
            timeout=10
        )
        results = resp.json()
        if results:
            return {
                "lat": float(results[0]["lat"]),
                "lon": float(results[0]["lon"]),
                "display": results[0].get("display_name", "")
            }
    except Exception as e:
        print(f"Geocoding error: {e}")
    return None


def haversine_miles(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in miles."""
    R = 3959  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def overpass_query(lat, lon, radius, tags):
    """Query OpenStreetMap Overpass API for nearby places."""
    tag_parts = []
    for key, values in tags.items():
        if isinstance(values, list):
            for v in values:
                tag_parts.append(f'node["{key}"="{v}"](around:{radius},{lat},{lon});')
        else:
            tag_parts.append(f'node["{key}"="{values}"](around:{radius},{lat},{lon});')

    query = f"""[out:json][timeout:25];({" ".join(tag_parts)});out body;"""

    try:
        resp = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            timeout=30
        )
        data = resp.json()
        places = []
        for el in data.get("elements", []):
            name = el.get("tags", {}).get("name", "Unnamed")
            dist = haversine_miles(lat, lon, el["lat"], el["lon"])
            places.append({
                "name": name,
                "distance_miles": round(dist, 2),
                "lat": el["lat"],
                "lon": el["lon"]
            })
        places.sort(key=lambda x: x["distance_miles"])
        return places
    except Exception as e:
        print(f"Overpass error: {e}")
        return []


def fetch_neighborhood(lat, lon):
    """Fetch all neighborhood data for scoring."""
    results = {}

    # Restaurants
    restaurants = overpass_query(lat, lon, 2500, {"amenity": "restaurant"})
    time.sleep(1)
    cafes = overpass_query(lat, lon, 2500, {"amenity": "cafe"})
    time.sleep(1)
    all_dining = restaurants + cafes
    results["restaurant_count"] = len(all_dining)
    results["restaurants_nearby"] = all_dining[:15]

    # Grocery
    grocery = overpass_query(lat, lon, 5000, {"shop": "supermarket"})
    time.sleep(1)
    wholesale = overpass_query(lat, lon, 16000, {"shop": "wholesale"})
    time.sleep(1)

    all_grocery = grocery.copy()
    existing = {g["name"].lower() for g in all_grocery}
    for s in wholesale:
        if s["name"].lower() not in existing:
            all_grocery.append(s)
    all_grocery.sort(key=lambda x: x["distance_miles"])

    results["grocery_stores"] = all_grocery[:15]
    results["has_costco"] = any("costco" in g["name"].lower() for g in all_grocery)
    results["costco_distance"] = next(
        (g["distance_miles"] for g in all_grocery if "costco" in g["name"].lower()), None
    )

    # Nightlife
    bars = overpass_query(lat, lon, 3000, {"amenity": "bar"})
    time.sleep(1)
    nightclubs = overpass_query(lat, lon, 3000, {"amenity": "nightclub"})
    time.sleep(1)
    cinemas = overpass_query(lat, lon, 3000, {"amenity": "cinema"})

    all_nightlife = bars + nightclubs + cinemas
    seen = set()
    unique_nightlife = []
    for p in all_nightlife:
        if p["name"].lower() not in seen:
            seen.add(p["name"].lower())
            unique_nightlife.append(p)
    unique_nightlife.sort(key=lambda x: x["distance_miles"])

    results["nightlife_count"] = len(unique_nightlife)
    results["nightlife_nearby"] = unique_nightlife[:15]

    time.sleep(1)

    # Transit
    bus = overpass_query(lat, lon, 1000, {"highway": "bus_stop"})
    time.sleep(1)
    rail = overpass_query(lat, lon, 2000, {"railway": "station"})
    all_transit = bus + rail
    results["transit_count"] = len(all_transit)

    if len(all_transit) >= 5:
        results["transit_level"] = "nearby"
    elif len(all_transit) >= 2:
        results["transit_level"] = "some"
    else:
        results["transit_level"] = "none"

    time.sleep(1)

    # Schools
    schools = overpass_query(lat, lon, 3000, {"amenity": "school"})
    results["schools_nearby"] = schools[:10]
    results["school_count"] = len(schools)

    # Commute estimate
    commute_miles = haversine_miles(
        lat, lon,
        USER_SETTINGS["commute_target"]["lat"],
        USER_SETTINGS["commute_target"]["lon"]
    )
    road_miles = commute_miles * 1.4
    results["commute_minutes"] = round((road_miles / 25) * 60)

    return results


# ============================================
# SCORING FUNCTIONS
# ============================================

def score_price(rent):
    cap = USER_SETTINGS["budget_cap"]
    avg = USER_SETTINGS["market_avg_rent"]

    budget = 50 if rent <= cap else max(0, 50 - ((rent - cap) / 100) * 10)
    market = 50 if rent <= avg else max(0, 50 - ((rent - avg) / 100) * 10)

    return round(budget + market)


def score_rooms(beds, baths, sqft):
    bed_score = max(0, 40 - abs(beds - USER_SETTINGS["ideal_bedrooms"]) * 20)
    bath_score = max(0, 40 - abs(baths - USER_SETTINGS["ideal_bathrooms"]) * 20)

    if sqft >= USER_SETTINGS["ideal_sqft"]:
        sqft_score = 20
    elif sqft >= USER_SETTINGS["ideal_sqft"] * 0.8:
        sqft_score = 10
    else:
        sqft_score = 0

    return round(bed_score + bath_score + sqft_score)


def score_necessities(amenities):
    for n in USER_SETTINGS["necessities"]:
        if n not in amenities:
            return 0
    return 100


def score_nice_to_haves(amenities):
    total = len(USER_SETTINGS["nice_to_haves"])
    if total == 0:
        return 100
    count = sum(1 for n in USER_SETTINGS["nice_to_haves"] if n in amenities)
    return round((count / total) * 100)


def score_restaurants(count):
    density = min(50, round((count / 20) * 50))
    quality = 35  # Default since OSM doesn't have ratings
    return min(100, density + quality)


def score_commute(drive_min, transit_level):
    if drive_min <= 10:
        drive = 70
    elif drive_min <= 20:
        drive = 55
    elif drive_min <= 30:
        drive = 40
    elif drive_min <= 45:
        drive = 25
    else:
        drive = 10

    transit_map = {"nearby": 30, "some": 15, "none": 0}
    transit = transit_map.get(transit_level, 0)

    return round(drive + transit)


def score_nightlife(count):
    density = min(50, round((count / 10) * 50))
    quality = 35  # Default
    return min(100, density + quality)


def score_grocery(stores):
    if not stores:
        return 0

    nearby = [g for g in stores if g["distance_miles"] <= 3]
    unique = len(set(g["name"].lower() for g in nearby))
    variety = min(40, round((unique / 5) * 40))

    closest = min(g["distance_miles"] for g in stores) if stores else 99
    if closest <= 0.5:
        prox = 30
    elif closest <= 1:
        prox = 25
    elif closest <= 2:
        prox = 15
    elif closest <= 3:
        prox = 10
    else:
        prox = 0

    costco_list = [g for g in stores if "costco" in g["name"].lower()]
    if costco_list:
        cd = min(c["distance_miles"] for c in costco_list)
        if cd <= 3:
            costco = 30
        elif cd <= 5:
            costco = 20
        elif cd <= 10:
            costco = 10
        else:
            costco = 0
    else:
        costco = 0

    return round(variety + prox + costco)


def score_schools(count):
    """Estimate based on school density. Edina district gets a bonus."""
    base = min(70, round((count / 5) * 70))
    # We default to 20 bonus pts since we can't auto-fetch ratings yet
    return min(100, base + 20)


def calculate_all_scores(apartment_data, neighborhood):
    """Calculate all 10 category scores."""
    scores = {}

    scores["price"] = score_price(apartment_data.get("rent", 0))
    scores["rooms"] = score_rooms(
        apartment_data.get("bedrooms", 2),
        apartment_data.get("bathrooms", 2),
        apartment_data.get("sqft", 0)
    )
    scores["necessities"] = score_necessities(apartment_data.get("amenities", []))
    scores["nice_to_haves"] = score_nice_to_haves(apartment_data.get("amenities", []))
    scores["schools"] = score_schools(neighborhood.get("school_count", 0))
    scores["crime"] = 65  # Default - Minneapolis crime data needs manual config
    scores["restaurants"] = score_restaurants(neighborhood.get("restaurant_count", 0))
    scores["commute"] = score_commute(
        neighborhood.get("commute_minutes", 60),
        neighborhood.get("transit_level", "none")
    )
    scores["nightlife"] = score_nightlife(neighborhood.get("nightlife_count", 0))
    scores["grocery"] = score_grocery(neighborhood.get("grocery_stores", []))

    values = list(scores.values())
    scores["overall"] = round(sum(values) / len(values))

    return scores


# ============================================
# API ENDPOINTS
# ============================================

# In-memory storage (will persist while server runs)
apartment_db = []


@app.route("/api/score", methods=["POST"])
def score_from_url():
    """
    Main endpoint: receives a URL + optional overrides,
    scrapes data, fetches neighborhood, returns scores.
    """
    body = request.json
    url = body.get("url", "")
    
    # Optional manual overrides
    manual_rent = body.get("rent")
    manual_beds = body.get("bedrooms")
    manual_baths = body.get("bathrooms")
    manual_sqft = body.get("sqft")
    manual_address = body.get("address")
    manual_name = body.get("name")

    result = {"status": "processing"}

    # Step 1: Scrape
    scraped = scrape_apartment(url) if url else {"scraped": False}

    # Step 2: Build apartment data (manual overrides take priority)
    apartment = {
        "name": manual_name or scraped.get("name") or "Unknown Apartment",
        "address": manual_address or scraped.get("address") or "",
        "url": url,
        "rent": manual_rent or (scraped.get("all_prices", [None])[0] if scraped.get("all_prices") else 0),
        "bedrooms": manual_beds or 2,
        "bathrooms": manual_baths or 2,
        "sqft": manual_sqft or 0,
        "amenities": scraped.get("classified_amenities", []),
        "tour_3d": scraped.get("tour_3d"),
        "raw_amenities": scraped.get("raw_amenities", []),
        "floor_plans_raw": scraped.get("floor_plans_raw", []),
    }

    # Step 3: Geocode + fetch neighborhood
    neighborhood = {}
    address_to_geocode = apartment["address"]
    
    if address_to_geocode:
        coords = geocode(address_to_geocode)
        if coords:
            apartment["lat"] = coords["lat"]
            apartment["lon"] = coords["lon"]
            neighborhood = fetch_neighborhood(coords["lat"], coords["lon"])
            apartment["neighborhood_data"] = neighborhood

    # Step 4: Score
    scores = calculate_all_scores(apartment, neighborhood)
    apartment["scores"] = scores

    # Step 5: Store
    apartment["id"] = str(int(time.time() * 1000))
    apartment_db.append(apartment)

    return jsonify({
        "status": "success",
        "apartment": apartment,
        "scores": scores,
        "neighborhood_summary": {
            "commute_minutes": neighborhood.get("commute_minutes"),
            "restaurant_count": neighborhood.get("restaurant_count", 0),
            "grocery_count": len(neighborhood.get("grocery_stores", [])),
            "has_costco": neighborhood.get("has_costco", False),
            "costco_distance": neighborhood.get("costco_distance"),
            "nightlife_count": neighborhood.get("nightlife_count", 0),
            "transit_level": neighborhood.get("transit_level", "unknown"),
            "school_count": neighborhood.get("school_count", 0)
        },
        "scrape_info": {
            "scraped": scraped.get("scraped", False),
            "amenities_found": scraped.get("raw_amenities", []),
            "amenities_classified": scraped.get("classified_amenities", []),
            "prices_found": scraped.get("all_prices", []),
            "tour_found": scraped.get("tour_3d") is not None
        }
    })


@app.route("/api/score-manual", methods=["POST"])
def score_manual():
    """
    Fallback endpoint for manual entry when scraping fails.
    Accepts all apartment data directly.
    """
    body = request.json

    apartment = {
        "name": body.get("name", "Unknown"),
        "address": body.get("address", ""),
        "url": body.get("url"),
        "rent": body.get("rent", 0),
        "bedrooms": body.get("bedrooms", 2),
        "bathrooms": body.get("bathrooms", 2),
        "sqft": body.get("sqft", 0),
        "amenities": body.get("amenities", []),
        "tour_3d": body.get("tour_3d"),
    }

    # Geocode + neighborhood
    neighborhood = {}
    if apartment["address"]:
        coords = geocode(apartment["address"])
        if coords:
            apartment["lat"] = coords["lat"]
            apartment["lon"] = coords["lon"]
            neighborhood = fetch_neighborhood(coords["lat"], coords["lon"])
            apartment["neighborhood_data"] = neighborhood

    scores = calculate_all_scores(apartment, neighborhood)
    apartment["scores"] = scores
    apartment["id"] = str(int(time.time() * 1000))
    apartment_db.append(apartment)

    return jsonify({
        "status": "success",
        "apartment": apartment,
        "scores": scores
    })


@app.route("/api/apartments", methods=["GET"])
def get_apartments():
    """Return all scored apartments."""
    return jsonify(apartment_db)


@app.route("/api/apartments/<apt_id>", methods=["DELETE"])
def delete_apartment(apt_id):
    """Delete an apartment."""
    global apartment_db
    apartment_db = [a for a in apartment_db if a["id"] != apt_id]
    return jsonify({"status": "deleted"})


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "running", "apartments_stored": len(apartment_db)})


# ============================================
# RUN SERVER
# ============================================

if __name__ == "__main__":
    print("\n🏢 Apartment Scorer API running!")
    print("   http://localhost:5000")
    print("   POST /api/score  — Score from URL")
    print("   POST /api/score-manual  — Score from manual input")
    print("   GET  /api/apartments  — Get all apartments")
    print("")
    app.run(debug=True, port=5000)
