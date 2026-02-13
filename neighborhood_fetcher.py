# neighborhood_fetcher.py
# Phase 3: Auto-Fetch Neighborhood Data from Address

import time
import math
import json
from geopy.geocoders import Nominatim
from geopy.distance import geodesic

try:
    import overpy
    OVERPY_AVAILABLE = True
except ImportError:
    OVERPY_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


# ============================================
# GEOCODING - Convert Address to Coordinates
# ============================================

def geocode_address(address):
    """
    Convert a street address to latitude/longitude.
    Uses free Nominatim geocoder (OpenStreetMap).
    """
    geolocator = Nominatim(user_agent="apartment_scorer_app")
    try:
        location = geolocator.geocode(address, timeout=10)
        if location:
            print(f"📍 Found coordinates: {location.latitude}, {location.longitude}")
            return {
                "lat": location.latitude,
                "lon": location.longitude,
                "display_name": location.address
            }
        else:
            print(f"⚠️  Could not geocode address: {address}")
            return None
    except Exception as e:
        print(f"⚠️  Geocoding error: {e}")
        return None


# ============================================
# COMMUTE TARGET - Hopkins/Excelsior Blvd
# ============================================

COMMUTE_TARGET = {
    "name": "Excelsior Blvd, Hopkins, MN",
    "lat": 44.9258,
    "lon": -93.4083
}


def estimate_drive_minutes(origin_coords, destination=COMMUTE_TARGET):
    """
    Estimates drive time based on straight-line distance.
    Rough formula: 1 mile straight-line ≈ 2.5 min driving in metro area.
    (Will be replaced with real routing API later if needed)
    """
    origin = (origin_coords["lat"], origin_coords["lon"])
    dest = (destination["lat"], destination["lon"])

    straight_line_miles = geodesic(origin, dest).miles

    # Metro driving estimate: multiply straight line by 1.4 for road factor
    road_miles = straight_line_miles * 1.4
    # Assume average 25 mph in metro
    drive_minutes = (road_miles / 25) * 60

    return round(drive_minutes)


# ============================================
# OPENSTREETMAP QUERIES (Free!)
# ============================================

def query_osm_nearby(lat, lon, radius_meters, tags):
    """
    Query OpenStreetMap for nearby points of interest.
    tags = dict like {"amenity": "restaurant"}
    Returns list of places with name and distance.
    """
    if not OVERPY_AVAILABLE:
        print("⚠️  overpy not installed. Skipping OSM query.")
        return []

    api = overpy.Overpass()

    # Build tag filter
    tag_filters = ""
    for key, value in tags.items():
        if isinstance(value, list):
            for v in value:
                tag_filters += f'node["{key}"="{v}"](around:{radius_meters},{lat},{lon});'
        else:
            tag_filters += f'node["{key}"="{value}"](around:{radius_meters},{lat},{lon});'

    query = f"""
    [out:json][timeout:25];
    (
        {tag_filters}
    );
    out body;
    """

    try:
        result = api.query(query)
        places = []
        for node in result.nodes:
            name = node.tags.get("name", "Unnamed")
            distance_miles = geodesic(
                (lat, lon),
                (float(node.lat), float(node.lon))
            ).miles

            places.append({
                "name": name,
                "distance_miles": round(distance_miles, 2),
                "lat": float(node.lat),
                "lon": float(node.lon),
                "tags": dict(node.tags)
            })

        # Sort by distance
        places.sort(key=lambda x: x["distance_miles"])
        return places

    except Exception as e:
        print(f"⚠️  OSM query error: {e}")
        return []


# ============================================
# CATEGORY-SPECIFIC FETCHERS
# ============================================

def fetch_restaurants(lat, lon, radius=2500):
    """Fetch nearby restaurants (within ~1.5 miles)."""
    print("🍽️  Searching for restaurants...")
    places = query_osm_nearby(lat, lon, radius, {"amenity": "restaurant"})

    # Also grab cafes and fast food for a fuller picture
    cafes = query_osm_nearby(lat, lon, radius, {"amenity": "cafe"})
    time.sleep(1)  # Be nice to the free API

    all_dining = places + cafes
    all_dining.sort(key=lambda x: x["distance_miles"])

    print(f"   Found {len(all_dining)} dining options nearby")
    return all_dining


def fetch_grocery(lat, lon, radius=5000):
    """
    Fetch nearby grocery stores (within ~3 miles).
    Includes supermarkets + specific stores like Costco.
    """
    print("🛒 Searching for grocery stores...")
    
    # Get supermarkets
    supermarkets = query_osm_nearby(lat, lon, radius, {"shop": "supermarket"})
    time.sleep(1)

    # Also check for wholesale clubs (Costco, Sam's Club)
    wholesale = query_osm_nearby(lat, lon, 16000, {"shop": "wholesale"})  # 10 mile radius for Costco
    time.sleep(1)

    # Combine and deduplicate
    all_grocery = supermarkets.copy()
    
    # Add wholesale that aren't already in the list
    existing_names = {g["name"].lower() for g in all_grocery}
    for store in wholesale:
        if store["name"].lower() not in existing_names:
            all_grocery.append(store)

    all_grocery.sort(key=lambda x: x["distance_miles"])

    # Flag Costco specifically
    for store in all_grocery:
        if "costco" in store["name"].lower():
            print(f"   🎯 Costco found: {store['distance_miles']} miles away!")

    print(f"   Found {len(all_grocery)} grocery options nearby")
    return all_grocery


def fetch_nightlife(lat, lon, radius=3000):
    """Fetch nearby bars, nightclubs, entertainment."""
    print("🎶 Searching for nightlife...")

    bars = query_osm_nearby(lat, lon, radius, {"amenity": "bar"})
    time.sleep(1)

    nightclubs = query_osm_nearby(lat, lon, radius, {"amenity": "nightclub"})
    time.sleep(1)

    entertainment = query_osm_nearby(lat, lon, radius, {"leisure": "bowling_alley"})
    time.sleep(1)

    theatres = query_osm_nearby(lat, lon, radius, {"amenity": "theatre"})
    time.sleep(1)

    cinemas = query_osm_nearby(lat, lon, radius, {"amenity": "cinema"})

    all_nightlife = bars + nightclubs + entertainment + theatres + cinemas

    # Deduplicate by name
    seen = set()
    unique = []
    for place in all_nightlife:
        if place["name"].lower() not in seen:
            seen.add(place["name"].lower())
            unique.append(place)

    unique.sort(key=lambda x: x["distance_miles"])
    print(f"   Found {len(unique)} nightlife/entertainment options nearby")
    return unique


def fetch_transit(lat, lon, radius=1000):
    """Fetch nearby transit stops (within ~0.6 miles)."""
    print("🚌 Searching for transit...")

    bus_stops = query_osm_nearby(lat, lon, radius, {"highway": "bus_stop"})
    time.sleep(1)

    rail = query_osm_nearby(lat, lon, 2000, {"railway": "station"})

    all_transit = bus_stops + rail
    all_transit.sort(key=lambda x: x["distance_miles"])

    print(f"   Found {len(all_transit)} transit stops nearby")
    return all_transit


def fetch_schools(lat, lon, radius=3000):
    """
    Fetch nearby schools.
    Note: OSM doesn't have ratings, so we return school names
    and you'd cross-reference with GreatSchools manually or via API.
    For now, we estimate based on count and proximity.
    """
    print("🏫 Searching for schools...")

    schools = query_osm_nearby(lat, lon, radius, {"amenity": "school"})

    print(f"   Found {len(schools)} schools nearby")
    return schools


def fetch_crime_estimate(lat, lon):
    """
    Attempts to get crime data from Minneapolis Open Data.
    Falls back to a neutral estimate if unavailable.
    """
    print("🔒 Checking crime data...")

    if not REQUESTS_AVAILABLE:
        print("   ⚠️  requests library not available. Using neutral estimate.")
        return {"crime_index": 50, "source": "estimate"}

    # Minneapolis Open Data API (SODA API - free)
    # Searches for incidents within ~0.5 miles in the last year
    try:
        # Convert to approximate bounding box (0.5 mile ≈ 0.007 degrees)
        offset = 0.007
        min_lat = lat - offset
        max_lat = lat + offset
        min_lon = lon - offset
        max_lon = lon + offset

        url = (
            "https://opendata.minneapolismn.gov/resource/a]resource.json"
            f"?$where=latitude>{min_lat} AND latitude<{max_lat} "
            f"AND longitude>{min_lon} AND longitude<{max_lon}"
            f"&$limit=1000"
        )

        # This is a placeholder URL - the actual Minneapolis open data
        # endpoint would need to be configured with the correct dataset ID
        print("   ⚠️  Crime API needs configuration for Minneapolis dataset.")
        print("   Using neighborhood-based estimate for now.")
        
        return {"crime_index": 50, "source": "estimate"}

    except Exception as e:
        print(f"   ⚠️  Crime data error: {e}. Using neutral estimate.")
        return {"crime_index": 50, "source": "estimate"}


# ============================================
# MASTER FETCH FUNCTION
# ============================================

def fetch_all_neighborhood_data(address):
    """
    Main entry point. Takes an address and returns all
    neighborhood data needed for scoring.
    """
    print(f"\n{'='*50}")
    print(f"  🏘️  NEIGHBORHOOD ANALYSIS")
    print(f"  📍 {address}")
    print(f"{'='*50}\n")

    # Step 1: Geocode the address
    coords = geocode_address(address)
    if not coords:
        print("❌ Could not find address. Please check and try again.")
        return None

    lat = coords["lat"]
    lon = coords["lon"]

    print(f"\n🔍 Scanning neighborhood...\n")

    # Step 2: Fetch all data (with pauses to be nice to free APIs)
    restaurants = fetch_restaurants(lat, lon)
    time.sleep(2)

    grocery = fetch_grocery(lat, lon)
    time.sleep(2)

    nightlife = fetch_nightlife(lat, lon)
    time.sleep(2)

    transit = fetch_transit(lat, lon)
    time.sleep(2)

    schools = fetch_schools(lat, lon)
    time.sleep(1)

    crime = fetch_crime_estimate(lat, lon)

    # Step 3: Calculate commute
    drive_min = estimate_drive_minutes(coords)
    print(f"\n🚗 Estimated commute to Hopkins: {drive_min} minutes")

    # Step 4: Determine transit level
    if len(transit) >= 5:
        transit_level = "nearby"
    elif len(transit) >= 2:
        transit_level = "some"
    else:
        transit_level = "none"

    # Step 5: Build the neighborhood data dict for scoring
    neighborhood_data = {
        "coordinates": coords,
        "drive_minutes": drive_min,
        "transit_available": transit_level,
        "transit_stops": transit,

        "restaurant_count": len(restaurants),
        "restaurant_avg_rating": None,  # OSM doesn't have ratings
        "restaurants": restaurants[:20],  # Top 20 closest

        "grocery_stores": [
            {
                "name": g["name"],
                "distance_miles": g["distance_miles"],
                "type": "wholesale" if "costco" in g["name"].lower() 
                        or "sam" in g["name"].lower() else "grocery"
            }
            for g in grocery
        ],

        "nightlife_count": len(nightlife),
        "nightlife_avg_rating": None,  # OSM doesn't have ratings
        "nightlife": nightlife[:20],

        "school_ratings": [],  # Will need GreatSchools API or manual input
        "schools": schools[:10],

        "crime_index": crime["crime_index"],
        "crime_source": crime["source"]
    }

    # Step 6: Print summary
    print(f"\n{'='*50}")
    print(f"  📊 NEIGHBORHOOD SUMMARY")
    print(f"{'='*50}")
    print(f"  🚗 Commute to Hopkins: {drive_min} min")
    print(f"  🚌 Transit: {transit_level} ({len(transit)} stops)")
    print(f"  🍽️  Restaurants: {len(restaurants)} nearby")
    print(f"  🛒 Grocery: {len(grocery)} stores")

    costco_list = [g for g in grocery if "costco" in g["name"].lower()]
    if costco_list:
        print(f"  🎯 Nearest Costco: {costco_list[0]['distance_miles']} mi")
    else:
        print(f"  🎯 Costco: None found within 10 miles")

    print(f"  🎶 Nightlife: {len(nightlife)} venues")
    print(f"  🏫 Schools: {len(schools)} nearby")
    print(f"  🔒 Crime index: {crime['crime_index']}/100")
    print(f"{'='*50}")

    return neighborhood_data


def save_neighborhood_data(address, data, filename="neighborhoods.json"):
    """Cache neighborhood data so we don't re-fetch."""
    try:
        with open(filename, "r") as f:
            cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        cache = {}

    cache[address] = data

    with open(filename, "w") as f:
        json.dump(cache, f, indent=2)

    print(f"💾 Neighborhood data cached for: {address}")


# ============================================
# SCHOOL RATING MANUAL INPUT
# ============================================

def input_school_ratings(schools):
    """
    Since OSM doesn't have school ratings, this lets you
    manually enter GreatSchools ratings for nearby schools.
    Go to greatschools.org, search the school, enter rating.
    """
    print("\n🏫 SCHOOL RATINGS")
    print("   Visit greatschools.org to look up each school's rating (1-10)")
    print("   Press Enter to skip any school.\n")

    ratings = []
    for school in schools[:5]:  # Top 5 closest schools
        rating = input(f"   {school['name']} ({school['distance_miles']} mi) - Rating (1-10): ").strip()
        if rating:
            try:
                r = int(rating)
                if 1 <= r <= 10:
                    ratings.append(r)
            except ValueError:
                pass

    return ratings


# ============================================
# EXAMPLE USAGE
# ============================================

if __name__ == "__main__":
    print("\n🏢 APARTMENT SCORER - Neighborhood Analysis")
    print("=" * 50)

    address = input("\nEnter apartment address: ").strip()

    if address:
        data = fetch_all_neighborhood_data(address)

        if data:
            # Prompt for school ratings
            if data["schools"]:
                ratings = input_school_ratings(data["schools"])
                data["school_ratings"] = ratings

            save_neighborhood_data(address, data)

            print("\n✅ Neighborhood data ready for scoring!")
    else:
        print("No address entered.")
