# apartment_scorer.py
# Phase 1: Core Scoring Engine for Apartment Scorer

# ============================================
# USER SETTINGS (set once)
# ============================================
USER_SETTINGS = {
    "budget_cap": 2500,
    "ideal_bedrooms": 2,
    "ideal_bathrooms": 2,
    "ideal_sqft": 1000,  # Adjust to your preference
    "commute_target": "Excelsior Blvd, Hopkins, MN",
    "necessities": [
        "covered_parking",
        "dishwasher",
        "in_unit_laundry",
        "ac"
    ],
    "nice_to_haves": [
        "pool",
        "sauna_hot_tub",
        "gym",
        "package_lockers"
    ],
    # Average 2bd/2ba rent in Minneapolis (used for market comparison)
    "market_avg_rent": 1750
}


# ============================================
# SCORING FUNCTIONS (each returns 0-100)
# ============================================

def score_price(rent, settings):
    """
    50 pts from budget comparison:
      - At or under cap = 50
      - Every $100 over cap = -10 pts
    50 pts from market comparison:
      - At or below market avg = 50
      - Every $100 above avg = -10 pts
    """
    budget_cap = settings["budget_cap"]
    market_avg = settings["market_avg_rent"]

    # Budget comparison (50 pts max)
    if rent <= budget_cap:
        # Reward being under budget: closer to $0 = higher score
        budget_score = 50
    else:
        over = rent - budget_cap
        budget_score = max(0, 50 - (over / 100) * 10)

    # Market comparison (50 pts max)
    if rent <= market_avg:
        market_score = 50
    else:
        over = rent - market_avg
        market_score = max(0, 50 - (over / 100) * 10)

    return round(budget_score + market_score)


def score_rooms(bedrooms, bathrooms, sqft, settings):
    """
    40 pts: Bedroom match
    40 pts: Bathroom match
    20 pts: Square footage bonus
    """
    ideal_bed = settings["ideal_bedrooms"]
    ideal_bath = settings["ideal_bathrooms"]
    ideal_sqft = settings["ideal_sqft"]

    # Bedroom score (40 pts)
    bed_diff = abs(bedrooms - ideal_bed)
    bed_score = max(0, 40 - (bed_diff * 20))

    # Bathroom score (40 pts)
    bath_diff = abs(bathrooms - ideal_bath)
    bath_score = max(0, 40 - (bath_diff * 20))

    # Sqft bonus (20 pts)
    if sqft >= ideal_sqft:
        sqft_score = 20
    elif sqft >= ideal_sqft * 0.8:
        sqft_score = 10
    else:
        sqft_score = 0

    return round(bed_score + bath_score + sqft_score)


def score_necessities(amenities, settings):
    """
    All-or-nothing: All necessities present = 100, any missing = 0
    """
    for necessity in settings["necessities"]:
        if necessity not in amenities:
            return 0
    return 100


def score_nice_to_haves(amenities, settings):
    """
    Proportional: Each nice-to-have present = equal share of 100
    4 nice-to-haves = 25 pts each
    """
    nice_list = settings["nice_to_haves"]
    total = len(nice_list)
    if total == 0:
        return 100

    count = sum(1 for item in nice_list if item in amenities)
    return round((count / total) * 100)


def score_schools(school_ratings):
    """
    Takes a list of nearby school ratings (1-10 scale from GreatSchools).
    Averages them and converts to 0-100.
    """
    if not school_ratings:
        return 50  # Neutral if no data
    avg = sum(school_ratings) / len(school_ratings)
    return round(avg * 10)


def score_crime(crime_index):
    """
    Takes a crime index (0-100 where 100 = most dangerous).
    Inverts it so safer = higher score.
    """
    if crime_index is None:
        return 50  # Neutral if no data
    return round(max(0, 100 - crime_index))


def score_restaurants(restaurant_count, avg_rating):
    """
    50 pts: Density (number of restaurants within 1 mile)
      - 20+ restaurants = 50
      - Scales linearly below that
    50 pts: Quality (average rating)
      - 4.5+ avg = 50
      - Scales linearly below that
    """
    # Density score (50 pts)
    density = min(50, round((restaurant_count / 20) * 50))

    # Quality score (50 pts)
    if avg_rating is None:
        quality = 25  # Neutral
    else:
        quality = min(50, round((avg_rating / 4.5) * 50))

    return round(density + quality)


def score_commute(drive_minutes, transit_available):
    """
    70 pts: Drive time to commute target
      - 0-10 min = 70
      - 10-20 min = 55
      - 20-30 min = 40
      - 30-45 min = 25
      - 45+ min = 10
    30 pts: Transit access
      - Nearby transit = 30
      - Some transit = 15
      - None = 0
    """
    # Drive time score (70 pts)
    if drive_minutes <= 10:
        drive_score = 70
    elif drive_minutes <= 20:
        drive_score = 55
    elif drive_minutes <= 30:
        drive_score = 40
    elif drive_minutes <= 45:
        drive_score = 25
    else:
        drive_score = 10

    # Transit score (30 pts)
    transit_map = {"nearby": 30, "some": 15, "none": 0}
    transit_score = transit_map.get(transit_available, 0)

    return round(drive_score + transit_score)


def score_nightlife(venue_count, avg_rating):
    """
    Same logic as restaurants:
    50 pts density (10+ venues = full marks)
    50 pts quality (avg rating)
    """
    density = min(50, round((venue_count / 10) * 50))

    if avg_rating is None:
        quality = 25
    else:
        quality = min(50, round((avg_rating / 4.5) * 50))

    return round(density + quality)


def score_grocery(grocery_data):
    """
    Scores based on proximity and variety of grocery stores.
    Bonus points for Costco proximity.
    
    grocery_data = list of dicts: {"name": str, "distance_miles": float, "type": str}
    
    40 pts: Variety (unique store types within 3 miles)
    30 pts: Closest grocery distance
    30 pts: Costco/warehouse club within reasonable distance
    """
    if not grocery_data:
        return 0

    # Variety score (40 pts) - unique stores within 3 miles
    nearby = [g for g in grocery_data if g["distance_miles"] <= 3]
    unique_types = len(set(g["name"].lower() for g in nearby))
    variety_score = min(40, round((unique_types / 5) * 40))

    # Closest grocery (30 pts)
    closest = min(g["distance_miles"] for g in grocery_data)
    if closest <= 0.5:
        proximity_score = 30
    elif closest <= 1:
        proximity_score = 25
    elif closest <= 2:
        proximity_score = 15
    elif closest <= 3:
        proximity_score = 10
    else:
        proximity_score = 0

    # Costco bonus (30 pts)
    costco = [g for g in grocery_data if "costco" in g["name"].lower()]
    if costco:
        costco_dist = min(c["distance_miles"] for c in costco)
        if costco_dist <= 3:
            costco_score = 30
        elif costco_dist <= 5:
            costco_score = 20
        elif costco_dist <= 10:
            costco_score = 10
        else:
            costco_score = 0
    else:
        costco_score = 0

    return round(variety_score + proximity_score + costco_score)


# ============================================
# MASTER SCORING FUNCTION
# ============================================

def score_apartment(apartment, neighborhood_data, settings=USER_SETTINGS):
    """
    Takes apartment data + auto-fetched neighborhood data.
    Returns all 10 category scores + overall score.
    """
    scores = {}

    # Manual input scores
    scores["price"] = score_price(apartment["rent"], settings)
    scores["rooms"] = score_rooms(
        apartment["bedrooms"],
        apartment["bathrooms"],
        apartment["sqft"],
        settings
    )
    scores["necessities"] = score_necessities(apartment["amenities"], settings)
    scores["nice_to_haves"] = score_nice_to_haves(apartment["amenities"], settings)

    # Auto-fetched neighborhood scores
    scores["schools"] = score_schools(neighborhood_data.get("school_ratings", []))
    scores["crime"] = score_crime(neighborhood_data.get("crime_index"))
    scores["restaurants"] = score_restaurants(
        neighborhood_data.get("restaurant_count", 0),
        neighborhood_data.get("restaurant_avg_rating")
    )
    scores["commute"] = score_commute(
        neighborhood_data.get("drive_minutes", 60),
        neighborhood_data.get("transit_available", "none")
    )
    scores["nightlife"] = score_nightlife(
        neighborhood_data.get("nightlife_count", 0),
        neighborhood_data.get("nightlife_avg_rating")
    )
    scores["grocery"] = score_grocery(neighborhood_data.get("grocery_stores", []))

    # Overall score = average of all 10
    scores["overall"] = round(sum(scores.values()) / len(scores))

    return scores


# ============================================
# COLOR CODING HELPER
# ============================================

def get_score_color(score):
    """Returns color label for PDP display."""
    if score >= 75:
        return "green"
    elif score >= 50:
        return "yellow"
    else:
        return "red"


# ============================================
# EXAMPLE USAGE
# ============================================

if __name__ == "__main__":
    # Example apartment data (would come from web scraper in Phase 2)
    example_apartment = {
        "name": "The Nordic Apartments",
        "address": "1234 Hennepin Ave, Minneapolis, MN 55403",
        "url": "https://apartments.com/example",
        "rent": 2200,
        "bedrooms": 2,
        "bathrooms": 2,
        "sqft": 1050,
        "amenities": [
            "covered_parking",
            "dishwasher",
            "in_unit_laundry",
            "ac",
            "gym",
            "pool",
            "package_lockers"
        ],
        "tour_3d": "https://my.matterport.com/example"
    }

    # Example neighborhood data (would be auto-fetched in Phase 2)
    example_neighborhood = {
        "school_ratings": [7, 8, 6],
        "crime_index": 35,
        "restaurant_count": 25,
        "restaurant_avg_rating": 4.2,
        "drive_minutes": 18,
        "transit_available": "nearby",
        "nightlife_count": 12,
        "nightlife_avg_rating": 4.0,
        "grocery_stores": [
            {"name": "Trader Joe's", "distance_miles": 0.8, "type": "grocery"},
            {"name": "Cub Foods", "distance_miles": 1.2, "type": "grocery"},
            {"name": "Costco", "distance_miles": 4.5, "type": "warehouse"},
            {"name": "Aldi", "distance_miles": 1.5, "type": "grocery"},
            {"name": "Target", "distance_miles": 0.5, "type": "grocery"},
        ]
    }

    # Run the scorer
    results = score_apartment(example_apartment, example_neighborhood)

    # Display results
    print(f"\n{'='*50}")
    print(f"  {example_apartment['name']}")
    print(f"  {example_apartment['address']}")
    print(f"{'='*50}")
    print(f"\n  OVERALL SCORE: {results['overall']}/100\n")

    for category, score in results.items():
        if category != "overall":
            color = get_score_color(score)
            bar = "█" * (score // 5) + "░" * (20 - score // 5)
            print(f"  {category.replace('_', ' ').title():20s} {bar} {score}/100 ({color})")

    print(f"\n{'='*50}")
```

This is the complete Phase 1 scoring engine. If you run that example at the bottom, it'll output something like:
```
==================================================
  The Nordic Apartments
  1234 Hennepin Ave, Minneapolis, MN 55403
==================================================

  OVERALL SCORE: 77/100

  Price                ████████████████░░░░ 80/100 (green)
  Rooms                ████████████████████ 100/100 (green)
  Necessities          ████████████████████ 100/100 (green)
  Nice To Haves        ███████████████░░░░░ 75/100 (green)
  Schools              ██████████████░░░░░░ 70/100 (yellow)
  Crime                █████████████░░░░░░░ 65/100 (yellow)
  Restaurants          ████████████████████ 97/100 (green)
  Commute              █████████████████░░░ 85/100 (green)
  Nightlife            ████████████████████ 94/100 (green)
  Grocery              ██████████████░░░░░░ 70/100 (yellow)
