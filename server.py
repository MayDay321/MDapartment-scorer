# server.py
# Backend API - Apartment Scorer

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re
import json
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
    "commute_target": {"lat": 44.9258, "lon": -93.4083, "name": "Hopkins, MN"}
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
# SMART SCRAPER
# ============================================

def scrape_apartment(url):
    """Scrape apartment data from URL with multiple strategies."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            return {"error": f"Status {response.status_code}", "scraped": False}

        soup = BeautifulSoup(response.text, "html.parser")
        page_text = soup.get_text(separator=" ")
        page_text_lower = page_text.lower()
        html = response.text

        data = {
            "scraped": True,
            "url": url,
            "name": None,
            "address": None,
            "floor_plans": [],
            "amenities_classified": [],
            "tour_3d": None,
            "raw_amenities": []
        }

        # Extract apartment name
        data["name"] = extract_name(soup, url)

        # Extract address
        data["address"] = extract_address(soup, page_text)

        # Extract floor plans (the key part!)
        data["floor_plans"] = extract_floor_plans_smart(soup, page_text, html)

        # Classify amenities from full page text
        data["amenities_classified"] = classify_amenities(page_text_lower)

        # Find 3D tour links
        data["tour_3d"] = extract_tour(soup)

        # Also scrape the main site if we're on a floor plans subpage
        if "/floor-plan" in url.lower():
            base_url = get_base_url(url)
            if base_url:
                try:
                    main_resp = requests.get(base_url, headers=headers, timeout=15)
                    if main_resp.status_code == 200:
                        main_soup = BeautifulSoup(main_resp.text, "html.parser")
                        main_text = main_resp.text.lower()

                        # Get name from main page if we don't have it
                        if not data["name"]:
                            data["name"] = extract_name(main_soup, base_url)

                        # Get address from main page if we don't have it
                        if not data["address"]:
                            data["address"] = extract_address(main_soup, main_soup.get_text(separator=" "))

                        # Merge amenities from main page
                        main_amenities = classify_amenities(main_text)
                        data["amenities_classified"] = list(set(
                            data["amenities_classified"] + main_amenities
                        ))
                except Exception:
                    pass

        return data

    except Exception as e:
        return {"error": str(e), "scraped": False}


def get_base_url(url):
    """Get the base domain URL from a subpage URL."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/"
    except Exception:
        return None


def extract_name(soup, url):
    """Extract apartment name."""
    # Try title tag first
    title = soup.find("title")
    if title:
        text = title.text.strip()
        # Clean up common title patterns
        for sep in ["|", "-", "–", ":", "•"]:
            if sep in text:
                text = text.split(sep)[0].strip()
        if text and len(text) < 100:
            return text

    # Try h1
    h1 = soup.find("h1")
    if h1 and h1.text.strip():
        return h1.text.strip()[:100]

    # Fall back to domain name
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.replace("www.", "")
        name = domain.split(".")[0].title()
        return name
    except Exception:
        return None


def extract_address(soup, page_text):
    """Extract address using multiple strategies."""
    # Look for common address patterns in text
    # Minnesota address pattern
    mn_pattern = re.search(
        r'(\d+\s+[A-Za-z\s]+(?:St|Street|Ave|Avenue|Blvd|Boulevard|Dr|Drive|Rd|Road|Way|Ln|Lane|Ct|Court)[^,]*,\s*[A-Za-z\s]+,\s*MN\s*\d{5})',
        page_text
    )
    if mn_pattern:
        return mn_pattern.group(1).strip()

    # Generic US address pattern
    addr_pattern = re.search(
        r'(\d+\s+[A-Za-z\s]+(?:St|Street|Ave|Avenue|Blvd|Boulevard|Dr|Drive|Rd|Road|Way|Ln|Lane)[^,]*,\s*[A-Za-z\s]+,\s*[A-Z]{2}\s*\d{5})',
        page_text
    )
    if addr_pattern:
        return addr_pattern.group(1).strip()

    # Look for structured address elements
    for selector in [".address", "[itemprop='address']", ".property-address",
                      ".community-address", "address"]:
        el = soup.select_one(selector)
        if el and el.text.strip() and len(el.text.strip()) < 200:
            return el.text.strip()

    return None


def extract_floor_plans_smart(soup, page_text, html):
    """
    Smart floor plan extraction that handles multiple HTML patterns.
    Designed to work with sites like frededina.com.
    """
    plans = []

    # Strategy 1: Parse structured floor plan blocks
    # Look for text blocks containing bedroom/bath/sqft/price patterns
    text_blocks = []

    # Find all divs/sections that might contain floor plan info
    for container in soup.find_all(["div", "section", "article", "li"]):
        text = container.get_text(separator=" ").strip()
        # Must mention bedrooms AND have a price
        if ("bedroom" in text.lower() or "bed" in text.lower() or "br" in text.lower()) and "$" in text:
            if 50 < len(text) < 2000:  # Reasonable size
                text_blocks.append({"text": text, "element": container})

    # Deduplicate by removing blocks that are subsets of others
    unique_blocks = []
    for block in sorted(text_blocks, key=lambda x: len(x["text"])):
        is_subset = False
        for existing in unique_blocks:
            if block["text"] in existing["text"]:
                is_subset = True
                break
        if not is_subset:
            unique_blocks.append(block)

    for block in unique_blocks:
        text = block["text"]
        plan = parse_floor_plan_text(text, block["element"])
        if plan and plan.get("bedrooms"):
            plans.append(plan)

    # Strategy 2: Regex on full page text if Strategy 1 found nothing
    if not plans:
        plans = parse_floor_plans_from_text(page_text)

    return plans


def parse_floor_plan_text(text, element=None):
    """Parse a text block to extract floor plan details."""
    plan = {
        "bedrooms": None,
        "bathrooms": None,
        "sqft": None,
        "units": [],
        "tour_3d": None,
        "plan_name": None
    }

    text_lower = text.lower()

    # Bedrooms
    bed_match = re.search(r'(\d+)\s*(?:bedroom|bed|br)', text_lower)
    if bed_match:
        plan["bedrooms"] = int(bed_match.group(1))

    # Bathrooms
    bath_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:bathroom|bath|ba)', text_lower)
    if bath_match:
        plan["bathrooms"] = float(bath_match.group(1))
        if plan["bathrooms"] == int(plan["bathrooms"]):
            plan["bathrooms"] = int(plan["bathrooms"])

    # Square footage - try multiple patterns
    sqft_patterns = [
        r'(?:total\s+(?:interior\s+)?(?:livable\s+)?sq\s*ft[:\s]*)([\d,]+)',
        r'([\d,]+)\s*(?:sq\s*ft|sqft|sf|square\s*feet)',
        r'(?:sq\s*ft|sqft)[:\s]*([\d,]+)',
    ]
    for pattern in sqft_patterns:
        sqft_match = re.search(pattern, text_lower)
        if sqft_match:
            plan["sqft"] = int(sqft_match.group(1).replace(",", ""))
            break

    # Available units with prices
    # Pattern: #115 available now, $2399/mo
    unit_pattern = re.findall(
        r'#(\w+)\s+available\s+([^,]+),\s*\$([\d,]+)/mo',
        text, re.IGNORECASE
    )
    for unit_num, avail_date, price in unit_pattern:
        plan["units"].append({
            "unit": f"#{unit_num}",
            "available": avail_date.strip(),
            "rent": int(price.replace(",", ""))
        })

    # If no specific units found, look for general price
    if not plan["units"]:
        price_matches = re.findall(r'\$([\d,]+)\s*/\s*mo', text)
        for p in price_matches:
            val = int(p.replace(",", ""))
            if 500 <= val <= 10000:
                plan["units"].append({"unit": "unknown", "available": "unknown", "rent": val})

        # Also try: $X,XXX without /mo
        if not plan["units"]:
            price_matches = re.findall(r'\$([\d,]+)', text)
            for p in price_matches:
                val = int(p.replace(",", ""))
                if 800 <= val <= 5000:
                    plan["units"].append({"unit": "unknown", "available": "unknown", "rent": val})

    # 3D tour link
    if element:
        for link in element.find_all("a", href=True):
            href = link["href"].lower()
            link_text = link.get_text().lower()
            if "3d" in href or "3d" in link_text or "tour" in link_text:
                plan["tour_3d"] = link["href"]
                break

    # Service fee
    fee_match = re.search(r'service\s+fee[:\s]*\$([\d,]+)', text_lower)
    if fee_match:
        plan["service_fee"] = int(fee_match.group(1).replace(",", ""))

    return plan


def parse_floor_plans_from_text(page_text):
    """Fallback: extract floor plans from raw page text using regex."""
    plans = []

    # Split text into chunks around bedroom mentions
    chunks = re.split(r'(?=\d+\s*(?:bedroom|bed|br))', page_text, flags=re.IGNORECASE)

    for chunk in chunks:
        if len(chunk) < 20 or len(chunk) > 2000:
            continue
        plan = parse_floor_plan_text(chunk)
        if plan and plan.get("bedrooms") and plan.get("units"):
            plans.append(plan)

    return plans


def classify_amenities(page_text_lower):
    """Match amenities from page text."""
    classified = []
    for key, keywords in AMENITY_KEYWORDS.items():
        if any(kw in page_text_lower for kw in keywords):
            classified.append(key)
    return list(set(classified))


def extract_tour(soup):
    """Find 3D tour links."""
    tour_patterns = ["matterport", "tour.realync", "3dtour", "virtual-tour",
                      "virtualtour", "my.tour", "3d-plan", "plan-3d"]

    for link in soup.find_all("a", href=True):
        href = link["href"].lower()
        link_text = link.get_text().lower()
        if any(p in href for p in tour_patterns) or "3d" in link_text:
            full_href = link["href"]
            if full_href.startswith("/"):
                # Relative URL - we'll return it as-is, frontend can handle
                pass
            return full_href

    for iframe in soup.find_all("iframe", src=True):
        if any(p in iframe["src"].lower() for p in tour_patterns):
            return iframe["src"]

    return None


# ============================================
# NEIGHBORHOOD DATA via OpenStreetMap
# ============================================

def geocode(address):
    """Convert address to coordinates."""
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
    """Distance between two points in miles."""
    R = 3959
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def overpass_query(lat, lon, radius, tags):
    """Query OpenStreetMap for nearby places."""
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
    """Fetch all neighborhood data."""
    results = {}

    # Restaurants
    restaurants = overpass_query(lat, lon, 2500, {"amenity": "restaurant"})
    time.sleep(1)
    cafes = overpass_query(lat, lon, 2500, {"amenity": "cafe"})
    time.sleep(1)
    results["restaurant_count"] = len(restaurants) + len(cafes)
    results["restaurants_nearby"] = (restaurants + cafes)[:15]

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

    results["nightlife_count"] = len(unique_nightlife)
    results["nightlife_nearby"] = unique_nightlife[:15]

    time.sleep(1)

    # Transit
    bus = overpass_query(lat, lon, 1000, {"highway": "bus_stop"})
    time.sleep(1)
    rail = overpass_query(lat, lon, 2000, {"railway": "station"})
    results["transit_count"] = len(bus) + len(rail)

    if len(bus) + len(rail) >= 5:
        results["transit_level"] = "nearby"
    elif len(bus) + len(rail) >= 2:
        results["transit_level"] = "some"
    else:
        results["transit_level"] = "none"

    time.sleep(1)

    # Schools
    schools = overpass_query(lat, lon, 3000, {"amenity": "school"})
    results["schools_nearby"] = schools[:10]
    results["school_count"] = len(schools)

    # Commute
    commute_miles = haversine_miles(
        lat, lon,
        USER_SETTINGS["commute_target"]["lat"],
        USER_SETTINGS["commute_target"]["lon"]
    )
    results["commute_minutes"] = round((commute_miles * 1.4 / 25) * 60)

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
    return min(100, density + 35)

def score_commute(drive_min, transit_level):
    if drive_min <= 10: drive = 70
    elif drive_min <= 20: drive = 55
    elif drive_min <= 30: drive = 40
    elif drive_min <= 45: drive = 25
    else: drive = 10
    transit_map = {"nearby": 30, "some": 15, "none": 0}
    return round(drive + transit_map.get(transit_level, 0))

def score_nightlife(count):
    density = min(50, round((count / 10) * 50))
    return min(100, density + 35)

def score_grocery(stores):
    if not stores:
        return 0
    nearby = [g for g in stores if g["distance_miles"] <= 3]
    unique = len(set(g["name"].lower() for g in nearby))
    variety = min(40, round((unique / 5) * 40))
    closest = min(g["distance_miles"] for g in stores)
    if closest <= 0.5: prox = 30
    elif closest <= 1: prox = 25
    elif closest <= 2: prox = 15
    elif closest <= 3: prox = 10
    else: prox = 0
    costco_list = [g for g in stores if "costco" in g["name"].lower()]
    if costco_list:
        cd = min(c["distance_miles"] for c in costco_list)
        if cd <= 3: costco = 30
        elif cd <= 5: costco = 20
        elif cd <= 10: costco = 10
        else: costco = 0
    else:
        costco = 0
    return round(variety + prox + costco)

def score_schools(count):
    base = min(70, round((count / 5) * 70))
    return min(100, base + 20)

def calculate_all_scores(apartment_data, neighborhood):
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
    scores["crime"] = 65
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

apartment_db = []


@app.route("/api/score", methods=["POST"])
def score_from_url():
    """Main endpoint: scrape URL, fetch neighborhood, return scores."""
    body = request.json
    url = body.get("url", "")

    result = {"status": "processing"}

    # Step 1: Scrape
    scraped = scrape_apartment(url) if url else {"scraped": False}

    if not scraped.get("scraped"):
        return jsonify({
            "status": "scrape_failed",
            "error": scraped.get("error", "Could not scrape"),
            "needs_manual": True
        })

    # Step 2: Filter to 2bd/2ba plans
    all_plans = scraped.get("floor_plans", [])
    target_beds = USER_SETTINGS["ideal_bedrooms"]
    target_baths = USER_SETTINGS["ideal_bathrooms"]

    matching_plans = [
        p for p in all_plans
        if p.get("bedrooms") == target_beds and p.get("bathrooms") == target_baths
    ]

    # If no exact match, show all plans
    if not matching_plans:
        matching_plans = all_plans

    # Step 3: Build response for each matching floor plan
    scored_plans = []

    for plan in matching_plans:
        # Get the best (lowest) rent from available units
        units = plan.get("units", [])
        rents = [u["rent"] for u in units if u.get("rent")]
        best_rent = min(rents) if rents else 0

        apartment = {
            "name": scraped.get("name") or "Unknown Apartment",
            "address": scraped.get("address") or "",
            "url": url,
            "rent": best_rent,
            "bedrooms": plan.get("bedrooms", target_beds),
            "bathrooms": plan.get("bathrooms", target_baths),
            "sqft": plan.get("sqft", 0),
            "amenities": scraped.get("amenities_classified", []),
            "tour_3d": plan.get("tour_3d") or scraped.get("tour_3d"),
            "units_available": units,
            "service_fee": plan.get("service_fee"),
            "plan_name": plan.get("plan_name")
        }

        # Step 4: Geocode + neighborhood (only for first plan, reuse for others)
        neighborhood = {}
        if scored_plans:
            # Reuse neighborhood data from first plan
            neighborhood = scored_plans[0].get("neighborhood_data", {})
            apartment["neighborhood_data"] = neighborhood
        else:
            address = apartment["address"]
            if address:
                coords = geocode(address)
                if coords:
                    apartment["lat"] = coords["lat"]
                    apartment["lon"] = coords["lon"]
                    neighborhood = fetch_neighborhood(coords["lat"], coords["lon"])
                    apartment["neighborhood_data"] = neighborhood

        # Step 5: Score
        scores = calculate_all_scores(apartment, neighborhood)
        apartment["scores"] = scores
        apartment["id"] = str(int(time.time() * 1000)) + str(len(scored_plans))

        scored_plans.append(apartment)

    # Store all plans
    apartment_db.extend(scored_plans)

    return jsonify({
        "status": "success",
        "apartments": scored_plans,
        "total_plans_found": len(all_plans),
        "matching_plans": len(matching_plans),
        "scrape_info": {
            "name": scraped.get("name"),
            "address": scraped.get("address"),
            "amenities_detected": scraped.get("amenities_classified", []),
            "tour_found": scraped.get("tour_3d") is not None,
            "all_plans_count": len(all_plans)
        }
    })


@app.route("/api/score-manual", methods=["POST"])
def score_manual():
    """Fallback for manual entry."""
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

    return jsonify({"status": "success", "apartment": apartment, "scores": scores})


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
    print("\n🏢 Apartment Scorer API running!")
    print("   http://localhost:5000")
    app.run(debug=True, port=5000)
