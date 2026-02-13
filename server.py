# server.py
# Backend API - Apartment Scorer (Streamlined)

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re
import time
import math

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})


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
    "commute_target": {"lat": 44.9258, "lon": -93.4083}
}

AMENITY_KEYWORDS = {
    "covered_parking": ["covered parking", "garage parking", "indoor parking", "heated parking",
                         "parking garage", "underground parking", "heated underground"],
    "dishwasher": ["dishwasher"],
    "in_unit_laundry": ["in-unit laundry", "in unit laundry", "washer/dryer", "washer and dryer",
                         "in-home laundry", "w/d in unit", "washer & dryer", "in unit washer",
                         "full-size washer", "in-unit washer", "washer dryer"],
    "ac": ["air conditioning", "a/c", "central air", "climate control", "air-conditioning"],
    "pool": ["pool", "swimming"],
    "sauna_hot_tub": ["sauna", "hot tub", "spa", "steam room"],
    "gym": ["gym", "fitness center", "fitness room", "exercise room", "workout", "fitness"],
    "package_lockers": ["package locker", "parcel locker", "package room", "mailroom",
                         "package concierge", "package"]
}


# ============================================
# SCRAPER
# ============================================

def scrape_apartment(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            return {"error": f"Status {response.status_code}", "scraped": False}

        soup = BeautifulSoup(response.text, "html.parser")
        page_text = soup.get_text(separator=" ")
        page_text_lower = page_text.lower()

        data = {
            "scraped": True,
            "url": url,
            "name": extract_name(soup, url),
            "address": extract_address(soup, page_text),
            "floor_plans": extract_floor_plans(soup, page_text),
            "amenities_classified": classify_amenities(page_text_lower),
            "tour_3d": extract_tour(soup),
        }

        # Also scrape main site if on a subpage
        if "/floor-plan" in url.lower():
            base_url = get_base_url(url)
            if base_url:
                try:
                    main_resp = requests.get(base_url, headers=headers, timeout=10)
                    if main_resp.status_code == 200:
                        main_soup = BeautifulSoup(main_resp.text, "html.parser")
                        main_text = main_resp.text.lower()
                        if not data["name"]:
                            data["name"] = extract_name(main_soup, base_url)
                        if not data["address"]:
                            data["address"] = extract_address(main_soup, main_soup.get_text(separator=" "))
                        main_amenities = classify_amenities(main_text)
                        data["amenities_classified"] = list(set(data["amenities_classified"] + main_amenities))
                except Exception:
                    pass

        return data
    except Exception as e:
        return {"error": str(e), "scraped": False}


def get_base_url(url):
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/"
    except Exception:
        return None


def extract_name(soup, url):
    title = soup.find("title")
    if title:
        text = title.text.strip()
        for sep in ["|", "-", "–", ":", "•"]:
            if sep in text:
                text = text.split(sep)[0].strip()
        if text and len(text) < 100:
            return text
    h1 = soup.find("h1")
    if h1 and h1.text.strip():
        return h1.text.strip()[:100]
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.replace("www.", "")
        return domain.split(".")[0].title()
    except Exception:
        return None


def extract_address(soup, page_text):
    mn_pattern = re.search(
        r'(\d+\s+[A-Za-z\s]+(?:St|Street|Ave|Avenue|Blvd|Boulevard|Dr|Drive|Rd|Road|Way|Ln|Lane|Ct|Court)[^,]*,\s*[A-Za-z\s]+,\s*MN\s*\d{5})',
        page_text
    )
    if mn_pattern:
        return mn_pattern.group(1).strip()
    addr_pattern = re.search(
        r'(\d+\s+[A-Za-z\s]+(?:St|Street|Ave|Avenue|Blvd|Boulevard|Dr|Drive|Rd|Road|Way|Ln|Lane)[^,]*,\s*[A-Za-z\s]+,\s*[A-Z]{2}\s*\d{5})',
        page_text
    )
    if addr_pattern:
        return addr_pattern.group(1).strip()
    return None


def extract_floor_plans(soup, page_text):
    plans = []
    for container in soup.find_all(["div", "section", "article", "li"]):
        text = container.get_text(separator=" ").strip()
        if ("bedroom" in text.lower() or "bed" in text.lower()) and "$" in text:
            if 50 < len(text) < 2000:
                plan = parse_plan(text, container)
                if plan and plan.get("bedrooms"):
                    # Check for duplicates
                    is_dup = False
                    for existing in plans:
                        if existing.get("sqft") == plan.get("sqft") and existing.get("bedrooms") == plan.get("bedrooms"):
                            is_dup = True
                            break
                    if not is_dup:
                        plans.append(plan)
    return plans


def parse_plan(text, element=None):
    plan = {"bedrooms": None, "bathrooms": None, "sqft": None, "units": [], "tour_3d": None}
    text_lower = text.lower()

    bed_match = re.search(r'(\d+)\s*(?:bedroom|bed|br)', text_lower)
    if bed_match:
        plan["bedrooms"] = int(bed_match.group(1))

    bath_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:bathroom|bath|ba)', text_lower)
    if bath_match:
        val = float(bath_match.group(1))
        plan["bathrooms"] = int(val) if val == int(val) else val

    for pattern in [r'(?:total\s+(?:interior\s+)?sq\s*ft[:\s]*)([\d,]+)', r'([\d,]+)\s*(?:sq\s*ft|sqft|sf)']:
        sqft_match = re.search(pattern, text_lower)
        if sqft_match:
            plan["sqft"] = int(sqft_match.group(1).replace(",", ""))
            break

    unit_pattern = re.findall(r'#(\w+)\s+available\s+([^,]+),\s*\$([\d,]+)/mo', text, re.IGNORECASE)
    for unit_num, avail, price in unit_pattern:
        plan["units"].append({"unit": f"#{unit_num}", "available": avail.strip(), "rent": int(price.replace(",", ""))})

    if not plan["units"]:
        for p in re.findall(r'\$([\d,]+)\s*/\s*mo', text):
            val = int(p.replace(",", ""))
            if 500 <= val <= 10000:
                plan["units"].append({"unit": "?", "available": "?", "rent": val})

    if element:
        for link in element.find_all("a", href=True):
            if "3d" in link["href"].lower() or "3d" in link.get_text().lower():
                plan["tour_3d"] = link["href"]
                break

    fee_match = re.search(r'service\s+fee[:\s]*\$([\d,]+)', text_lower)
    if fee_match:
        plan["service_fee"] = int(fee_match.group(1).replace(",", ""))

    return plan


def classify_amenities(text):
    classified = []
    for key, keywords in AMENITY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            classified.append(key)
    return list(set(classified))


def extract_tour(soup):
    for link in soup.find_all("a", href=True):
        href = link["href"].lower()
        link_text = link.get_text().lower()
        if any(p in href for p in ["matterport", "3d-plan", "plan-3d", "virtual-tour"]) or "3d" in link_text:
            return link["href"]
    return None


# ============================================
# NEIGHBORHOOD - FAST VERSION
# ============================================

def geocode(address):
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1},
            headers={"User-Agent": "apartment-scorer-app"},
            timeout=10
        )
        results = resp.json()
        if results:
            return {"lat": float(results[0]["lat"]), "lon": float(results[0]["lon"])}
    except Exception as e:
        print(f"Geocoding error: {e}")
    return None


def haversine_miles(lat1, lon1, lat2, lon2):
    R = 3959
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def overpass_combined(lat, lon):
    """Single combined Overpass query for ALL nearby amenities at once."""
    query = f"""[out:json][timeout:20];
    (
        node["amenity"="restaurant"](around:2500,{lat},{lon});
        node["amenity"="cafe"](around:2500,{lat},{lon});
        node["amenity"="bar"](around:3000,{lat},{lon});
        node["amenity"="nightclub"](around:3000,{lat},{lon});
        node["amenity"="cinema"](around:3000,{lat},{lon});
        node["amenity"="school"](around:3000,{lat},{lon});
        node["shop"="supermarket"](around:5000,{lat},{lon});
        node["highway"="bus_stop"](around:1000,{lat},{lon});
        node["railway"="station"](around:2000,{lat},{lon});
    );
    out body;"""

    try:
        resp = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            timeout=25
        )
        return resp.json().get("elements", [])
    except Exception as e:
        print(f"Overpass error: {e}")
        return []


def overpass_wholesale(lat, lon):
    """Separate query for wholesale/Costco with wider radius."""
    query = f"""[out:json][timeout:15];
    node["shop"="wholesale"](around:16000,{lat},{lon});
    out body;"""

    try:
        resp = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            timeout=20
        )
        return resp.json().get("elements", [])
    except Exception as e:
        print(f"Wholesale query error: {e}")
        return []


def fetch_neighborhood(lat, lon):
    """Fetch neighborhood data with minimal API calls."""
    results = {
        "restaurant_count": 0,
        "grocery_stores": [],
        "has_costco": False,
        "costco_distance": None,
        "nightlife_count": 0,
        "transit_count": 0,
        "transit_level": "none",
        "school_count": 0,
        "commute_minutes": 0
    }

    # Single combined query for most things
    elements = overpass_combined(lat, lon)

    restaurants = []
    bars = []
    schools = []
    grocery = []
    transit = []

    for el in elements:
        if "lat" not in el or "lon" not in el:
            continue
        tags = el.get("tags", {})
        name = tags.get("name", "Unnamed")
        dist = haversine_miles(lat, lon, el["lat"], el["lon"])
        place = {"name": name, "distance_miles": round(dist, 2)}

        amenity = tags.get("amenity", "")
        shop = tags.get("shop", "")
        highway = tags.get("highway", "")
        railway = tags.get("railway", "")

        if amenity in ("restaurant", "cafe"):
            restaurants.append(place)
        elif amenity in ("bar", "nightclub", "cinema"):
            bars.append(place)
        elif amenity == "school":
            schools.append(place)
        elif shop == "supermarket":
            grocery.append(place)
        elif highway == "bus_stop" or railway == "station":
            transit.append(place)

    # Separate wholesale query for Costco
    time.sleep(1)
    wholesale_elements = overpass_wholesale(lat, lon)
    for el in wholesale_elements:
        if "lat" not in el or "lon" not in el:
            continue
        tags = el.get("tags", {})
        name = tags.get("name", "Unnamed")
        dist = haversine_miles(lat, lon, el["lat"], el["lon"])
        grocery.append({"name": name, "distance_miles": round(dist, 2)})

    grocery.sort(key=lambda x: x["distance_miles"])

    # Build results
    results["restaurant_count"] = len(restaurants)
    results["nightlife_count"] = len(bars)
    results["school_count"] = len(schools)
    results["transit_count"] = len(transit)
    results["grocery_stores"] = grocery[:15]

    if len(transit) >= 5:
        results["transit_level"] = "nearby"
    elif len(transit) >= 2:
        results["transit_level"] = "some"

    results["has_costco"] = any("costco" in g["name"].lower() for g in grocery)
    results["costco_distance"] = next(
        (g["distance_miles"] for g in grocery if "costco" in g["name"].lower()), None
    )

    # Commute
    commute_miles = haversine_miles(lat, lon, USER_SETTINGS["commute_target"]["lat"], USER_SETTINGS["commute_target"]["lon"])
    results["commute_minutes"] = round((commute_miles * 1.4 / 25) * 60)

    return results


# ============================================
# SCORING
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
    sqft_score = 20 if sqft >= USER_SETTINGS["ideal_sqft"] else (10 if sqft >= USER_SETTINGS["ideal_sqft"] * 0.8 else 0)
    return round(bed_score + bath_score + sqft_score)

def score_necessities(amenities):
    for n in USER_SETTINGS["necessities"]:
        if n not in amenities:
            return 0
    return 100

def score_nice_to_haves(amenities):
    total = len(USER_SETTINGS["nice_to_haves"])
    if total == 0: return 100
    count = sum(1 for n in USER_SETTINGS["nice_to_haves"] if n in amenities)
    return round((count / total) * 100)

def score_restaurants(count):
    return min(100, round((count / 20) * 50) + 35)

def score_commute(mins, transit):
    if mins <= 10: d = 70
    elif mins <= 20: d = 55
    elif mins <= 30: d = 40
    elif mins <= 45: d = 25
    else: d = 10
    t = {"nearby": 30, "some": 15, "none": 0}.get(transit, 0)
    return round(d + t)

def score_nightlife(count):
    return min(100, round((count / 10) * 50) + 35)

def score_grocery(stores):
    if not stores: return 0
    nearby = [g for g in stores if g["distance_miles"] <= 3]
    variety = min(40, round((len(set(g["name"].lower() for g in nearby)) / 5) * 40))
    closest = min(g["distance_miles"] for g in stores)
    prox = 30 if closest <= 0.5 else (25 if closest <= 1 else (15 if closest <= 2 else (10 if closest <= 3 else 0)))
    costco_list = [g for g in stores if "costco" in g["name"].lower()]
    costco = 0
    if costco_list:
        cd = min(c["distance_miles"] for c in costco_list)
        costco = 30 if cd <= 3 else (20 if cd <= 5 else (10 if cd <= 10 else 0))
    return round(variety + prox + costco)

def score_schools(count):
    return min(100, round((count / 5) * 70) + 20)

def calculate_all_scores(apt, nbr):
    s = {}
    s["price"] = score_price(apt.get("rent", 0))
    s["rooms"] = score_rooms(apt.get("bedrooms", 2), apt.get("bathrooms", 2), apt.get("sqft", 0))
    s["necessities"] = score_necessities(apt.get("amenities", []))
    s["nice_to_haves"] = score_nice_to_haves(apt.get("amenities", []))
    s["schools"] = score_schools(nbr.get("school_count", 0))
    s["crime"] = 65
    s["restaurants"] = score_restaurants(nbr.get("restaurant_count", 0))
    s["commute"] = score_commute(nbr.get("commute_minutes", 60), nbr.get("transit_level", "none"))
    s["nightlife"] = score_nightlife(nbr.get("nightlife_count", 0))
    s["grocery"] = score_grocery(nbr.get("grocery_stores", []))
    vals = list(s.values())
    s["overall"] = round(sum(vals) / len(vals))
    return s


# ============================================
# API ENDPOINTS
# ============================================

apartment_db = []

@app.route("/api/score", methods=["POST"])
def score_from_url():
    body = request.json
    url = body.get("url", "")

    scraped = scrape_apartment(url) if url else {"scraped": False}

    if not scraped.get("scraped"):
        return jsonify({"status": "scrape_failed", "error": scraped.get("error", "Could not scrape"), "needs_manual": True})

    all_plans = scraped.get("floor_plans", [])
    matching = [p for p in all_plans if p.get("bedrooms") == 2 and p.get("bathrooms") == 2]
    if not matching:
        matching = all_plans

    # Geocode + neighborhood (once)
    neighborhood = {}
    address = scraped.get("address", "")
    coords = None
    if address:
        coords = geocode(address)
        if coords:
            neighborhood = fetch_neighborhood(coords["lat"], coords["lon"])

    scored_plans = []
    for i, plan in enumerate(matching):
        units = plan.get("units", [])
        rents = [u["rent"] for u in units if u.get("rent")]
        best_rent = min(rents) if rents else 0

        apt = {
            "name": scraped.get("name") or "Unknown",
            "address": address,
            "url": url,
            "rent": best_rent,
            "bedrooms": plan.get("bedrooms", 2),
            "bathrooms": plan.get("bathrooms", 2),
            "sqft": plan.get("sqft", 0),
            "amenities": scraped.get("amenities_classified", []),
            "tour_3d": plan.get("tour_3d") or scraped.get("tour_3d"),
            "units_available": units,
            "service_fee": plan.get("service_fee"),
            "neighborhood_data": neighborhood,
            "id": str(int(time.time() * 1000)) + str(i)
        }
        if coords:
            apt["lat"] = coords["lat"]
            apt["lon"] = coords["lon"]

        apt["scores"] = calculate_all_scores(apt, neighborhood)
        scored_plans.append(apt)

    apartment_db.extend(scored_plans)

    return jsonify({
        "status": "success",
        "apartments": scored_plans,
        "total_plans_found": len(all_plans),
        "matching_plans": len(matching),
        "scrape_info": {
            "name": scraped.get("name"),
            "address": address,
            "amenities_detected": scraped.get("amenities_classified", []),
            "tour_found": scraped.get("tour_3d") is not None
        }
    })


@app.route("/api/score-manual", methods=["POST"])
def score_manual():
    body = request.json
    apt = {
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
    neighborhood = {}
    if apt["address"]:
        coords = geocode(apt["address"])
        if coords:
            apt["lat"] = coords["lat"]
            apt["lon"] = coords["lon"]
            neighborhood = fetch_neighborhood(coords["lat"], coords["lon"])
            apt["neighborhood_data"] = neighborhood
    apt["scores"] = calculate_all_scores(apt, neighborhood)
    apt["id"] = str(int(time.time() * 1000))
    apartment_db.append(apt)
    return jsonify({"status": "success", "apartment": apt, "scores": apt["scores"]})


@app.route("/api/apartments", methods=["GET"])
def get_apartments():
    return jsonify(apartment_db)


@app.route("/api/apartments/<apt_id>", methods=["DELETE"])
def delete_apartment(apt_id):
    global apartment_db
    apartment_db = [a for a in apartment_db if a["id"] != apt_id]
    return jsonify({"status": "deleted"})


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "running", "apartments_stored": len(apartment_db)})


if __name__ == "__main__":
    print("Apartment Scorer API running on http://localhost:5000")
    app.run(debug=True, port=5000)
