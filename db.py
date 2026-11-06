"""
WattWise Database Engine
Unified database management supporting MySQL 8.0 as primary with
transparent SQLite fallback for frictionless local execution and testing.
Never reveals or leaks database passwords.
"""
import os
import sys
import sqlite3
import logging
from datetime import datetime, date
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Load .env from both local project directory and parent workspace
load_dotenv(os.path.join(BASE_DIR, ".env"))
load_dotenv(os.path.join(os.path.dirname(BASE_DIR), ".env"))

logger = logging.getLogger("wattwise.db")

# Environment configurations
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DB = os.getenv("MYSQL_DB", "electricity_analysis")
PREFERRED_ENGINE = os.getenv("DB_ENGINE", "mysql").lower()  # 'mysql', 'sqlite', or 'auto'

SQLITE_PATH = os.path.join(BASE_DIR, "wattwise.db")

# Global engine state
_active_engine = "mysql" if PREFERRED_ENGINE == "mysql" else "sqlite"
_connection_status = {
    "engine": "mysql",
    "mysql_available": False,
    "mysql_error": None,
    "active_db": f"MySQL ({MYSQL_USER}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB})",
    "is_connected": False
}


def _sqlite_date_format(val, fmt: str) -> Optional[str]:
    """Compatibility function for MySQL DATE_FORMAT in SQLite"""
    if val is None:
        return None
    try:
        s = str(val)[:10]
        dt = datetime.strptime(s, "%Y-%m-%d")
        py_fmt = fmt.replace("%%Y", "%Y").replace("%%m", "%m").replace("%%d", "%d").replace("%Y", "%Y").replace("%m", "%m").replace("%d", "%d")
        return dt.strftime(py_fmt)
    except Exception:
        return str(val)


def _sqlite_if(condition, true_val, false_val):
    """Compatibility function for MySQL IF(cond, a, b) in SQLite"""
    return true_val if condition else false_val


def get_sqlite_connection(db_path: str = SQLITE_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.create_function("IF", 3, _sqlite_if)
    conn.create_function("DATE_FORMAT", 2, _sqlite_date_format)
    conn.create_function("date_format", 2, _sqlite_date_format)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _test_mysql_connection() -> Tuple[bool, Optional[str]]:
    """Tests if MySQL is reachable with current credentials and ensures database exists."""
    try:
        import pymysql
        # 1. Connect to MySQL server
        conn = pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            charset="utf8mb4",
            connect_timeout=4
        )
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        conn.close()

        # 2. Verify direct database connection
        conn2 = pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DB,
            charset="utf8mb4",
            connect_timeout=4
        )
        conn2.close()
        return True, None
    except Exception as exc:
        err_str = str(exc)
        if MYSQL_PASSWORD:
            err_str = err_str.replace(MYSQL_PASSWORD, "***")
        return False, err_str


def determine_engine():
    """Detects available database engine."""
    global _active_engine, _connection_status
    
    if PREFERRED_ENGINE == "sqlite":
        _active_engine = "sqlite"
        _connection_status = {
            "engine": "sqlite",
            "mysql_available": False,
            "mysql_error": "SQLite forced by DB_ENGINE configuration",
            "active_db": SQLITE_PATH,
            "is_connected": True
        }
        return "sqlite"

    # Attempt MySQL
    is_ok, err = _test_mysql_connection()
    if is_ok:
        _active_engine = "mysql"
        _connection_status = {
            "engine": "mysql",
            "mysql_available": True,
            "mysql_error": None,
            "active_db": f"MySQL ({MYSQL_USER}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB})",
            "is_connected": True
        }
        return "mysql"
    else:
        if PREFERRED_ENGINE == "mysql":
            # If user explicitly requested mysql, do not silently fallback
            _active_engine = "mysql"
            _connection_status = {
                "engine": "mysql",
                "mysql_available": False,
                "mysql_error": err,
                "active_db": f"MySQL ({MYSQL_USER}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB})",
                "is_connected": False
            }
            raise ConnectionError(f"Failed to connect to MySQL: {err}")
        else:
            _active_engine = "sqlite"
            _connection_status = {
                "engine": "sqlite",
                "mysql_available": False,
                "mysql_error": err,
                "active_db": "wattwise.db",
                "is_connected": True
            }
            return "sqlite"


def get_db_status() -> Dict[str, Any]:
    global _connection_status
    return _connection_status


def get_connection():
    global _active_engine
    if _active_engine == "mysql":
        import pymysql
        from pymysql.cursors import DictCursor
        return pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DB,
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=True
        )
    else:
        return get_sqlite_connection()


def _adapt_query_for_sqlite(sql: str) -> str:
    """Replaces MySQL %s placeholders with SQLite ? placeholders."""
    parts = sql.split("%%")
    transformed = []
    for part in parts:
        transformed.append(part.replace("%s", "?"))
    return "%".join(transformed)


def _normalize_params_for_sqlite(params: tuple) -> tuple:
    """Converts date/datetime parameters to ISO strings to avoid Python 3.12 deprecation warnings."""
    if not params:
        return ()
    normalized = []
    for p in params:
        if isinstance(p, (date, datetime)):
            normalized.append(p.isoformat())
        else:
            normalized.append(p)
    return tuple(normalized)


def query_all(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    global _active_engine
    conn = get_connection()
    try:
        if _active_engine == "mysql":
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                result = []
                for r in rows:
                    row_dict = {}
                    for k, val in r.items():
                        if isinstance(val, Decimal):
                            val = float(val)
                        row_dict[k] = val
                    result.append(row_dict)
                return result
        else:
            adapted_sql = _adapt_query_for_sqlite(sql)
            sqlite_params = _normalize_params_for_sqlite(params)
            cur = conn.cursor()
            cur.execute(adapted_sql, sqlite_params)
            rows = cur.fetchall()
            result = []
            for r in rows:
                row_dict = {}
                for k in r.keys():
                    val = r[k]
                    if isinstance(val, Decimal):
                        val = float(val)
                    row_dict[k] = val
                result.append(row_dict)
            return result
    finally:
        conn.close()


def query_one(sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    rows = query_all(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple = ()) -> int:
    global _active_engine
    conn = get_connection()
    try:
        if _active_engine == "mysql":
            with conn.cursor() as cur:
                cur.execute(sql, params)
                last_id = cur.lastrowid
            conn.commit()
            return last_id
        else:
            adapted_sql = _adapt_query_for_sqlite(sql)
            sqlite_params = _normalize_params_for_sqlite(params)
            cur = conn.cursor()
            cur.execute(adapted_sql, sqlite_params)
            last_id = cur.lastrowid
            conn.commit()
            return last_id
    finally:
        conn.close()


def schema_ready() -> bool:
    try:
        res = query_one("SELECT COUNT(*) AS n FROM consumers")
        return res is not None
    except Exception:
        return False


def init_sqlite_tables(db_path: str = SQLITE_PATH):
    """Creates SQLite schema matching MySQL tables and constraints."""
    conn = get_sqlite_connection(db_path)
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS consumers (
        consumer_id INTEGER PRIMARY KEY AUTOINCREMENT,
        consumer_name TEXT NOT NULL,
        consumer_type TEXT NOT NULL DEFAULT 'Residential' CHECK(consumer_type IN ('Residential','Commercial','Industrial','Agricultural','Other')),
        region TEXT NOT NULL,
        phone TEXT NULL,
        email TEXT NULL,
        status TEXT NOT NULL DEFAULT 'Active' CHECK(status IN ('Active','Inactive')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_consumers_region ON consumers(region);
    CREATE INDEX IF NOT EXISTS idx_consumers_status ON consumers(status);

    CREATE TABLE IF NOT EXISTS meters (
        meter_id INTEGER PRIMARY KEY AUTOINCREMENT,
        consumer_id INTEGER NOT NULL,
        meter_code TEXT NOT NULL UNIQUE,
        meter_capacity REAL NULL,
        status TEXT NOT NULL DEFAULT 'Active' CHECK(status IN ('Active','Inactive')),
        installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (consumer_id) REFERENCES consumers(consumer_id) ON UPDATE CASCADE ON DELETE RESTRICT
    );

    CREATE INDEX IF NOT EXISTS idx_meters_consumer ON meters(consumer_id);

    CREATE TABLE IF NOT EXISTS meter_readings (
        reading_id INTEGER PRIMARY KEY AUTOINCREMENT,
        meter_id INTEGER NOT NULL,
        reading_date TEXT NOT NULL,
        cumulative_kwh REAL NOT NULL CHECK (cumulative_kwh >= 0),
        consumption_kwh REAL NULL,
        notes TEXT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (meter_id) REFERENCES meters(meter_id) ON UPDATE CASCADE ON DELETE RESTRICT,
        UNIQUE (meter_id, reading_date)
    );

    CREATE INDEX IF NOT EXISTS idx_readings_date ON meter_readings(reading_date);
    CREATE INDEX IF NOT EXISTS idx_readings_meter_date ON meter_readings(meter_id, reading_date);

    CREATE TABLE IF NOT EXISTS system_settings (
        setting_key TEXT PRIMARY KEY,
        setting_value TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    INSERT OR IGNORE INTO system_settings (setting_key, setting_value)
    VALUES ('high_usage_threshold', '500');
    """)
    conn.commit()
    conn.close()


# Initialize engine on module load
determine_engine()
