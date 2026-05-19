"""
Seed demo data into workspace SQLite DB.
Inserts ~300 vehicles + kanban cards + contacts + deals for tenant t_demo.
Run: py seed_demo.py
"""
import sqlite3, uuid, random, datetime, json

DB = "data/workspace.db"
TENANT = "t_demo"

MAKES = {
    "BMW": ["118i", "120d", "320d", "320i", "330d", "520d", "520i", "X1", "X3", "X5", "M3", "118d"],
    "Mercedes-Benz": ["A180", "A200", "C200", "C220d", "C300", "E220d", "E350", "GLA200", "GLC300", "CLA200"],
    "Volkswagen": ["Golf 1.6 TDI", "Golf 2.0 TDI", "Passat 2.0 TDI", "Tiguan 2.0 TDI", "Polo 1.0 TSI", "T-Roc"],
    "Audi": ["A3 2.0 TDI", "A4 2.0 TDI", "A6 3.0 TDI", "Q3 2.0 TDI", "Q5 2.0 TDI", "A1 1.4 TFSI"],
    "Renault": ["Clio 1.5 dCi", "Megane 1.5 dCi", "Kadjar 1.6 dCi", "Captur 1.3 TCe", "Zoe"],
    "Peugeot": ["208 1.2 PureTech", "308 1.5 BlueHDi", "3008 1.6 THP", "5008 2.0 BlueHDi", "2008"],
    "Ford": ["Focus 1.5 EcoBlue", "Fiesta 1.1", "Kuga 2.0 TDCi", "Puma 1.0 EcoBoost", "Mondeo 2.0 TDCi"],
    "Seat": ["Ibiza 1.0 TSI", "Leon 1.5 TSI", "Ateca 2.0 TDI", "Arona 1.0 TSI"],
    "Toyota": ["Corolla 1.8 Hybrid", "Yaris 1.5 Hybrid", "RAV4 2.5 Hybrid", "C-HR 1.8 Hybrid"],
    "Skoda": ["Octavia 2.0 TDI", "Fabia 1.0 TSI", "Kodiaq 2.0 TDI", "Karoq 1.5 TSI"],
    "Opel": ["Astra 1.6 CDTI", "Corsa 1.2", "Insignia 2.0 CDTI", "Grandland X 1.5 CDTI"],
    "Fiat": ["500 1.2", "Tipo 1.6 Multijet", "Panda 1.2"],
    "Hyundai": ["i20 1.0 T-GDI", "i30 1.5 CRDi", "Tucson 1.6 CRDi", "Kona 1.0 T-GDI"],
    "Kia": ["Ceed 1.6 CRDi", "Sportage 1.6 CRDi", "Niro 1.6 GDI Hybrid", "Stonic 1.0 T-GDI"],
}

FUELS = ["Diesel", "Petrol", "Hybrid", "Electric", "Petrol"]
GEARBOXES = ["Manual", "Automatic", "Manual", "Manual"]
COLORS = ["Black", "White", "Silver", "Grey", "Blue", "Red", "Dark Blue", "Anthracite", "Beige"]
COUNTRIES = ["ES", "DE", "FR", "NL", "BE", "CH"]

STATUSES = ["available"] * 12 + ["inquiry"] * 4 + ["reserved"] * 2 + ["sold"] * 2

CONTACT_NAMES = [
    "Carlos García", "Marie Dupont", "Hans Müller", "Marco Rossi", "Sophie Laurent",
    "Javier Martínez", "Anna Schmidt", "Pierre Martin", "Luis Fernández", "Emma Bernard",
    "Diego López", "Clara Weber", "Romain Dubois", "Isabel Rodríguez", "Felix Wagner",
    "Nathalie Petit", "Alejandro Sánchez", "Katrin Becker", "Mathieu Moreau", "Elena Gómez",
    "Thomas Hoffmann", "Sarah Lefebvre", "Manuel Torres", "Laura Fischer", "Antoine Simon",
]

DEAL_STAGES = ["new", "contacted", "offer_sent", "negotiation", "won", "lost"]
DEAL_STAGE_WEIGHTS = [3, 3, 2, 2, 1, 1]


def uid() -> str:
    return uuid.uuid4().hex


def now_iso() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def past_iso(days_ago: int) -> str:
    dt = datetime.datetime.utcnow() - datetime.timedelta(days=days_ago)
    return dt.isoformat() + "Z"


def random_vin() -> str:
    chars = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
    return "WV" + "".join(random.choices(chars, k=15))


def random_price(make: str, year: int) -> int:
    base = {
        "BMW": 22000, "Mercedes-Benz": 24000, "Audi": 21000,
        "Volkswagen": 14000, "Ford": 12000, "Renault": 10000,
        "Peugeot": 11000, "Seat": 11000, "Toyota": 18000,
        "Skoda": 13000, "Opel": 10000, "Fiat": 8000,
        "Hyundai": 13000, "Kia": 14000,
    }.get(make, 12000)
    age_factor = max(0.4, 1 - (2025 - year) * 0.07)
    jitter = random.uniform(0.85, 1.18)
    return int(base * age_factor * jitter / 100) * 100


def weighted_choice(items, weights):
    total = sum(weights)
    r = random.uniform(0, total)
    cumulative = 0
    for item, w in zip(items, weights):
        cumulative += w
        if r <= cumulative:
            return item
    return items[-1]


def seed():
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys = OFF")

    # ── clear existing demo data ──────────────────────────────────────────────
    for tbl in ["crm_kanban_cards", "crm_deals", "crm_activities",
                "crm_transactions", "crm_vehicles", "crm_contacts"]:
        conn.execute(f"DELETE FROM {tbl} WHERE tenant_id=?", (TENANT,))
    conn.commit()

    # ── fetch kanban columns ──────────────────────────────────────────────────
    cols = conn.execute(
        "SELECT id, state_key, position FROM crm_kanban_columns WHERE tenant_id=? ORDER BY position",
        (TENANT,)
    ).fetchall()
    col_map = {c[1] or f"pos{c[2]}": c[0] for c in cols}
    col_ids = [c[0] for c in cols]

    status_to_col = {
        "available": col_map.get("available") or col_ids[0],
        "inquiry":   col_map.get("inquiry")   or col_ids[min(1, len(col_ids)-1)],
        "reserved":  col_map.get("reserved")  or col_ids[min(2, len(col_ids)-1)],
        "sold":      col_map.get("sold")       or col_ids[-1],
    }

    # ── vehicles ──────────────────────────────────────────────────────────────
    vehicles = []
    makes_list = list(MAKES.keys())
    for i in range(300):
        make = random.choice(makes_list)
        model = random.choice(MAKES[make])
        year = random.randint(2014, 2023)
        status = random.choice(STATUSES)
        days_ago = random.randint(1, 180)
        vid = uid()
        price = random_price(make, year)
        km = random.randint(8000, 220000)
        fuel = random.choice(FUELS)
        gear = random.choice(GEARBOXES)
        color = random.choice(COLORS)
        country = random.choice(COUNTRIES)
        ext_id = f"{country}-{random.randint(10000000, 99999999)}"
        vin = random_vin()
        created = past_iso(days_ago)
        updated = past_iso(max(0, days_ago - random.randint(0, days_ago)))

        conn.execute(
            """INSERT INTO crm_vehicles
               (id, tenant_id, external_id, vin, make, model, year, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (vid, TENANT, ext_id, vin, make, model, year, status, created, updated)
        )
        vehicles.append({
            "id": vid, "make": make, "model": model, "year": year,
            "status": status, "price": price, "km": km,
            "fuel": fuel, "gear": gear, "color": color,
            "created": created, "days_ago": days_ago,
        })

        # purchase transaction
        cost = int(price * random.uniform(0.72, 0.88))
        conn.execute(
            """INSERT INTO crm_transactions
               (id, tenant_id, vehicle_id, type, amount_cents, currency, vat_cents, vat_rate, counterparty, reference, date, notes, created_at, updated_at)
               VALUES (?,?,?,'purchase',?,?,?,?,?,?,?,?,?,?)""",
            (uid(), TENANT, vid, cost * 100, "EUR",
             int(cost * 100 * 0.21), 0.21,
             f"{make} Dealer", f"INV-{random.randint(10000,99999)}",
             created[:10], f"{fuel} · {gear} · {km:,} km · {color}",
             created, updated)
        )

        # sale transaction for sold vehicles
        if status == "sold":
            sold_date = past_iso(max(0, days_ago - random.randint(5, 30)))
            conn.execute(
                """INSERT INTO crm_transactions
                   (id, tenant_id, vehicle_id, type, amount_cents, currency, vat_cents, vat_rate, counterparty, reference, date, notes, created_at, updated_at)
                   VALUES (?,?,?,'sale',?,?,?,?,?,?,?,?,?,?)""",
                (uid(), TENANT, vid, price * 100, "EUR",
                 int(price * 100 * 0.21), 0.21,
                 "Customer", f"VTA-{random.randint(10000,99999)}",
                 sold_date[:10], "", sold_date, sold_date)
            )

        # kanban card
        col_id = status_to_col.get(status, col_ids[0])
        conn.execute(
            """INSERT OR IGNORE INTO crm_kanban_cards
               (vehicle_id, tenant_id, column_id, position, priority, labels, updated_at)
               VALUES (?,?,?,?,?,?,?)""",
            (vid, TENANT, col_id, i, "normal", "[]", updated)
        )

    conn.commit()
    print(f"OK {len(vehicles)} vehicles inserted")

    # ── contacts ──────────────────────────────────────────────────────────────
    contacts = []
    for name in CONTACT_NAMES:
        cid = uid()
        slug = name.lower().replace(" ", ".").replace("-", "")
        domains = ["gmail.com", "hotmail.com", "outlook.com", "yahoo.com"]
        email = f"{slug}@{random.choice(domains)}"
        phone = f"+{random.choice([34,33,49,31,32,41])}{random.randint(600000000,799999999)}"
        created = past_iso(random.randint(10, 200))
        conn.execute(
            "INSERT INTO crm_contacts (id, tenant_id, name, email, phone, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (cid, TENANT, name, email, phone, created, created)
        )
        contacts.append({"id": cid, "name": name, "created": created})
    conn.commit()
    print(f"OK {len(contacts)} contacts inserted")

    # ── deals ─────────────────────────────────────────────────────────────────
    deal_vehicles = [v for v in vehicles if v["status"] in ("inquiry", "reserved", "sold")]
    deal_vehicles += random.sample([v for v in vehicles if v["status"] == "available"], min(30, len(vehicles)))
    random.shuffle(deal_vehicles)

    deal_count = 0
    for v in deal_vehicles[:80]:
        contact = random.choice(contacts)
        stage = weighted_choice(DEAL_STAGES, DEAL_STAGE_WEIGHTS)
        if v["status"] == "sold":
            stage = "won"
        elif v["status"] == "reserved":
            stage = random.choice(["offer_sent", "negotiation"])
        created = past_iso(random.randint(1, v["days_ago"]))
        conn.execute(
            """INSERT INTO crm_deals (id, tenant_id, contact_id, vehicle_id, stage, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?)""",
            (uid(), TENANT, contact["id"], v["id"], stage, created, created)
        )
        deal_count += 1
    conn.commit()
    print(f"OK {deal_count} deals inserted")

    conn.execute("PRAGMA foreign_keys = ON")
    conn.close()
    print("\nDone. Login: admin / admin  →  http://localhost:5173")


if __name__ == "__main__":
    random.seed(42)
    seed()
