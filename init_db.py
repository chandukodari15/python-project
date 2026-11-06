"""
WattWise Database Initializer & Migration Service
Sets up the database schema on MySQL 8.0 and safely migrates data.
Never reveals credentials.
"""
import os
import sys
import argparse
import sqlite3
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

load_dotenv()
import db

def init_mysql(migrate_from_sqlite: bool = True):
    print("=" * 65)
    print(" WattWise: MySQL Database Initializer & Migration")
    print("=" * 65)
    host = os.getenv("MYSQL_HOST", "localhost")
    port = int(os.getenv("MYSQL_PORT", "3306"))
    user = os.getenv("MYSQL_USER", "root")
    password = os.getenv("MYSQL_PASSWORD", "")
    database = os.getenv("MYSQL_DB", "electricity_analysis")

    print(f"Targeting MySQL Server at {host}:{port} with user '{user}'...")

    try:
        import pymysql
        # Connect to MySQL server without selecting DB initially
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            charset="utf8mb4",
            autocommit=True
        )
        print("[OK] Connected to MySQL server successfully!")

        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            print(f"[OK] Database `{database}` confirmed/created.")
            cur.execute(f"USE `{database}`;")

            # 1. Execute schema DDL statements
            schema_path = os.path.join(BASE_DIR, "schema.sql")
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_content = f.read()

            statements = []
            current = []
            in_delimiter = False
            for line in schema_content.splitlines():
                stripped = line.strip()
                if stripped.startswith("DELIMITER"):
                    in_delimiter = not in_delimiter
                    continue
                if in_delimiter:
                    continue
                if stripped.startswith("--") or not stripped:
                    continue
                current.append(line)
                if stripped.endswith(";"):
                    stmt = "\n".join(current).strip()
                    if stmt:
                        statements.append(stmt)
                    current = []

            for stmt in statements:
                if stmt.upper().startswith("CREATE DATABASE") or stmt.upper().startswith("USE "):
                    continue
                try:
                    cur.execute(stmt)
                except Exception as e:
                    print(f"  Note during schema execution: {e}")

            # 2. Create triggers explicitly
            try:
                cur.execute("DROP TRIGGER IF EXISTS before_meter_reading_insert;")
                cur.execute("""
                CREATE TRIGGER before_meter_reading_insert
                BEFORE INSERT ON meter_readings
                FOR EACH ROW
                BEGIN
                  DECLARE previous_value DECIMAL(12,2);
                  SELECT cumulative_kwh INTO previous_value
                  FROM meter_readings
                  WHERE meter_id = NEW.meter_id AND reading_date < NEW.reading_date
                  ORDER BY reading_date DESC, reading_id DESC LIMIT 1;

                  IF previous_value IS NOT NULL AND NEW.cumulative_kwh < previous_value THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cumulative reading cannot be lower than the previous reading; verify meter reset/rollover.';
                  END IF;

                  IF previous_value IS NOT NULL THEN
                    SET NEW.consumption_kwh = NEW.cumulative_kwh - previous_value;
                  ELSE
                    SET NEW.consumption_kwh = NULL;
                  END IF;
                END;
                """)
                print("[OK] Stored trigger 'before_meter_reading_insert' created.")
            except Exception as e:
                print(f"  Note creating insert trigger: {e}")

            try:
                cur.execute("DROP TRIGGER IF EXISTS before_meter_reading_update;")
                cur.execute("""
                CREATE TRIGGER before_meter_reading_update
                BEFORE UPDATE ON meter_readings
                FOR EACH ROW
                BEGIN
                  DECLARE previous_value DECIMAL(12,2);
                  SELECT cumulative_kwh INTO previous_value
                  FROM meter_readings
                  WHERE meter_id = NEW.meter_id AND reading_date < NEW.reading_date
                    AND reading_id <> OLD.reading_id
                  ORDER BY reading_date DESC, reading_id DESC LIMIT 1;

                  IF previous_value IS NOT NULL AND NEW.cumulative_kwh < previous_value THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cumulative reading cannot be lower than the previous reading.';
                  END IF;

                  IF previous_value IS NOT NULL THEN
                    SET NEW.consumption_kwh = NEW.cumulative_kwh - previous_value;
                  ELSE
                    SET NEW.consumption_kwh = NULL;
                  END IF;
                END;
                """)
                print("[OK] Stored trigger 'before_meter_reading_update' created.")
            except Exception as e:
                print(f"  Note creating update trigger: {e}")

            # 3. Check and populate demo data if MySQL is empty
            cur.execute("SELECT COUNT(*) FROM consumers;")
            mysql_count = cur.fetchone()[0]

            if mysql_count == 0:
                sqlite_path = os.path.join(BASE_DIR, "wattwise.db")
                if migrate_from_sqlite and os.path.exists(sqlite_path):
                    print(f"\nMigrating existing data from {sqlite_path} to MySQL...")
                    s_conn = sqlite3.connect(sqlite_path)
                    s_conn.row_factory = sqlite3.Row
                    s_cur = s_conn.cursor()

                    # Migrate consumers
                    s_cur.execute("SELECT * FROM consumers ORDER BY consumer_id ASC;")
                    c_rows = s_cur.fetchall()
                    for c in c_rows:
                        cur.execute("""
                            INSERT INTO consumers (consumer_id, consumer_name, consumer_type, region, phone, email, status, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """, (c["consumer_id"], c["consumer_name"], c["consumer_type"], c["region"], c["phone"], c["email"], c["status"], c["created_at"]))
                    print(f"  + Migrated {len(c_rows)} consumers to MySQL.")

                    # Migrate meters
                    s_cur.execute("SELECT * FROM meters ORDER BY meter_id ASC;")
                    m_rows = s_cur.fetchall()
                    for m in m_rows:
                        cur.execute("""
                            INSERT INTO meters (meter_id, consumer_id, meter_code, meter_capacity, status, installed_at)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (m["meter_id"], m["consumer_id"], m["meter_code"], m["meter_capacity"], m["status"], m["installed_at"]))
                    print(f"  + Migrated {len(m_rows)} meters to MySQL.")

                    # Migrate readings
                    s_cur.execute("SELECT * FROM meter_readings ORDER BY meter_id ASC, reading_date ASC, reading_id ASC;")
                    r_rows = s_cur.fetchall()
                    for r in r_rows:
                        cur.execute("""
                            INSERT INTO meter_readings (reading_id, meter_id, reading_date, cumulative_kwh, consumption_kwh, notes, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (r["reading_id"], r["meter_id"], r["reading_date"], r["cumulative_kwh"], r["consumption_kwh"], r["notes"], r["created_at"]))
                    print(f"  + Migrated {len(r_rows)} meter readings to MySQL.")

                    s_conn.close()
                else:
                    print("\nSeeding realistic demo dataset into MySQL...")
                    import seed_demo
                    seed_demo.seed_database(clear_existing=False)
            else:
                print(f"MySQL already contains {mysql_count} consumer records; skipping migration/seeding.")

            # Verify tables and counts
            cur.execute("SHOW TABLES;")
            tables = [row[0] for row in cur.fetchall()]
            print(f"\n[OK] MySQL Tables verified: {', '.join(tables)}")

            cur.execute("SELECT COUNT(*) FROM consumers;")
            c_cnt = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM meters;")
            m_cnt = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM meter_readings;")
            r_cnt = cur.fetchone()[0]
            print(f"[OK] Record Verification: Consumers={c_cnt}, Meters={m_cnt}, Readings={r_cnt}")

        conn.close()
        print("\nSUCCESS: MySQL Database initialized, migrated, and ready for WattWise!")
        return True
    except Exception as exc:
        print("\n[ERROR] Could not connect or initialize MySQL:")
        # Sanitize error to avoid showing credentials
        err_msg = str(exc)
        if password:
            err_msg = err_msg.replace(password, "***")
        print(f"  Error details: {err_msg}")
        return False

def init_sqlite():
    print("=" * 65)
    print(" WattWise: SQLite Local Database Initializer")
    print("=" * 65)
    sqlite_file = os.path.join(BASE_DIR, "wattwise.db")
    print(f"Initializing local SQLite database at: {sqlite_file}")
    db.init_sqlite_tables(sqlite_file)
    print("[OK] Created tables: consumers, meters, meter_readings, system_settings.")
    print("\nSUCCESS: Local SQLite database initialized and ready!")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize WattWise Database")
    parser.add_argument("--sqlite", action="store_true", help="Force SQLite initialization")
    parser.add_argument("--mysql", action="store_true", help="Force MySQL initialization")
    args = parser.parse_args()

    if args.sqlite:
        init_sqlite()
    else:
        init_mysql(migrate_from_sqlite=True)
