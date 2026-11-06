"""
WattWise Demo Data Seeder
Populates the active database with realistic, high-fidelity sample records:
- Diverse consumer sectors (Residential, Commercial, Industrial, Agricultural)
- Active meters across regions (Tirupati, Chittoor, Nellore, Kadapa, Madanapalle)
- 14 months of chronological readings (Jan 2025 to Feb 2026)
- Realistic seasonal consumption curves and high-usage alerts
"""
import os
import sys
from datetime import date, timedelta
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

load_dotenv()
import db
from services.calculator import calculate_period_consumption

DEMO_CONSUMERS = [
    {
        "name": "Aarav Sharma",
        "type": "Residential",
        "region": "Tirupati",
        "phone": "+91 98480 12345",
        "email": "aarav.sharma@example.com",
        "status": "Active"
    },
    {
        "name": "Lakshmi Residency Apartments",
        "type": "Residential",
        "region": "Tirupati",
        "phone": "+91 94401 23456",
        "email": "secretary@lakshmiresidency.org",
        "status": "Active"
    },
    {
        "name": "Dr. K. Srinivas Rao",
        "type": "Residential",
        "region": "Chittoor",
        "phone": "+91 98852 34567",
        "email": "srinivas.rao@medmail.in",
        "status": "Active"
    },
    {
        "name": "Green Basket Supermarket",
        "type": "Commercial",
        "region": "Chittoor",
        "phone": "+91 97003 45678",
        "email": "ops@greenbasket.co.in",
        "status": "Active"
    },
    {
        "name": "Sapthagiri Grand Hotel",
        "type": "Commercial",
        "region": "Tirupati",
        "phone": "+91 99894 56789",
        "email": "facilities@sapthagirigrand.com",
        "status": "Active"
    },
    {
        "name": "Nellore Cold Storage & Logistics",
        "type": "Commercial",
        "region": "Nellore",
        "phone": "+91 98495 67890",
        "email": "warehouse@nellorecoldstorage.com",
        "status": "Active"
    },
    {
        "name": "Sunrise Spinning & Textiles Mill",
        "type": "Industrial",
        "region": "Nellore",
        "phone": "+91 98486 78901",
        "email": "accounts@sunrisetextiles.com",
        "status": "Active"
    },
    {
        "name": "Balaji Auto Component Foundry",
        "type": "Industrial",
        "region": "Chittoor",
        "phone": "+91 98497 89012",
        "email": "planthead@balajiauto.in",
        "status": "Active"
    },
    {
        "name": "Sri Venkateswara Dairy & Agri Farm",
        "type": "Agricultural",
        "region": "Madanapalle",
        "phone": "+91 99638 90123",
        "email": "contact@svdairyfarm.in",
        "status": "Active"
    },
    {
        "name": "Raman Micro-Irrigation Coop",
        "type": "Agricultural",
        "region": "Kadapa",
        "phone": "+91 94419 01234",
        "email": "secretary@ramanirrigation.org",
        "status": "Active"
    }
]

# Baseline monthly profiles (approximate base kWh per month)
MONTHLY_MULTIPLIERS = {
    1: 0.85,   # Jan (Mild winter)
    2: 0.90,   # Feb
    3: 1.05,   # Mar (Spring begins)
    4: 1.30,   # Apr (Summer peak begins)
    5: 1.50,   # May (Peak summer air-conditioning)
    6: 1.40,   # Jun (Hot summer)
    7: 1.15,   # Jul (Monsoon onset)
    8: 1.10,   # Aug
    9: 1.05,   # Sep
    10: 0.95,  # Oct (Post-monsoon)
    11: 0.88,  # Nov
    12: 0.82   # Dec (Cool winter)
}

METER_PROFILES = [
    {"code": "WW-TPT-101", "consumer_idx": 0, "base_kwh": 260, "capacity": 10000},
    {"code": "WW-TPT-102", "consumer_idx": 1, "base_kwh": 620, "capacity": 25000},
    {"code": "WW-CTR-103", "consumer_idx": 2, "base_kwh": 310, "capacity": 10000},
    {"code": "WW-CTR-201", "consumer_idx": 3, "base_kwh": 1450, "capacity": 50000},
    {"code": "WW-TPT-202", "consumer_idx": 4, "base_kwh": 2800, "capacity": 100000},
    {"code": "WW-NEL-203", "consumer_idx": 5, "base_kwh": 2100, "capacity": 75000},
    {"code": "WW-NEL-301", "consumer_idx": 6, "base_kwh": 4800, "capacity": 200000},
    {"code": "WW-CTR-302", "consumer_idx": 7, "base_kwh": 3900, "capacity": 150000},
    {"code": "WW-MDP-401", "consumer_idx": 8, "base_kwh": 780, "capacity": 25000},
    {"code": "WW-KDP-402", "consumer_idx": 9, "base_kwh": 650, "capacity": 25000},
]


def seed_database(clear_existing: bool = False):
    print("=" * 65)
    print(" WattWise Demo Data Generator")
    print("=" * 65)
    status = db.get_db_status()
    print(f"Target Database Engine: {status['engine'].upper()} ({status['active_db']})")

    if clear_existing:
        print("Clearing existing records...")
        db.execute("DELETE FROM meter_readings;")
        db.execute("DELETE FROM meters;")
        db.execute("DELETE FROM consumers;")
        print("Existing tables emptied.")

    # 1. Insert Consumers
    consumer_ids = []
    print("\nRegistering demo consumers...")
    for c in DEMO_CONSUMERS:
        existing = db.query_one("SELECT consumer_id FROM consumers WHERE consumer_name=%s", (c["name"],))
        if existing:
            cid = existing["consumer_id"]
            print(f"  Existing consumer: {c['name']} (ID: {cid})")
        else:
            cid = db.execute("""
                INSERT INTO consumers (consumer_name, consumer_type, region, phone, email, status)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (c["name"], c["type"], c["region"], c["phone"], c["email"], c["status"]))
            print(f"  + Added consumer: {c['name']} ({c['type']}, {c['region']})")
        consumer_ids.append(cid)

    # 2. Register Meters
    print("\nRegistering demo meters...")
    meter_ids = []
    for mp in METER_PROFILES:
        cid = consumer_ids[mp["consumer_idx"]]
        code = mp["code"]
        existing = db.query_one("SELECT meter_id FROM meters WHERE meter_code=%s", (code,))
        if existing:
            mid = existing["meter_id"]
            print(f"  Existing meter: {code} (ID: {mid})")
        else:
            mid = db.execute("""
                INSERT INTO meters (consumer_id, meter_code, meter_capacity, status)
                VALUES (%s, %s, %s, 'Active')
            """, (cid, code, mp["capacity"]))
            print(f"  + Added meter: {code} for Consumer ID {cid}")
        meter_ids.append((mid, mp))

    # 3. Generate Chronological Readings
    # 14 consecutive monthly reading cycles from 2025-01-05 to 2026-02-05
    dates = []
    cur_year = 2025
    cur_month = 1
    for _ in range(14):
        dates.append(date(cur_year, cur_month, 5))
        cur_month += 1
        if cur_month > 12:
            cur_month = 1
            cur_year += 1

    print(f"\nRecording {len(dates)} monthly readings for each meter...")
    total_readings_created = 0

    for mid, mp in meter_ids:
        # Starting base cumulative counter
        cumulative_counter = round(float(mp["base_kwh"]) * 3.5, 2)
        base_kwh = mp["base_kwh"]

        for i, read_date in enumerate(dates):
            date_str = read_date.strftime("%Y-%m-%d")
            
            # Check if reading already exists
            existing = db.query_one("SELECT reading_id FROM meter_readings WHERE meter_id=%s AND reading_date=%s", (mid, date_str))
            if existing:
                continue

            if i == 0:
                # Baseline initial reading
                period_consumption = None
                notes = "Initial baseline meter installation reading"
            else:
                multiplier = MONTHLY_MULTIPLIERS.get(read_date.month, 1.0)
                # Introduce subtle realistic variations (+/- 4%)
                variation = 1.0 + ((i % 5) - 2) * 0.02
                period_consumption = round(base_kwh * multiplier * variation, 2)
                cumulative_counter = round(cumulative_counter + period_consumption, 2)
                
                if period_consumption >= 2000:
                    notes = "High-load commercial/industrial cycle recorded"
                elif read_date.month in (5, 6) and period_consumption >= 500:
                    notes = "Summer peak cooling load observed"
                else:
                    notes = "Regular monthly utility cycle"

            db.execute("""
                INSERT INTO meter_readings (meter_id, reading_date, cumulative_kwh, consumption_kwh, notes)
                VALUES (%s, %s, %s, %s, %s)
            """, (mid, date_str, cumulative_counter, period_consumption, notes))
            total_readings_created += 1

    print(f"\n✓ Seeding complete! {total_readings_created} new meter readings inserted.")
    print("✓ All tables populated with realistic, analytical electricity data.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Seed WattWise Demo Data")
    parser.add_argument("--clear", action="store_true", help="Clear existing data before seeding")
    args = parser.parse_args()
    seed_database(clear_existing=args.clear)
