#!/usr/bin/env python3
"""
CARDEX Seed Script — Generates realistic European vehicle listings
and injects them through the Gateway → Pipeline → PostgreSQL → MeiliSearch pipeline.
"""
import hashlib
import hmac as hmac_mod
import json
import random
import string
import sys
import time
import urllib.request

GATEWAY_URL = "http://localhost:8090/v1/ingest"
HMAC_SECRET = b"dev_pipeline_hmac_secret_change_in_prod"

# ── Vehicle catalog by country ──────────────────────────────────────────────

PLATFORMS = {
    "DE": [
        ("autoscout24_de", "https://www.autoscout24.de/angebote/"),
        ("mobile_de", "https://suchen.mobile.de/fahrzeuge/details/"),
    ],
    "ES": [
        ("autoscout24_es", "https://www.autoscout24.es/ofertas/"),
        ("coches_net", "https://www.coches.net/"),
    ],
    "FR": [
        ("autoscout24_fr", "https://www.autoscout24.fr/offres/"),
        ("leboncoin", "https://www.leboncoin.fr/voitures/"),
    ],
    "NL": [
        ("autoscout24_nl", "https://www.autoscout24.nl/aanbod/"),
        ("marktplaats", "https://www.marktplaats.nl/auto/"),
    ],
    "BE": [
        ("autoscout24_be", "https://www.autoscout24.be/nl/aanbod/"),
        ("2dehands", "https://www.2dehands.be/auto/"),
    ],
    "CH": [
        ("autoscout24_ch", "https://www.autoscout24.ch/de/angebote/"),
        ("comparis", "https://www.comparis.ch/auto/"),
    ],
}

CITIES = {
    "DE": [
        ("Berlin", 52.52, 13.405), ("Munich", 48.137, 11.576), ("Hamburg", 53.551, 9.994),
        ("Frankfurt", 50.110, 8.682), ("Cologne", 50.938, 6.960), ("Stuttgart", 48.776, 9.183),
        ("Dusseldorf", 51.228, 6.773), ("Dortmund", 51.514, 7.468), ("Leipzig", 51.340, 12.375),
        ("Hannover", 52.376, 9.732), ("Dresden", 51.051, 13.738), ("Nuremberg", 49.454, 11.078),
    ],
    "ES": [
        ("Madrid", 40.417, -3.704), ("Barcelona", 41.389, 2.159), ("Valencia", 39.470, -0.377),
        ("Seville", 37.389, -5.984), ("Malaga", 36.721, -4.421), ("Bilbao", 43.263, -2.935),
        ("Zaragoza", 41.649, -0.887), ("Alicante", 38.346, -0.490), ("Palma", 39.570, 2.650),
    ],
    "FR": [
        ("Paris", 48.856, 2.352), ("Lyon", 45.764, 4.836), ("Marseille", 43.297, 5.381),
        ("Toulouse", 43.605, 1.444), ("Bordeaux", 44.838, -0.579), ("Lille", 50.630, 3.057),
        ("Nice", 43.710, 7.262), ("Nantes", 47.218, -1.554), ("Strasbourg", 48.573, 7.752),
    ],
    "NL": [
        ("Amsterdam", 52.370, 4.895), ("Rotterdam", 51.925, 4.479), ("The Hague", 52.079, 4.309),
        ("Utrecht", 52.091, 5.122), ("Eindhoven", 51.442, 5.470), ("Groningen", 53.219, 6.567),
    ],
    "BE": [
        ("Brussels", 50.850, 4.352), ("Antwerp", 51.220, 4.402), ("Ghent", 51.054, 3.725),
        ("Liege", 50.633, 5.568), ("Bruges", 51.209, 3.225), ("Leuven", 50.879, 4.701),
    ],
    "CH": [
        ("Zurich", 47.377, 8.542), ("Geneva", 46.205, 6.144), ("Basel", 47.559, 7.589),
        ("Bern", 46.948, 7.448), ("Lausanne", 46.520, 6.634), ("Lucerne", 47.050, 8.310),
    ],
}

MAKES_MODELS = {
    "BMW": [
        ("1 Series", "HATCHBACK"), ("2 Series", "COUPE"), ("3 Series", "SEDAN"),
        ("4 Series", "COUPE"), ("5 Series", "SEDAN"), ("X1", "SUV"),
        ("X3", "SUV"), ("X5", "SUV"), ("X6", "SUV"), ("iX3", "SUV"),
    ],
    "Mercedes-Benz": [
        ("A-Class", "HATCHBACK"), ("C-Class", "SEDAN"), ("E-Class", "SEDAN"),
        ("S-Class", "SEDAN"), ("GLA", "SUV"), ("GLC", "SUV"),
        ("GLE", "SUV"), ("CLA", "COUPE"), ("EQC", "SUV"), ("B-Class", "MPV"),
    ],
    "Audi": [
        ("A1", "HATCHBACK"), ("A3", "SEDAN"), ("A4", "SEDAN"), ("A5", "COUPE"),
        ("A6", "SEDAN"), ("Q3", "SUV"), ("Q5", "SUV"), ("Q7", "SUV"),
        ("e-tron", "SUV"), ("TT", "COUPE"),
    ],
    "Volkswagen": [
        ("Golf", "HATCHBACK"), ("Polo", "HATCHBACK"), ("Passat", "SEDAN"),
        ("Tiguan", "SUV"), ("T-Roc", "SUV"), ("T-Cross", "SUV"),
        ("ID.3", "HATCHBACK"), ("ID.4", "SUV"), ("Arteon", "SEDAN"), ("Touareg", "SUV"),
    ],
    "Peugeot": [
        ("208", "HATCHBACK"), ("308", "HATCHBACK"), ("508", "SEDAN"),
        ("2008", "SUV"), ("3008", "SUV"), ("5008", "SUV"), ("e-208", "HATCHBACK"),
    ],
    "Renault": [
        ("Clio", "HATCHBACK"), ("Megane", "HATCHBACK"), ("Captur", "SUV"),
        ("Kadjar", "SUV"), ("Arkana", "SUV"), ("Zoe", "HATCHBACK"),
        ("Scenic", "MPV"), ("Talisman", "SEDAN"),
    ],
    "SEAT": [
        ("Ibiza", "HATCHBACK"), ("Leon", "HATCHBACK"), ("Arona", "SUV"),
        ("Ateca", "SUV"), ("Tarraco", "SUV"), ("Cupra Formentor", "SUV"),
    ],
    "Skoda": [
        ("Fabia", "HATCHBACK"), ("Octavia", "SEDAN"), ("Superb", "SEDAN"),
        ("Kamiq", "SUV"), ("Karoq", "SUV"), ("Kodiaq", "SUV"), ("Enyaq", "SUV"),
    ],
    "Toyota": [
        ("Yaris", "HATCHBACK"), ("Corolla", "SEDAN"), ("Camry", "SEDAN"),
        ("C-HR", "SUV"), ("RAV4", "SUV"), ("Yaris Cross", "SUV"), ("Aygo X", "HATCHBACK"),
    ],
    "Ford": [
        ("Fiesta", "HATCHBACK"), ("Focus", "HATCHBACK"), ("Puma", "SUV"),
        ("Kuga", "SUV"), ("Mustang Mach-E", "SUV"), ("Mondeo", "SEDAN"),
    ],
    "Opel": [
        ("Corsa", "HATCHBACK"), ("Astra", "HATCHBACK"), ("Mokka", "SUV"),
        ("Crossland", "SUV"), ("Grandland", "SUV"), ("Insignia", "SEDAN"),
    ],
    "Fiat": [
        ("500", "HATCHBACK"), ("Panda", "HATCHBACK"), ("Tipo", "SEDAN"),
        ("500X", "SUV"), ("500L", "MPV"), ("500e", "HATCHBACK"),
    ],
    "Hyundai": [
        ("i20", "HATCHBACK"), ("i30", "HATCHBACK"), ("Tucson", "SUV"),
        ("Kona", "SUV"), ("IONIQ 5", "SUV"), ("Santa Fe", "SUV"),
    ],
    "Kia": [
        ("Picanto", "HATCHBACK"), ("Rio", "HATCHBACK"), ("Ceed", "HATCHBACK"),
        ("Sportage", "SUV"), ("EV6", "SUV"), ("Niro", "SUV"), ("Sorento", "SUV"),
    ],
    "Volvo": [
        ("XC40", "SUV"), ("XC60", "SUV"), ("XC90", "SUV"),
        ("V60", "ESTATE"), ("V90", "ESTATE"), ("S60", "SEDAN"), ("C40", "SUV"),
    ],
    "Porsche": [
        ("Cayenne", "SUV"), ("Macan", "SUV"), ("911", "COUPE"),
        ("Taycan", "SEDAN"), ("Panamera", "SEDAN"), ("718 Cayman", "COUPE"),
    ],
    "Land Rover": [
        ("Range Rover Evoque", "SUV"), ("Range Rover Sport", "SUV"),
        ("Discovery Sport", "SUV"), ("Defender", "SUV"), ("Range Rover Velar", "SUV"),
    ],
    "Citroen": [
        ("C3", "HATCHBACK"), ("C4", "HATCHBACK"), ("C5 Aircross", "SUV"),
        ("Berlingo", "MPV"), ("C3 Aircross", "SUV"), ("e-C4", "HATCHBACK"),
    ],
    "Nissan": [
        ("Micra", "HATCHBACK"), ("Qashqai", "SUV"), ("Juke", "SUV"),
        ("X-Trail", "SUV"), ("Leaf", "HATCHBACK"), ("Ariya", "SUV"),
    ],
    "Mazda": [
        ("Mazda2", "HATCHBACK"), ("Mazda3", "HATCHBACK"), ("Mazda6", "SEDAN"),
        ("CX-3", "SUV"), ("CX-5", "SUV"), ("CX-30", "SUV"), ("MX-5", "CONVERTIBLE"),
    ],
    "Tesla": [
        ("Model 3", "SEDAN"), ("Model Y", "SUV"), ("Model S", "SEDAN"), ("Model X", "SUV"),
    ],
}

FUEL_TYPES = ["PETROL", "DIESEL", "ELECTRIC", "HYBRID_PETROL", "HYBRID_DIESEL"]
FUEL_WEIGHTS = [0.30, 0.35, 0.10, 0.15, 0.10]
TRANSMISSIONS = ["MANUAL", "AUTOMATIC"]
TX_WEIGHTS = [0.40, 0.60]
COLORS = [
    "Black", "White", "Silver", "Grey", "Blue", "Red", "Green",
    "Brown", "Beige", "Orange", "Yellow", "Navy",
]
SELLER_TYPES = ["DEALER", "DEALER", "DEALER", "DEALER", "PRIVATE"]  # 80% dealers

# Price ranges by segment
PRICE_RANGES = {
    "HATCHBACK": (3500, 35000), "SEDAN": (5000, 65000), "COUPE": (8000, 90000),
    "SUV": (6000, 85000), "ESTATE": (5000, 55000), "MPV": (4000, 40000),
    "CONVERTIBLE": (8000, 70000),
}

PREMIUM_MAKES = {"BMW", "Mercedes-Benz", "Audi", "Porsche", "Land Rover", "Volvo", "Tesla"}

DEALER_NAMES = {
    "DE": ["AutoHaus Schmidt", "Müller Automobile", "Berliner AutoCenter", "AutoLand Bayern",
           "Rhein-Main Automobile", "Nordwest Auto", "Auto König", "Fahrzeughaus Weber",
           "Premium Cars GmbH", "AutoWelt Dresden", "Süddeutsche Automobile", "EuroCar Hamburg"],
    "ES": ["AutoSur Madrid", "Cars Barcelona SL", "Motor Valencia", "Coches Andalucía",
           "AutoMálaga Sur", "Bilbao Motor", "Zaragoza Cars", "Costa Blanca Autos",
           "Mallorca Motor", "Iberian Cars SL", "Sol y Motor", "AutoPremium España"],
    "FR": ["Auto Paris Centre", "Lyon Automobiles", "Méditerranée Auto", "Garage Toulouse",
           "Bordeaux Motors", "Nord Auto Lille", "Côte d'Azur Cars", "Atlantic Auto Nantes",
           "Alsace Automobiles", "Premium Cars Paris", "AutoFrance SAS", "Garage du Midi"],
    "NL": ["Amsterdam Auto", "Rotterdam Cars BV", "Den Haag Motors", "Utrecht Automobiles",
           "Eindhoven Auto", "Groningen Cars", "Holland Auto BV", "Dutch Premium Cars",
           "Randstad Automobiles", "AutoHolland BV", "Noord Auto", "Premium NL"],
    "BE": ["Bruxelles Auto", "Antwerpen Motors", "Gent Cars", "Liège Automobile",
           "Brugge Auto", "Leuven Cars", "Belgian Premium", "AutoBelgique BVBA",
           "Flanders Cars", "Wallonia Auto", "BeNeLux Motors", "Euro Cars Belgium"],
    "CH": ["Zürich Auto AG", "Genève Motors", "Basel Automobile", "Bern Cars AG",
           "Lausanne Auto", "Luzern Motors", "Swiss Premium Cars", "AutoSchweiz AG",
           "Alpine Motors", "Helvetia Cars", "Swiss Auto Center", "Edelweiss Motors"],
}

CURRENCIES = {"DE": "EUR", "ES": "EUR", "FR": "EUR", "NL": "EUR", "BE": "EUR", "CH": "CHF"}

# Listings per country
COUNTS = {"DE": 1500, "ES": 800, "FR": 1000, "NL": 600, "BE": 500, "CH": 600}


def random_vin():
    """Generate a plausible 17-char VIN."""
    chars = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
    wmi = random.choice(["WBA", "WDB", "WAU", "WVW", "VF1", "VF3", "VSS", "TMB",
                          "SB1", "WF0", "W0L", "ZFA", "KMH", "KNA", "YV1", "WP0",
                          "SAL", "VR1", "SJN", "JMZ", "5YJ"])
    rest = "".join(random.choices(chars, k=14))
    return wmi + rest


def generate_listing(country):
    make = random.choice(list(MAKES_MODELS.keys()))
    model_name, body_type = random.choice(MAKES_MODELS[make])

    year = random.randint(2015, 2025)
    age = 2026 - year
    mileage = max(500, int(random.gauss(age * 14000, age * 4000)))

    price_min, price_max = PRICE_RANGES.get(body_type, (5000, 50000))
    if make in PREMIUM_MAKES:
        price_min = int(price_min * 1.6)
        price_max = int(price_max * 1.8)

    # Newer = more expensive, high mileage = cheaper
    age_factor = max(0.3, 1.0 - (age * 0.08))
    mileage_factor = max(0.4, 1.0 - (mileage / 300000))
    base_price = random.uniform(price_min, price_max)
    price = int(base_price * age_factor * mileage_factor)
    price = max(500, min(price, 1999000))

    fuel = random.choices(FUEL_TYPES, weights=FUEL_WEIGHTS)[0]
    if make == "Tesla":
        fuel = "ELECTRIC"
    if "e-" in model_name or "EV" in model_name or "ID." in model_name or model_name in ("Leaf", "Zoe", "500e", "e-C4", "IONIQ 5", "Taycan"):
        fuel = "ELECTRIC"

    tx = random.choices(TRANSMISSIONS, weights=TX_WEIGHTS)[0]
    if make in ("Tesla", "Porsche") or fuel == "ELECTRIC":
        tx = "AUTOMATIC"

    power_kw = random.randint(60, 400) if make in PREMIUM_MAKES else random.randint(50, 220)
    co2 = 0 if fuel == "ELECTRIC" else random.randint(90, 250)

    city_name, lat, lng = random.choice(CITIES[country])
    lat += random.uniform(-0.15, 0.15)
    lng += random.uniform(-0.15, 0.15)

    platform, base_url = random.choice(PLATFORMS[country])
    listing_id = "".join(random.choices(string.digits, k=9))
    source_url = f"{base_url}{listing_id}"

    seller_type = random.choice(SELLER_TYPES)
    seller_name = random.choice(DEALER_NAMES[country]) if seller_type == "DEALER" else ""

    color = random.choice(COLORS)

    has_vin = random.random() < 0.65
    vin = random_vin() if has_vin else ""

    variant_suffixes = ["", " Sport", " Elegance", " AMG Line", " S line", " R-Line",
                        " GT", " Sportback", " Touring", " xDrive", " quattro", " 4MATIC"]
    variant = f"{model_name}{random.choice(variant_suffixes)}"

    n_photos = random.randint(3, 15)
    photo_urls = [f"https://cdn.cardex.eu/img/{listing_id}/{i}.jpg" for i in range(n_photos)]

    return {
        "vin": vin,
        "source_url": source_url,
        "source_listing_id": listing_id,
        "make": make,
        "model": model_name,
        "variant": variant,
        "year": year,
        "mileage_km": mileage,
        "color": color,
        "fuel_type": fuel,
        "transmission": tx,
        "body_type": body_type,
        "co2_gkm": co2,
        "power_kw": power_kw,
        "price_raw": price,
        "currency_raw": CURRENCIES[country],
        "lat": round(lat, 6),
        "lng": round(lng, 6),
        "city": city_name,
        "region": city_name,
        "source_country": country,
        "seller_type": seller_type,
        "seller_name": seller_name,
        "photo_urls": photo_urls,
        "thumbnail_url": photo_urls[0] if photo_urls else "",
        "description_snippet": f"{year} {make} {variant}, {mileage}km, {fuel.lower().replace('_', ' ')}, {tx.lower()}",
        "listing_status": "ACTIVE",
    }


def sign_body(body_bytes):
    return hmac_mod.new(HMAC_SECRET, body_bytes, hashlib.sha256).hexdigest()


def post_listing(listing):
    body = json.dumps(listing).encode("utf-8")
    sig = sign_body(body)
    req = urllib.request.Request(
        GATEWAY_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Cardex-Signature": sig,
            "X-Partner-ID": "cardex-seed",
            "X-Scraper-Source": listing.get("source_listing_id", "seed"),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return str(e)


def main():
    total = sum(COUNTS.values())
    print(f"=== CARDEX Seed: Generating {total} vehicles across 6 countries ===\n")

    success = 0
    errors = 0
    t0 = time.time()

    for country, count in COUNTS.items():
        print(f"  [{country}] Seeding {count} vehicles...")
        country_ok = 0
        for i in range(count):
            listing = generate_listing(country)
            status = post_listing(listing)
            if status == 200:
                country_ok += 1
                success += 1
            else:
                errors += 1
                if errors <= 5:
                    print(f"    [ERROR] Status {status} for {listing['make']} {listing['model']}")
                elif errors == 6:
                    print(f"    [ERROR] Suppressing further error logs...")

            if (i + 1) % 100 == 0:
                elapsed = time.time() - t0
                rate = success / elapsed if elapsed > 0 else 0
                print(f"    [{country}] {i+1}/{count} sent | {success} ok | {rate:.0f} listings/sec")

        print(f"  [{country}] Done: {country_ok}/{count} ingested\n")

    elapsed = time.time() - t0
    print(f"=== SEED COMPLETE ===")
    print(f"  Total sent:    {success + errors}")
    print(f"  Ingested:      {success}")
    print(f"  Errors:        {errors}")
    print(f"  Time:          {elapsed:.1f}s")
    print(f"  Rate:          {success/elapsed:.0f} listings/sec")
    print(f"\nWait 10-15 seconds for MeiliSearch indexing, then check:")
    print(f"  curl http://localhost:7700/indexes/vehicles/stats")
    print(f"  curl 'http://localhost:8080/api/v1/marketplace/search?q=BMW'")
    print(f"  Open http://localhost:3001")


if __name__ == "__main__":
    main()
