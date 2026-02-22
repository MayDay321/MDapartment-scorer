# server.py
# Backend API - Apartment Scorer (apartments.com optimized)

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
    "covered_parking": ["underground parking", "covered parking", "garage parking", "indoor parking",
                         "heated parking", "parking garage", "heated underground", "parking structure"],
    "dishwasher": ["dishwasher"],
    "in_unit_laundry": ["in-unit laundry", "in unit laundry", "washer/dryer", "washer and dryer",
                         "in-home laundry", "w/d in unit", "washer & dryer", "in unit washer",
                         "full-size washer", "in-unit washer", "washer dryer", "in-home washer"],
    "ac": ["air conditioning", "a/c", "central air", "climate control", "air-conditioning",
            "air conditioned", "central a/c", "hvac"],
    "pool": ["pool", "swimming", "lap pool", "heated pool", "indoor pool"],
    "sauna_hot_tub": ["sauna", "hot tub", "spa", "steam room"],
    "gym": ["gym", "fitness center", "fitness room", "exercise room", "workout", "fitness",
             "technogym", "24 hour gym", "weight room"],
    "package_lockers": ["package locker", "parcel locker", "package room", "mailroom",
                         "package concierge", "package receiving", "amazon locker"]
}


# ============================================
# APARTMENTS.COM SCRAPER
# ============================================

def scrape_apartments_com(url):
    """Scrape an apartments.com listing page."""
    
    # Try multiple user agents
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    ]

    for ua in user_agents:
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }

        try:
            response = requests.get(url, headers=headers, timeout=20)
            if response.status_code == 200:
                break
        except Exception:
            continue
    else:
        return {"error": "Blocked by apartments.com (403)", "scraped": False}

    if response.status_code != 200:
        return {"error": f"Status {response.status_code}", "scraped": False}

    soup = BeautifulSoup(response.text, "html.parser")
    page_text_lower = soup.get_text(separator=" ").lower()

    data = {
        "scraped": True,
        "url": url,
        "name": None,
        "address": None,
        "floor_plans": [],
        "amenities_raw": [],
        "amenities_classified": [],
        "tour_3d": None
    }

    # 1. PROPERTY NAME
    name_el = soup.select_one("h1#propertyName") or soup.select_one("h1.propertyName")
    if name_el:
        data["name"] = name_el.text.strip()

    # 2. ADDRESS
    data["address"] = extract_address_adc(soup)

    # 3. FLOOR PLANS
    data["floor_plans"] = extract_floor_plans_adc(soup)

    # 4. AMENITIES
    data["amenities_raw"] = extract_amenities_adc(soup)
    data["amenities_classified"] = classify_amenities_adc(data["amenities_raw"], page_text_lower)

    # 5. 3D TOUR
    data["tour_3d"] = extract_tour_adc(soup)

    return data


def extract_address_adc(soup):
    """Extract address from apartments.com."""
    street = ""
    city = ""
    state = ""
    zipcode = ""

    # Street address
    street_el = soup.select_one("span.delivery-address")
    if street_el:
        street = street_el.text.strip().rstrip(",").strip()

    # City, State, Zip from the address container
    addr_container = soup.select_one("div.propertyAddressContainer")
    if addr_container:
        h2 = addr_container.find("h2")
        if h2:
            # Get all direct text and spans
            all_spans = h2.find_all("span")
            for span in all_spans:
                cls = " ".join(span.get("class", []))
                text = span.text.strip().rstrip(",").strip()

                if "delivery-address" in cls:
                    continue
                elif "stateZipContainer" in cls:
                    inner = span.find_all("span")
                    for s in inner:
                        t = s.text.strip()
                        if len(t) == 2 and t.isupper():
                            state = t
                        elif t.isdigit() and len(t) == 5:
                            zipcode = t
                elif "neighborhoodAddress" in cls:
                    continue
                elif text and not city and text != street:
                    city = text

    # If we still don't have city, try neighborhoodAddress
    if not city:
        neighborhood = soup.select_one("span.neighborhoodAddress")
        if neighborhood:
            # Often contains "Edina" or similar
            text = neighborhood.text.strip().rstrip(",").strip()
            if text:
                city = text.split(",")[0].strip()

    # Build full address
    parts = []
    if street:
        parts.append(street)
    if city:
        parts.append(city)
    if state and zipcode:
        parts.append(f"{state} {zipcode}")
    elif state:
        parts.append(state)

    if parts:
        return ", ".join(parts)

    return None

def extract_floor_plans_adc(soup):
    """Extract all floor plans from apartments.com pricing grid."""
    plans = []

    # Each floor plan is in a priceGridModelWrapper
    wrappers = soup.select("div.priceGridModelWrapper")

    for wrapper in wrappers:
        plan = {
            "plan_name": None,
            "bedrooms": None,
            "bathrooms": None,
            "sqft": None,
            "rent": None,
            "deposit": None,
            "rental_key": None,
            "units": []
        }

        # Rental key
        plan["rental_key"] = wrapper.get("data-rentalkey")

        # Model/Plan name
        model_name = wrapper.select_one("span.modelName")
        if model_name:
            plan["plan_name"] = model_name.text.strip()

        # Rent
        rent_label = wrapper.select_one("span.rentLabel")
        if rent_label:
            rent_text = rent_label.get_text(separator=" ").strip()
            rent_match = re.search(r'\$([\d,]+)', rent_text)
            if rent_match:
                plan["rent"] = int(rent_match.group(1).replace(",", ""))

        # Details (beds, baths, sqft, deposit)
        details = wrapper.select_one("span.detailsTextWrapper")
        if details:
            spans = details.find_all("span")
            for span in spans:
                text = span.text.strip().lower()

                bed_match = re.search(r'(\d+)\s*bed', text)
                if bed_match:
                    plan["bedrooms"] = int(bed_match.group(1))

                bath_match = re.search(r'(\d+(?:\.\d+)?)\s*bath', text)
                if bath_match:
                    val = float(bath_match.group(1))
                    plan["bathrooms"] = int(val) if val == int(val) else val

                sqft_match = re.search(r'([\d,]+)\s*sq\s*ft', text)
                if sqft_match:
                    plan["sqft"] = int(sqft_match.group(1).replace(",", ""))

                deposit_match = re.search(r'\$([\d,]+)\s*deposit', text)
                if deposit_match:
                    plan["deposit"] = int(deposit_match.group(1).replace(",", ""))

        # If details wrapper didn't have beds/baths, try detailsLabel
        if not plan["bedrooms"]:
            details_label = wrapper.select_one("span.detailsLabel")
            if details_label:
                text = details_label.get_text(separator=" ").lower()
                bed_match = re.search(r'(\d+)\s*bed', text)
                if bed_match:
                    plan["bedrooms"] = int(bed_match.group(1))
                bath_match = re.search(r'(\d+(?:\.\d+)?)\s*bath', text)
                if bath_match:
                    val = float(bath_match.group(1))
                    plan["bathrooms"] = int(val) if val == int(val) else val
                sqft_match = re.search(r'([\d,]+)\s*sq\s*ft', text)
                if sqft_match:
                    plan["sqft"] = int(sqft_match.group(1).replace(",", ""))

        # Also check for individual unit rows within this plan
        unit_rows = wrapper.select("li.unitContainer") or wrapper.select("div.unitContainer")
        for unit_row in unit_rows:
            unit = {"unit_number": None, "rent": None, "sqft": None, "available": None}

            unit_text = unit_row.get_text(separator=" ").strip()

            # Unit number
            unit_num = unit_row.select_one("span.unitColumn") or unit_row.select_one("button.unitBtn")
            if unit_num:
                unit["unit_number"] = unit_num.text.strip()

            # Rent for this specific unit
            unit_rent = re.search(r'\$([\d,]+)', unit_text)
            if unit_rent:
                unit["rent"] = int(unit_rent.group(1).replace(",", ""))

            # Availability
            avail = unit_row.select_one("span.availableDate") or unit_row.select_one("span.dateAvailable")
            if avail:
                unit["available"] = avail.text.strip()

            if unit["rent"]:
                plan["units"].append(unit)

        # If no rent from main label, try from units
        if not plan["rent"] and plan["units"]:
            rents = [u["rent"] for u in plan["units"] if u["rent"]]
            if rents:
                plan["rent"] = min(rents)

        # Only add plans that have at least beds info
        if plan["bedrooms"] is not None or plan["rent"] is not None:
            plans.append(plan)

    # Also try JSON data embedded in page
    if not plans:
        plans = extract_plans_from_json(soup)

    return plans


def extract_plans_from_json(soup):
    """Fallback: try to find floor plan data in embedded JSON."""
    plans = []
    scripts = soup.find_all("script")
    for script in scripts:
        text = script.string or ""
        if "MinTotalMonthlyPrice" in text or "MaxTotalMonthlyPrice" in text:
            # Try to parse rental data
            try:
                matches = re.findall(
                    r'"ModelName":"([^"]*)".*?"Beds":(\d+).*?"Baths":([\d.]+).*?"MinSquareFeet":(\d+).*?"MinTotalMonthlyPrice":([\d.]+)',
                    text
                )
                for name, beds, baths, sqft, price in matches:
                    plans.append({
                        "plan_name": name,
                        "bedrooms": int(beds),
                        "bathrooms": int(float(baths)),
                        "sqft": int(sqft),
                        "rent": int(float(price)),
                        "units": []
                    })
            except Exception:
                pass
    return plans


def extract_amenities_adc(soup):
    """Extract amenity list from apartments.com."""
    amenities = []

    # Primary: uniqueAmenity items
    for li in soup.select("li.specInfo.uniqueAmenity"):
        span = li.find("span")
        if span:
            amenities.append(span.text.strip())

    # Also check other amenity sections
    for li in soup.select("li.specInfo"):
        span = li.find("span")
        if span:
            text = span.text.strip()
            if text and text not in amenities:
                amenities.append(text)

    # Check for "In-Unit Features" or similar sections
    for section in soup.select("div.specList"):
        for li in section.find_all("li"):
            text = li.get_text(separator=" ").strip()
            if text and text not in amenities and len(text) < 100:
                amenities.append(text)

    return amenities


def classify_amenities_adc(raw_amenities, page_text=""):
    """Classify raw amenity strings into our scoring categories."""
    classified = []
    combined = " ".join(raw_amenities).lower() + " " + page_text.lower()

    for key, keywords in AMENITY_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            classified.append(key)

    return list(set(classified))


def extract_tour_adc(soup):
    """Find 3D tour or virtual tour links."""
    # Look for tour buttons/links
    for link in soup.find_all("a", href=True):
        href = link["href"].lower()
        text = link.get_text().lower()
        if any(kw in href for kw in ["matterport", "3d-tour", "virtual-tour", "tour.realync"]):
            return link["href"]
        if any(kw in text for kw in ["3d tour", "virtual tour", "take a tour"]):
            return link["href"]

    # Check for tour iframes
    for iframe in soup.find_all("iframe", src=True):
        src = iframe["src"].lower()
        if any(kw in src for kw in ["matterport", "tour", "3d"]):
            return iframe["src"]

    # Check for tour buttons
    for btn in soup.select("button"):
        text = btn.get_text().lower()
        if "tour" in text or "3d" in text:
            onclick = btn.get("onclick", "") or btn.get("data-url", "")
            if onclick:
                return onclick

    return None


# ============================================
# GENERIC SCRAPER (fallback for non-apartments.com)
# ============================================

def scrape_generic(url):
    """Fallback scraper for non-apartments.com sites."""
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

        # Try to extract basic info
        name = None
        title = soup.find("title")
        if title:
            name = title.text.strip().split("|")[0].split("-")[0].strip()

        address = None
        addr_match = re.search(
            r'(\d+\s+[A-Za-z\s]+(?:St|Street|Ave|Avenue|Blvd|Boulevard|Dr|Drive|Rd|Road|Way|Ln|Lane)[^,]*,\s*[A-Za-z\s]+,\s*[A-Z]{2}\s*\d{5})',
            page_text
        )
        if addr_match:
            address = addr_match.group(1).strip()

        return {
            "scraped": True,
            "url": url,
            "name": name,
            "address": address,
            "floor_plans": [],
            "amenities_raw": [],
            "amenities_classified": classify_amenities_adc([], page_text_lower),
            "tour_3d": None
        }
    except Exception as e:
        return {"error": str(e), "scraped": False}


def scrape_apartment(url):
    """Route to the right scraper based on URL."""
    if "apartments.com" in url.lower():
        return scrape_apartments_com(url)
    else:
        return scrape_generic(url)


# ============================================
# NEIGHBORHOOD DATA
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
    """Single combined query for all nearby amenities."""
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
        resp = requests.post("https://overpass-api.de/api/interpreter", data={"data": query}, timeout=25)
        return resp.json().get("elements", [])
    except Exception as e:
        print(f"Overpass error: {e}")
        return []


def overpass_wholesale(lat, lon):
    """Separate query for Costco/wholesale with wider radius."""
    query = f"""[out:json][timeout:15];
    node["shop"="wholesale"](around:16000,{lat},{lon});
    out body;"""
    try:
        resp = requests.post("https://overpass-api.de/api/interpreter", data={"data": query}, timeout=20)
        return resp.json().get("elements", [])
    except Exception as e:
        print(f"Wholesale error: {e}")
        return []


def fetch_neighborhood(lat, lon):
    """Fetch all neighborhood data with 2 API calls."""
    results = {
        results["restaurants_nearby"] = sorted(restaurants, key=lambda x: x["distance_miles"])[:15]
    results["nightlife_nearby"] = sorted(bars, key=lambda x: x["distance_miles"])[:15]
    results["schools_nearby"] = sorted(schools, key=lambda x: x["distance_miles"])[:10]
        "restaurant_count": 0, "grocery_stores": [], "has_costco": False,
        "costco_distance": None, "nightlife_count": 0, "transit_count": 0,
        "transit_level": "none", "school_count": 0, "commute_minutes": 0
    }

    elements = overpass_combined(lat, lon)

    restaurants, bars, schools, grocery, transit = [], [], [], [], []

    for el in elements:
        if "lat" not in el or "lon" not in el:
            continue
        tags = el.get("tags", {})
        name = tags.get("name", "Unnamed")
        dist = haversine_miles(lat, lon, el["lat"], el["lon"])
        place = {"name": name, "distance_miles": round(dist, 2)}

        amenity = tags.get("amenity", "")
        shop = tags.get("shop", "")

        if amenity in ("restaurant", "cafe"): restaurants.append(place)
        elif amenity in ("bar", "nightclub", "cinema"): bars.append(place)
        elif amenity == "school": schools.append(place)
        elif shop == "supermarket": grocery.append(place)
        elif tags.get("highway") == "bus_stop" or tags.get("railway") == "station": transit.append(place)

    time.sleep(1)
    for el in overpass_wholesale(lat, lon):
        if "lat" not in el or "lon" not in el:
            continue
        tags = el.get("tags", {})
        name = tags.get("name", "Unnamed")
        dist = haversine_miles(lat, lon, el["lat"], el["lon"])
        grocery.append({"name": name, "distance_miles": round(dist, 2)})

    grocery.sort(key=lambda x: x["distance_miles"])

    results["restaurant_count"] = len(restaurants)
    results["nightlife_count"] = len(bars)
    results["school_count"] = len(schools)
    results["transit_count"] = len(transit)
    results["grocery_stores"] = grocery[:15]
    results["transit_level"] = "nearby" if len(transit) >= 5 else ("some" if len(transit) >= 2 else "none")
    results["has_costco"] = any("costco" in g["name"].lower() for g in grocery)
    results["costco_distance"] = next((g["distance_miles"] for g in grocery if "costco" in g["name"].lower()), None)

    commute_miles = haversine_miles(lat, lon, USER_SETTINGS["commute_target"]["lat"], USER_SETTINGS["commute_target"]["lon"])
    results["commute_minutes"] = round((commute_miles * 1.4 / 25) * 60)
    results["restaurants_nearby"] = sorted(restaurants, key=lambda x: x["distance_miles"])[:15]
    results["nightlife_nearby"] = sorted(bars, key=lambda x: x["distance_miles"])[:15]

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
    return round(d + {"nearby": 30, "some": 15, "none": 0}.get(transit, 0))

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

    # Filter to 2bd/2ba plans
    all_plans = scraped.get("floor_plans", [])
    matching = [p for p in all_plans if p.get("bedrooms") == 2 and p.get("bathrooms") == 2]
    if not matching:
        matching = [p for p in all_plans if p.get("bedrooms") == 2]
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

    # Score each matching plan
    scored_plans = []
    for i, plan in enumerate(matching):
        rent = plan.get("rent", 0)
        if not rent and plan.get("units"):
            rents = [u["rent"] for u in plan["units"] if u.get("rent")]
            rent = min(rents) if rents else 0

        apt = {
            "name": scraped.get("name") or "Unknown",
            "address": address,
            "url": url,
            "rent": rent,
            "bedrooms": plan.get("bedrooms", 2),
            "bathrooms": plan.get("bathrooms", 2),
            "sqft": plan.get("sqft", 0),
            "amenities": scraped.get("amenities_classified", []),
            "amenities_raw": scraped.get("amenities_raw", []),
            "tour_3d": scraped.get("tour_3d"),
            "plan_name": plan.get("plan_name"),
            "units_available": plan.get("units", []),
            "deposit": plan.get("deposit"),
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
            "amenities_raw": scraped.get("amenities_raw", []),
            "tour_found": scraped.get("tour_3d") is not None,
            "all_plans_count": len(all_plans)
        }
    })

@app.route("/api/score-source", methods=["POST"])
def score_from_source():
    """Parse raw HTML source from apartments.com."""
    body = request.json
    source = body.get("source", "")
    url = body.get("url", "")

    if not source:
        return jsonify({"status": "error", "error": "No source provided"})

    soup = BeautifulSoup(source, "html.parser")
    page_text_lower = soup.get_text(separator=" ").lower()

    # Parse using apartments.com selectors
    name = None
    name_el = soup.select_one("h1#propertyName") or soup.select_one("h1.propertyName")
    if name_el:
        name = name_el.text.strip()

    address = extract_address_adc(soup)
    floor_plans = extract_floor_plans_adc(soup)
    amenities_raw = extract_amenities_adc(soup)
    amenities_classified = classify_amenities_adc(amenities_raw, page_text_lower)
    tour = extract_tour_adc(soup)

    if not floor_plans:
        return jsonify({"status": "no_plans", "error": "No floor plans found"})

    # Filter to 2bd/2ba
    matching = [p for p in floor_plans if p.get("bedrooms") == 2 and p.get("bathrooms") == 2]
    if not matching:
        matching = [p for p in floor_plans if p.get("bedrooms") == 2]
    if not matching:
        matching = floor_plans

    # Geocode + neighborhood
    neighborhood = {}
    coords = None
    if address:
        coords = geocode(address)
        if coords:
            neighborhood = fetch_neighborhood(coords["lat"], coords["lon"])

    scored_plans = []
    for i, plan in enumerate(matching):
        rent = plan.get("rent", 0)
        if not rent and plan.get("units"):
            rents = [u["rent"] for u in plan["units"] if u.get("rent")]
            rent = min(rents) if rents else 0

        apt = {
            "name": name or "Unknown",
            "address": address or "",
            "url": url,
            "rent": rent,
            "bedrooms": plan.get("bedrooms", 2),
            "bathrooms": plan.get("bathrooms", 2),
            "sqft": plan.get("sqft", 0),
            "amenities": amenities_classified,
            "amenities_raw": amenities_raw,
            "tour_3d": tour,
            "plan_name": plan.get("plan_name"),
            "units_available": plan.get("units", []),
            "deposit": plan.get("deposit"),
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
        "total_plans_found": len(floor_plans),
        "matching_plans": len(matching),
        "scrape_info": {
            "name": name,
            "address": address,
            "amenities_detected": amenities_classified,
            "amenities_raw": amenities_raw,
            "tour_found": tour is not None
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
