# apartment_scraper.py
# Phase 2: Web Scraper + Manual Input Fallback

import requests
from bs4 import BeautifulSoup
import json
import re


# ============================================
# PLAN A: AUTO-SCRAPE FROM URL
# ============================================

def scrape_apartments_com(url):
    """
    Attempts to scrape apartment data from an apartments.com listing.
    Returns apartment dict if successful, None if blocked.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code != 200:
            print(f"⚠️  Website returned status {response.status_code}. Falling back to manual input.")
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        # Extract apartment data from page
        apartment = {
            "url": url,
            "name": extract_name(soup),
            "address": extract_address(soup),
            "rent_range": extract_rent(soup),
            "floor_plans": extract_floor_plans(soup),
            "amenities": extract_amenities(soup),
            "tour_3d": extract_3d_tour(soup),
            "photos": extract_photos(soup)
        }

        # Check if we actually got useful data
        if not apartment["name"] and not apartment["address"]:
            print("⚠️  Couldn't extract data from page. Falling back to manual input.")
            return None

        return apartment

    except requests.exceptions.RequestException as e:
        print(f"⚠️  Connection error: {e}. Falling back to manual input.")
        return None


def extract_name(soup):
    """Extract apartment complex name."""
    # Try common selectors for apartment name
    selectors = [
        "h1.propertyName",
        "h1[data-testid='property-name']",
        "h1",
        ".community-name"
    ]
    for selector in selectors:
        el = soup.select_one(selector)
        if el and el.text.strip():
            return el.text.strip()
    return None


def extract_address(soup):
    """Extract apartment address."""
    selectors = [
        ".propertyAddress",
        "[data-testid='property-address']",
        ".community-address",
        "span.delivery-address"
    ]
    for selector in selectors:
        el = soup.select_one(selector)
        if el and el.text.strip():
            return el.text.strip()
    return None


def extract_rent(soup):
    """Extract rent prices."""
    prices = []
    # Look for price patterns like $1,200 - $2,500
    price_pattern = re.compile(r'\$[\d,]+')
    
    selectors = [
        ".rentRollup",
        ".price-range",
        "[data-testid='price']",
        ".rent-range"
    ]
    for selector in selectors:
        elements = soup.select(selector)
        for el in elements:
            found = price_pattern.findall(el.text)
            prices.extend(found)
    
    if not prices:
        # Broader search
        text = soup.get_text()
        prices = price_pattern.findall(text)[:10]  # Limit to first 10

    return list(set(prices))


def extract_floor_plans(soup):
    """
    Extract floor plan details.
    Filters to show only 2bd/2ba plans.
    """
    plans = []

    # Look for floor plan containers
    selectors = [
        ".pricingGridItem",
        ".floor-plan-card",
        "[data-testid='floor-plan']",
        ".floorplan"
    ]

    for selector in selectors:
        elements = soup.select(selector)
        for el in elements:
            text = el.get_text(separator=" ").lower()
            plan = {
                "raw_text": el.get_text(separator=" ").strip()[:200],
                "beds": None,
                "baths": None,
                "sqft": None,
                "rent": None
            }

            # Parse beds
            bed_match = re.search(r'(\d+)\s*(?:bed|br|bedroom)', text)
            if bed_match:
                plan["beds"] = int(bed_match.group(1))

            # Parse baths
            bath_match = re.search(r'(\d+)\s*(?:bath|ba|bathroom)', text)
            if bath_match:
                plan["baths"] = int(bath_match.group(1))

            # Parse sqft
            sqft_match = re.search(r'([\d,]+)\s*(?:sq\s*ft|sqft|sf)', text)
            if sqft_match:
                plan["sqft"] = int(sqft_match.group(1).replace(",", ""))

            # Parse rent
            rent_match = re.search(r'\$([\d,]+)', text)
            if rent_match:
                plan["rent"] = int(rent_match.group(1).replace(",", ""))

            plans.append(plan)

    return plans


def filter_floor_plans(plans, target_beds=2, target_baths=2):
    """Filter floor plans to only show matching layouts."""
    matching = []
    for plan in plans:
        if plan["beds"] == target_beds and plan["baths"] == target_baths:
            matching.append(plan)
    
    if matching:
        return matching
    else:
        print(f"⚠️  No {target_beds}bd/{target_baths}ba plans found. Showing all plans.")
        return plans


def extract_amenities(soup):
    """Extract amenity list."""
    amenities = []

    selectors = [
        ".amenity",
        ".amenityCard",
        "[data-testid='amenity']",
        ".spec li",
        ".propertyFeatures li"
    ]

    for selector in selectors:
        elements = soup.select(selector)
        for el in elements:
            text = el.get_text(separator=" ").strip().lower()
            if text and len(text) < 100:
                amenities.append(text)

    return list(set(amenities))


def classify_amenities(raw_amenities):
    """
    Takes raw amenity strings and classifies them into
    our system's necessity/nice-to-have categories.
    """
    classified = []

    keyword_map = {
        "covered_parking": ["covered parking", "garage", "indoor parking", "heated parking"],
        "dishwasher": ["dishwasher"],
        "in_unit_laundry": ["in-unit laundry", "in unit laundry", "washer/dryer", 
                            "washer and dryer", "in-home laundry", "w/d in unit"],
        "ac": ["air conditioning", "a/c", "central air", "ac", "climate control"],
        "pool": ["pool", "swimming"],
        "sauna_hot_tub": ["sauna", "hot tub", "spa", "steam room"],
        "gym": ["gym", "fitness", "exercise", "workout"],
        "package_lockers": ["package", "parcel", "locker", "mailroom"]
    }

    for amenity_key, keywords in keyword_map.items():
        for raw in raw_amenities:
            if any(kw in raw.lower() for kw in keywords):
                classified.append(amenity_key)
                break

    return list(set(classified))


def extract_3d_tour(soup):
    """Extract 3D tour link if available."""
    # Look for Matterport or other tour links
    tour_patterns = [
        "matterport.com",
        "my.matterport",
        "tour.realync",
        "3dtour",
        "virtual-tour",
        "virtualtour"
    ]

    for link in soup.find_all("a", href=True):
        href = link["href"].lower()
        if any(pattern in href for pattern in tour_patterns):
            return link["href"]

    # Check iframes too
    for iframe in soup.find_all("iframe", src=True):
        src = iframe["src"].lower()
        if any(pattern in src for pattern in tour_patterns):
            return iframe["src"]

    return None


def extract_photos(soup):
    """Extract photo URLs."""
    photos = []
    for img in soup.find_all("img", src=True):
        src = img["src"]
        if any(kw in src.lower() for kw in ["photo", "image", "property", "unit", "apartment"]):
            photos.append(src)
    return photos[:20]  # Cap at 20 photos


# ============================================
# PLAN B: MANUAL INPUT FALLBACK
# ============================================

def manual_input():
    """
    Interactive form for manually entering apartment data
    when scraping doesn't work.
    """
    print("\n" + "=" * 50)
    print("  📝 MANUAL APARTMENT ENTRY")
    print("=" * 50)

    apartment = {}
    apartment["name"] = input("\nApartment name: ").strip()
    apartment["address"] = input("Full address: ").strip()
    apartment["url"] = input("Listing URL (optional): ").strip() or None

    # Rent
    while True:
        try:
            apartment["rent"] = int(input("Monthly rent ($): ").strip().replace("$", "").replace(",", ""))
            break
        except ValueError:
            print("  Please enter a number (e.g., 2200)")

    # Rooms
    while True:
        try:
            apartment["bedrooms"] = int(input("Bedrooms: ").strip())
            apartment["bathrooms"] = int(input("Bathrooms: ").strip())
            apartment["sqft"] = int(input("Square footage: ").strip().replace(",", ""))
            break
        except ValueError:
            print("  Please enter numbers only")

    # Amenities checklist
    print("\n  Check amenities (y/n):")
    all_amenities = {
        "covered_parking": "Covered/garage parking",
        "dishwasher": "Dishwasher",
        "in_unit_laundry": "In-unit laundry (washer/dryer)",
        "ac": "Air conditioning",
        "pool": "Pool",
        "sauna_hot_tub": "Sauna / Hot tub",
        "gym": "Gym / Fitness center",
        "package_lockers": "Package lockers"
    }

    apartment["amenities"] = []
    for key, label in all_amenities.items():
        answer = input(f"  {label}? (y/n): ").strip().lower()
        if answer in ["y", "yes"]:
            apartment["amenities"].append(key)

    # 3D Tour
    apartment["tour_3d"] = input("\n3D tour link (optional): ").strip() or None

    return apartment


# ============================================
# MAIN SCRAPER FUNCTION
# ============================================

def get_apartment_data(url=None):
    """
    Main entry point. Pass a URL to auto-scrape,
    or call with no URL for manual input.
    Returns a clean apartment dict ready for scoring.
    """
    apartment = None

    if url:
        print(f"\n🔍 Attempting to scrape: {url}")
        raw_data = scrape_apartments_com(url)

        if raw_data:
            print(f"✅ Successfully scraped: {raw_data['name']}")

            # Classify amenities
            classified = classify_amenities(raw_data.get("amenities", []))

            # Filter floor plans to 2bd/2ba
            plans = filter_floor_plans(raw_data.get("floor_plans", []))

            # Build clean apartment dict
            apartment = {
                "name": raw_data["name"],
                "address": raw_data["address"],
                "url": url,
                "amenities": classified,
                "tour_3d": raw_data.get("tour_3d"),
                "floor_plans": plans
            }

            # Try to get rent from filtered floor plans
            if plans and plans[0].get("rent"):
                apartment["rent"] = plans[0]["rent"]
                apartment["bedrooms"] = plans[0].get("beds", 2)
                apartment["bathrooms"] = plans[0].get("baths", 2)
                apartment["sqft"] = plans[0].get("sqft", 0)
            else:
                print("\n⚠️  Couldn't auto-detect rent/rooms. Please fill in:")
                try:
                    apartment["rent"] = int(input("  Monthly rent ($): ").strip().replace("$", "").replace(",", ""))
                    apartment["bedrooms"] = int(input("  Bedrooms: ").strip())
                    apartment["bathrooms"] = int(input("  Bathrooms: ").strip())
                    apartment["sqft"] = int(input("  Square footage: ").strip().replace(",", ""))
                except ValueError:
                    print("  Invalid input, using defaults")
                    apartment["rent"] = 0
                    apartment["bedrooms"] = 2
                    apartment["bathrooms"] = 2
                    apartment["sqft"] = 0

            # Show what we found
            print(f"\n📋 Scraped Data:")
            print(f"   Name: {apartment['name']}")
            print(f"   Address: {apartment['address']}")
            print(f"   Rent: ${apartment.get('rent', 'Unknown')}")
            print(f"   Layout: {apartment.get('bedrooms')}bd/{apartment.get('bathrooms')}ba")
            print(f"   Sqft: {apartment.get('sqft', 'Unknown')}")
            print(f"   Amenities: {', '.join(apartment['amenities'])}")
            print(f"   3D Tour: {'Yes' if apartment.get('tour_3d') else 'No'}")
            print(f"   Floor Plans Found: {len(plans)}")

            return apartment

    # Fallback to manual input
    print("\n📝 Switching to manual input...")
    return manual_input()


# ============================================
# SAVE/LOAD APARTMENTS
# ============================================

def save_apartment(apartment, filename="apartments.json"):
    """Save apartment to JSON file."""
    try:
        with open(filename, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = []

    data.append(apartment)

    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\n💾 Saved! You now have {len(data)} apartment(s) on file.")


def load_apartments(filename="apartments.json"):
    """Load all saved apartments."""
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


# ============================================
# EXAMPLE USAGE
# ============================================

if __name__ == "__main__":
    print("\n🏢 APARTMENT SCORER - Data Entry")
    print("=" * 50)

    choice = input("\nPaste an apartment URL (or press Enter for manual input): ").strip()

    if choice:
        apartment = get_apartment_data(url=choice)
    else:
        apartment = get_apartment_data()

    if apartment:
        save = input("\n💾 Save this apartment? (y/n): ").strip().lower()
        if save in ["y", "yes"]:
            save_apartment(apartment)
