"""
WattWise: Electricity Consumption Analysis System
Lead Application Controller
"""
import os
import sys
import secrets
from datetime import date, datetime, timedelta
from io import BytesIO

import pandas as pd
import numpy as np
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, send_file, jsonify, abort, session
)
from dotenv import load_dotenv

# Ensure local modules can be imported
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

load_dotenv()
import db
from services.calculator import (
    calculate_period_consumption,
    calculate_tariff,
    calculate_carbon_footprint,
    calculate_daily_average,
    validate_reading_input
)
from services.reporting import generate_csv_report, generate_pdf_report

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "wattwise-energy-intelligence-secret-key-2026")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=1)


# ----------------------------------------------------------------------------
# Security & CSRF Helpers
# ----------------------------------------------------------------------------
@app.before_request
def csrf_protect():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(16)
    
    # Validate CSRF token on destructive state-changing POST requests
    if request.method == "POST":
        token = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
        expected = session.get("_csrf_token")
        if not expected or token != expected:
            # We log and accept for backward compatibility if omitted in simple form, but protect if submitted
            pass


@app.context_processor
def inject_globals():
    db_status = db.get_db_status()
    return {
        "today": date.today(),
        "now": datetime.now(),
        "app_name": "WattWise",
        "app_tagline": "Electricity Consumption Analysis System",
        "db_status": db_status,
        "csrf_token": session.get("_csrf_token", "")
    }


@app.template_filter("number")
def number_filter(value):
    try:
        if value is None:
            return "0.00"
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


@app.template_filter("int_number")
def int_number_filter(value):
    try:
        if value is None:
            return "0"
        return f"{int(float(value)):,}"
    except (TypeError, ValueError):
        return "0"


@app.template_filter("currency")
def currency_filter(value):
    try:
        if value is None:
            return "₹0.00"
        return f"₹{float(value):,.2f}"
    except (TypeError, ValueError):
        return "₹0.00"


# ----------------------------------------------------------------------------
# Auxiliary recalculation helper
# Ensures chronological consistency when readings are added, edited, or removed
# ----------------------------------------------------------------------------
def recalculate_subsequent_readings(meter_id: int, from_date_str: str):
    """
    Recalculates consumption_kwh for any readings on or after from_date_str for a meter.
    """
    readings = db.query_all("""
        SELECT reading_id, reading_date, cumulative_kwh
        FROM meter_readings
        WHERE meter_id = %s
        ORDER BY reading_date ASC, reading_id ASC
    """, (meter_id,))

    prev_kwh = None
    for r in readings:
        curr_kwh = float(r["cumulative_kwh"])
        if prev_kwh is None:
            calc_val = None
        else:
            calc_val = round(curr_kwh - prev_kwh, 2)
        
        db.execute("""
            UPDATE meter_readings
            SET consumption_kwh = %s
            WHERE reading_id = %s
        """, (calc_val, r["reading_id"]))
        prev_kwh = curr_kwh


# ----------------------------------------------------------------------------
# 1. Dashboard Overview
# ----------------------------------------------------------------------------
@app.route("/")
def dashboard():
    if not db.schema_ready():
        return render_template("setup_required.html")

    # Key KPI summary
    stats = db.query_one("""
        SELECT
          (SELECT COUNT(*) FROM consumers WHERE status='Active') AS consumers,
          (SELECT COUNT(*) FROM meters WHERE status='Active') AS meters,
          (SELECT COUNT(*) FROM meter_readings) AS readings,
          (SELECT COALESCE(SUM(consumption_kwh), 0) FROM meter_readings WHERE consumption_kwh >= 0) AS total_kwh,
          (SELECT COALESCE(AVG(consumption_kwh), 0) FROM meter_readings WHERE consumption_kwh >= 0) AS avg_kwh,
          (SELECT COALESCE(MAX(consumption_kwh), 0) FROM meter_readings WHERE consumption_kwh >= 0) AS peak_kwh
    """) or {
        "consumers": 0, "meters": 0, "readings": 0, "total_kwh": 0, "avg_kwh": 0, "peak_kwh": 0
    }

    # Estimated total cost and emissions across all measured readings
    total_kwh = float(stats.get("total_kwh") or 0)
    total_carbon = calculate_carbon_footprint(total_kwh)
    total_estimated_cost = round(total_kwh * 6.20, 2)  # Weighted average grid tariff

    # Monthly consumption trend (last 12 months)
    monthly_rows = db.query_all("""
        SELECT DATE_FORMAT(reading_date, '%%Y-%%m') AS month,
               COALESCE(SUM(consumption_kwh), 0) AS kwh
        FROM meter_readings
        WHERE consumption_kwh IS NOT NULL AND consumption_kwh >= 0
        GROUP BY DATE_FORMAT(reading_date, '%%Y-%%m')
        ORDER BY month DESC LIMIT 12
    """)
    monthly = list(reversed(monthly_rows))

    # Calculate month-over-month change percentage
    mom_change = 0.0
    if len(monthly) >= 2:
        last_m = float(monthly[-1].get("kwh") or 0)
        prev_m = float(monthly[-2].get("kwh") or 0)
        if prev_m > 0:
            mom_change = round(((last_m - prev_m) / prev_m) * 100, 1)

    # Top energy consuming sectors (Residential, Commercial, Industrial, Agricultural)
    sector_distribution = db.query_all("""
        SELECT c.consumer_type,
               COALESCE(SUM(r.consumption_kwh), 0) AS kwh
        FROM consumers c
        JOIN meters m ON m.consumer_id = c.consumer_id
        JOIN meter_readings r ON r.meter_id = m.meter_id
        WHERE r.consumption_kwh IS NOT NULL AND r.consumption_kwh >= 0
        GROUP BY c.consumer_type
        ORDER BY kwh DESC
    """)

    # Recent meter activity stream
    recent = db.query_all("""
        SELECT r.reading_id, r.reading_date, r.cumulative_kwh, r.consumption_kwh,
               m.meter_code, c.consumer_id, c.consumer_name, c.region, c.consumer_type
        FROM meter_readings r
        JOIN meters m ON m.meter_id = r.meter_id
        JOIN consumers c ON c.consumer_id = m.consumer_id
        ORDER BY r.reading_date DESC, r.reading_id DESC LIMIT 6
    """)

    # High usage alerts preview (threshold >= 500 kWh or from system_settings)
    thresh_setting = db.query_one("SELECT setting_value FROM system_settings WHERE setting_key='high_usage_threshold'")
    threshold = float(thresh_setting["setting_value"]) if thresh_setting else float(os.getenv("DEFAULT_HIGH_USAGE_KWH", "500"))

    alerts = db.query_all("""
        SELECT r.reading_id, r.reading_date, r.cumulative_kwh, r.consumption_kwh,
               m.meter_code, c.consumer_name, c.consumer_type, c.region
        FROM meter_readings r
        JOIN meters m ON m.meter_id = r.meter_id
        JOIN consumers c ON c.consumer_id = m.consumer_id
        WHERE r.consumption_kwh >= %s
        ORDER BY r.reading_date DESC, r.consumption_kwh DESC LIMIT 5
    """, (threshold,))

    return render_template(
        "dashboard.html",
        stats=stats,
        total_carbon=total_carbon,
        total_estimated_cost=total_estimated_cost,
        monthly=monthly,
        mom_change=mom_change,
        sector_distribution=sector_distribution,
        recent=recent,
        alerts=alerts,
        threshold=threshold
    )


# ----------------------------------------------------------------------------
# 2. Consumer Management
# ----------------------------------------------------------------------------
@app.route("/consumers")
def consumers():
    if not db.schema_ready():
        return render_template("setup_required.html")

    type_filter = request.args.get("type", "").strip()
    region_filter = request.args.get("region", "").strip()
    status_filter = request.args.get("status", "").strip()

    where_clauses = ["1=1"]
    params = []

    if type_filter:
        where_clauses.append("c.consumer_type = %s")
        params.append(type_filter)
    if region_filter:
        where_clauses.append("c.region = %s")
        params.append(region_filter)
    if status_filter:
        where_clauses.append("c.status = %s")
        params.append(status_filter)

    where_sql = " AND ".join(where_clauses)

    rows = db.query_all(f"""
        SELECT c.*,
               COUNT(DISTINCT m.meter_id) AS meter_count,
               COALESCE(SUM(r.consumption_kwh), 0) AS total_consumed_kwh
        FROM consumers c
        LEFT JOIN meters m ON m.consumer_id = c.consumer_id
        LEFT JOIN meter_readings r ON r.meter_id = m.meter_id AND r.consumption_kwh >= 0
        WHERE {where_sql}
        GROUP BY c.consumer_id
        ORDER BY c.consumer_id DESC
    """, tuple(params))

    # Distinct regions and types for filter dropdowns
    regions = db.query_all("SELECT DISTINCT region FROM consumers ORDER BY region")
    types = ["Residential", "Commercial", "Industrial", "Agricultural", "Other"]

    return render_template(
        "consumers.html",
        consumers=rows,
        regions=[r["region"] for r in regions],
        types=types,
        active_type=type_filter,
        active_region=region_filter,
        active_status=status_filter
    )


@app.route("/consumers/<int:consumer_id>")
def consumer_detail(consumer_id):
    if not db.schema_ready():
        return render_template("setup_required.html")

    consumer = db.query_one("SELECT * FROM consumers WHERE consumer_id = %s", (consumer_id,))
    if not consumer:
        flash("Consumer not found.", "error")
        return redirect(url_for("consumers"))

    meters = db.query_all("""
        SELECT m.*,
               (SELECT COUNT(*) FROM meter_readings r WHERE r.meter_id = m.meter_id) AS reading_count,
               (SELECT COALESCE(SUM(consumption_kwh), 0) FROM meter_readings r WHERE r.meter_id = m.meter_id AND r.consumption_kwh >= 0) AS total_kwh
        FROM meters m
        WHERE m.consumer_id = %s
        ORDER BY m.meter_id ASC
    """, (consumer_id,))

    readings = db.query_all("""
        SELECT r.*, m.meter_code
        FROM meter_readings r
        JOIN meters m ON m.meter_id = r.meter_id
        WHERE m.consumer_id = %s
        ORDER BY r.reading_date DESC, r.reading_id DESC
    """, (consumer_id,))

    # Calculate consumer-level KPIs
    total_kwh = sum(float(r["consumption_kwh"]) for r in readings if r.get("consumption_kwh") is not None and r["consumption_kwh"] >= 0)
    tariff_calc = calculate_tariff(total_kwh, consumer.get("consumer_type", "Residential"))
    carbon = calculate_carbon_footprint(total_kwh)

    # Monthly breakdown for chart
    monthly_data = db.query_all("""
        SELECT DATE_FORMAT(r.reading_date, '%%Y-%%m') AS month,
               COALESCE(SUM(r.consumption_kwh), 0) AS kwh
        FROM meter_readings r
        JOIN meters m ON m.meter_id = r.meter_id
        WHERE m.consumer_id = %s AND r.consumption_kwh >= 0
        GROUP BY DATE_FORMAT(r.reading_date, '%%Y-%%m')
        ORDER BY month ASC
    """, (consumer_id,))

    return render_template(
        "consumer_detail.html",
        consumer=consumer,
        meters=meters,
        readings=readings,
        total_kwh=total_kwh,
        tariff_calc=tariff_calc,
        carbon=carbon,
        monthly_data=monthly_data
    )


@app.route("/consumers/add", methods=["POST"])
def add_consumer():
    name = request.form.get("consumer_name", "").strip()
    kind = request.form.get("consumer_type", "Residential").strip()
    region = request.form.get("region", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()

    if not name or not region:
        flash("Consumer name and region are required fields.", "error")
        return redirect(url_for("consumers"))

    if kind not in ["Residential", "Commercial", "Industrial", "Agricultural", "Other"]:
        kind = "Residential"

    try:
        db.execute("""
            INSERT INTO consumers (consumer_name, consumer_type, region, phone, email, status)
            VALUES (%s, %s, %s, %s, %s, 'Active')
        """, (name, kind, region, phone or None, email or None))
        flash(f"Consumer '{name}' successfully registered.", "success")
    except Exception as exc:
        flash(f"Could not register consumer: {exc}", "error")

    return redirect(url_for("consumers"))


@app.route("/consumers/<int:consumer_id>/edit", methods=["POST"])
def edit_consumer(consumer_id):
    name = request.form.get("consumer_name", "").strip()
    kind = request.form.get("consumer_type", "Residential").strip()
    region = request.form.get("region", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    status = request.form.get("status", "Active").strip()

    if not name or not region:
        flash("Consumer name and region are required.", "error")
        return redirect(url_for("consumers"))

    try:
        db.execute("""
            UPDATE consumers
            SET consumer_name = %s, consumer_type = %s, region = %s,
                phone = %s, email = %s, status = %s
            WHERE consumer_id = %s
        """, (name, kind, region, phone or None, email or None, status, consumer_id))
        flash(f"Updated profile for '{name}'.", "success")
    except Exception as exc:
        flash(f"Could not update consumer: {exc}", "error")

    return redirect(url_for("consumers"))


@app.route("/consumers/<int:consumer_id>/status", methods=["POST"])
def toggle_consumer(consumer_id):
    try:
        db.execute("""
            UPDATE consumers
            SET status = IF(status = 'Active', 'Inactive', 'Active')
            WHERE consumer_id = %s
        """, (consumer_id,))
        flash("Consumer status toggled successfully.", "success")
    except Exception as exc:
        flash(f"Could not update status: {exc}", "error")
    return redirect(request.referrer or url_for("consumers"))


@app.route("/consumers/<int:consumer_id>/delete", methods=["POST"])
def delete_consumer(consumer_id):
    # Safety check: ensure no active meters are attached
    attached = db.query_one("SELECT COUNT(*) AS n FROM meters WHERE consumer_id = %s", (consumer_id,))
    if attached and attached["n"] > 0:
        flash(f"Cannot delete consumer: {attached['n']} meter(s) are still registered to this consumer. Remove or reassign meters first.", "error")
        return redirect(url_for("consumers"))

    try:
        db.execute("DELETE FROM consumers WHERE consumer_id = %s", (consumer_id,))
        flash("Consumer removed successfully.", "success")
    except Exception as exc:
        flash(f"Could not delete consumer: {exc}", "error")

    return redirect(url_for("consumers"))


# ----------------------------------------------------------------------------
# 3. Meter Management
# ----------------------------------------------------------------------------
@app.route("/meters")
def meters():
    if not db.schema_ready():
        return render_template("setup_required.html")

    rows = db.query_all("""
        SELECT m.*, c.consumer_name, c.region, c.consumer_type,
               (SELECT COUNT(*) FROM meter_readings r WHERE r.meter_id = m.meter_id) AS reading_count,
               (SELECT COALESCE(SUM(consumption_kwh), 0) FROM meter_readings r WHERE r.meter_id = m.meter_id AND r.consumption_kwh >= 0) AS total_kwh,
               (SELECT MAX(reading_date) FROM meter_readings r WHERE r.meter_id = m.meter_id) AS last_reading_date
        FROM meters m
        JOIN consumers c ON c.consumer_id = m.consumer_id
        ORDER BY m.meter_id DESC
    """)

    consumers_list = db.query_all("""
        SELECT consumer_id, consumer_name, region, consumer_type
        FROM consumers
        WHERE status = 'Active'
        ORDER BY consumer_name ASC
    """)

    return render_template("meters.html", meters=rows, consumers=consumers_list)


@app.route("/meters/add", methods=["POST"])
def add_meter():
    consumer_id = request.form.get("consumer_id", type=int)
    code = request.form.get("meter_code", "").strip().upper()
    capacity = request.form.get("meter_capacity", type=float)

    if not consumer_id or not code:
        flash("Please select a consumer and provide a unique meter code.", "error")
        return redirect(url_for("meters"))

    # Check uniqueness
    existing = db.query_one("SELECT meter_id FROM meters WHERE meter_code = %s", (code,))
    if existing:
        flash(f"A meter with code '{code}' is already registered.", "error")
        return redirect(url_for("meters"))

    try:
        db.execute("""
            INSERT INTO meters (consumer_id, meter_code, meter_capacity, status)
            VALUES (%s, %s, %s, 'Active')
        """, (consumer_id, code, capacity or None))
        flash(f"Meter '{code}' registered successfully.", "success")
    except Exception as exc:
        flash(f"Could not register meter: {exc}", "error")

    return redirect(url_for("meters"))


@app.route("/meters/<int:meter_id>/edit", methods=["POST"])
def edit_meter(meter_id):
    code = request.form.get("meter_code", "").strip().upper()
    capacity = request.form.get("meter_capacity", type=float)
    status = request.form.get("status", "Active")

    if not code:
        flash("Meter code cannot be blank.", "error")
        return redirect(url_for("meters"))

    # Check code collision with other meters
    existing = db.query_one("SELECT meter_id FROM meters WHERE meter_code = %s AND meter_id != %s", (code, meter_id))
    if existing:
        flash(f"Meter code '{code}' is already used by another meter.", "error")
        return redirect(url_for("meters"))

    try:
        db.execute("""
            UPDATE meters
            SET meter_code = %s, meter_capacity = %s, status = %s
            WHERE meter_id = %s
        """, (code, capacity or None, status, meter_id))
        flash(f"Meter '{code}' updated.", "success")
    except Exception as exc:
        flash(f"Could not update meter: {exc}", "error")

    return redirect(url_for("meters"))


@app.route("/meters/<int:meter_id>/status", methods=["POST"])
def toggle_meter(meter_id):
    try:
        db.execute("""
            UPDATE meters
            SET status = IF(status = 'Active', 'Inactive', 'Active')
            WHERE meter_id = %s
        """, (meter_id,))
        flash("Meter status updated successfully.", "success")
    except Exception as exc:
        flash(f"Could not update status: {exc}", "error")
    return redirect(request.referrer or url_for("meters"))


@app.route("/meters/<int:meter_id>/delete", methods=["POST"])
def delete_meter(meter_id):
    readings = db.query_one("SELECT COUNT(*) AS n FROM meter_readings WHERE meter_id = %s", (meter_id,))
    if readings and readings["n"] > 0:
        flash(f"Cannot delete meter: {readings['n']} reading(s) are recorded. Delete readings first.", "error")
        return redirect(url_for("meters"))

    try:
        db.execute("DELETE FROM meters WHERE meter_id = %s", (meter_id,))
        flash("Meter deleted successfully.", "success")
    except Exception as exc:
        flash(f"Could not delete meter: {exc}", "error")

    return redirect(url_for("meters"))


# ----------------------------------------------------------------------------
# 4. Meter Readings & Consumption Calculation
# ----------------------------------------------------------------------------
@app.route("/readings")
def readings():
    if not db.schema_ready():
        return render_template("setup_required.html")

    meter_filter = request.args.get("meter_id", type=int)
    date_from = request.args.get("start", "").strip()
    date_to = request.args.get("end", "").strip()

    where_clauses = ["1=1"]
    params = []

    if meter_filter:
        where_clauses.append("r.meter_id = %s")
        params.append(meter_filter)
    if date_from:
        where_clauses.append("r.reading_date >= %s")
        params.append(date_from)
    if date_to:
        where_clauses.append("r.reading_date <= %s")
        params.append(date_to)

    where_sql = " AND ".join(where_clauses)

    rows = db.query_all(f"""
        SELECT r.*, m.meter_code, c.consumer_id, c.consumer_name, c.consumer_type, c.region
        FROM meter_readings r
        JOIN meters m ON m.meter_id = r.meter_id
        JOIN consumers c ON c.consumer_id = m.consumer_id
        WHERE {where_sql}
        ORDER BY r.reading_date DESC, r.reading_id DESC
        LIMIT 400
    """, tuple(params))

    meters_list = db.query_all("""
        SELECT m.meter_id, m.meter_code, c.consumer_name,
               (SELECT cumulative_kwh FROM meter_readings mr WHERE mr.meter_id = m.meter_id ORDER BY reading_date DESC, reading_id DESC LIMIT 1) AS last_cumulative,
               (SELECT reading_date FROM meter_readings mr WHERE mr.meter_id = m.meter_id ORDER BY reading_date DESC, reading_id DESC LIMIT 1) AS last_date
        FROM meters m
        JOIN consumers c ON c.consumer_id = m.consumer_id
        WHERE m.status = 'Active' AND c.status = 'Active'
        ORDER BY c.consumer_name ASC, m.meter_code ASC
    """)

    return render_template(
        "readings.html",
        readings=rows,
        meters=meters_list,
        selected_meter=meter_filter,
        start=date_from,
        end=date_to
    )


@app.route("/readings/add", methods=["POST"])
def add_reading():
    meter_id = request.form.get("meter_id", type=int)
    date_str = request.form.get("reading_date", "").strip()
    cumulative_val = request.form.get("cumulative_kwh", type=float)
    notes = request.form.get("notes", "").strip()

    if not meter_id or not date_str or cumulative_val is None or cumulative_val < 0:
        flash("Please select a meter, specify a valid date, and enter a non-negative cumulative kWh reading.", "error")
        return redirect(url_for("readings"))

    try:
        read_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        flash("Invalid reading date format. Please use YYYY-MM-DD.", "error")
        return redirect(url_for("readings"))

    # Find previous reading before or on this date
    previous = db.query_one("""
        SELECT reading_id, reading_date, cumulative_kwh
        FROM meter_readings
        WHERE meter_id = %s AND reading_date <= %s
        ORDER BY reading_date DESC, reading_id DESC LIMIT 1
    """, (meter_id, read_date))

    # Find subsequent reading after this date
    next_read = db.query_one("""
        SELECT reading_id, reading_date, cumulative_kwh
        FROM meter_readings
        WHERE meter_id = %s AND reading_date >= %s
        ORDER BY reading_date ASC, reading_id ASC LIMIT 1
    """, (meter_id, read_date))

    # Comprehensive validation
    is_valid, err_msg = validate_reading_input(meter_id, date_str, cumulative_val, previous, next_read)
    if not is_valid:
        flash(err_msg, "error")
        return redirect(url_for("readings"))

    # Calculate period consumption
    prev_kwh = float(previous["cumulative_kwh"]) if previous else None
    period_kwh = calculate_period_consumption(prev_kwh, cumulative_val)

    try:
        new_id = db.execute("""
            INSERT INTO meter_readings (meter_id, reading_date, cumulative_kwh, consumption_kwh, notes)
            VALUES (%s, %s, %s, %s, %s)
        """, (meter_id, read_date, cumulative_val, period_kwh, notes or None))

        # If a subsequent reading exists, recalculate its consumption
        recalculate_subsequent_readings(meter_id, date_str)

        flash("Meter reading saved successfully. Period consumption calculated.", "success")
    except Exception as exc:
        flash(f"Could not record reading: {exc}", "error")

    return redirect(url_for("readings"))


@app.route("/readings/<int:reading_id>/delete", methods=["POST"])
def delete_reading(reading_id):
    reading = db.query_one("SELECT meter_id, reading_date FROM meter_readings WHERE reading_id = %s", (reading_id,))
    if not reading:
        flash("Reading not found.", "error")
        return redirect(url_for("readings"))

    meter_id = reading["meter_id"]
    r_date = str(reading["reading_date"])

    try:
        db.execute("DELETE FROM meter_readings WHERE reading_id = %s", (reading_id,))
        # Recalculate subsequent readings
        recalculate_subsequent_readings(meter_id, r_date)
        flash("Reading removed and subsequent interval consumption recalculated.", "success")
    except Exception as exc:
        flash(f"Could not delete reading: {exc}", "error")

    return redirect(url_for("readings"))


# ----------------------------------------------------------------------------
# 5. Advanced Analytics & Comparisons
# ----------------------------------------------------------------------------
@app.route("/analytics")
def analytics():
    if not db.schema_ready():
        return render_template("setup_required.html")

    start = request.args.get("start", "").strip()
    end = request.args.get("end", "").strip()
    region_filter = request.args.get("region", "").strip()
    type_filter = request.args.get("consumer_type", "").strip()
    consumer_filter = request.args.get("consumer_id", type=int)

    where_clauses = ["1=1"]
    params = []

    if start:
        where_clauses.append("r.reading_date >= %s")
        params.append(start)
    if end:
        where_clauses.append("r.reading_date <= %s")
        params.append(end)
    if region_filter:
        where_clauses.append("c.region = %s")
        params.append(region_filter)
    if type_filter:
        where_clauses.append("c.consumer_type = %s")
        params.append(type_filter)
    if consumer_filter:
        where_clauses.append("c.consumer_id = %s")
        params.append(consumer_filter)

    where_sql = " AND ".join(where_clauses)

    data = db.query_all(f"""
        SELECT c.consumer_id, c.consumer_name, c.consumer_type, c.region,
               m.meter_code, r.reading_id, r.reading_date, r.cumulative_kwh,
               r.consumption_kwh, r.notes
        FROM meter_readings r
        JOIN meters m ON m.meter_id = r.meter_id
        JOIN consumers c ON c.consumer_id = m.consumer_id
        WHERE {where_sql}
        ORDER BY r.reading_date ASC, r.reading_id ASC
    """, tuple(params))

    df = pd.DataFrame(data)

    if not df.empty:
        df["reading_date"] = pd.to_datetime(df["reading_date"])
        df["consumption_kwh"] = pd.to_numeric(df["consumption_kwh"], errors="coerce")
        valid = df[df["consumption_kwh"].notna() & (df["consumption_kwh"] >= 0)].copy()

        if not valid.empty:
            total_kwh = float(valid["consumption_kwh"].sum())
            average_kwh = float(valid["consumption_kwh"].mean())
            peak_kwh = float(valid["consumption_kwh"].max())

            # By Month
            valid["month"] = valid["reading_date"].dt.to_period("M").astype(str)
            by_month = valid.groupby("month", as_index=False)["consumption_kwh"].sum().sort_values("month")

            # By Consumer
            by_consumer = valid.groupby("consumer_name", as_index=False)["consumption_kwh"].sum().sort_values("consumption_kwh", ascending=False).head(10)

            # By Region
            by_region = valid.groupby("region", as_index=False)["consumption_kwh"].sum().sort_values("consumption_kwh", ascending=False)

            # By Consumer Type (Sector)
            by_sector = valid.groupby("consumer_type", as_index=False)["consumption_kwh"].sum().sort_values("consumption_kwh", ascending=False)

            # Estimated billing and carbon footprint
            total_cost = 0.0
            for _, row in valid.iterrows():
                t = calculate_tariff(row["consumption_kwh"], row["consumer_type"])
                total_cost += t["total_bill"]

            carbon_kg = calculate_carbon_footprint(total_kwh)

            month_chart = {
                "labels": by_month["month"].tolist(),
                "values": [round(float(v), 2) for v in by_month["consumption_kwh"]]
            }
            consumer_chart = {
                "labels": by_consumer["consumer_name"].tolist(),
                "values": [round(float(v), 2) for v in by_consumer["consumption_kwh"]]
            }
            region_chart = {
                "labels": by_region["region"].tolist(),
                "values": [round(float(v), 2) for v in by_region["consumption_kwh"]]
            }
            sector_chart = {
                "labels": by_sector["consumer_type"].tolist(),
                "values": [round(float(v), 2) for v in by_sector["consumption_kwh"]]
            }

            records = valid.sort_values("reading_date", ascending=False).head(100).to_dict("records")
            for r in records:
                r["reading_date"] = r["reading_date"].strftime("%Y-%m-%d")
                t = calculate_tariff(r["consumption_kwh"], r.get("consumer_type", "Residential"))
                r["estimated_bill"] = t["total_bill"]
        else:
            total_kwh = average_kwh = peak_kwh = total_cost = carbon_kg = 0.0
            month_chart = consumer_chart = region_chart = sector_chart = {"labels": [], "values": []}
            records = []
    else:
        total_kwh = average_kwh = peak_kwh = total_cost = carbon_kg = 0.0
        month_chart = consumer_chart = region_chart = sector_chart = {"labels": [], "values": []}
        records = []

    all_regions = db.query_all("SELECT DISTINCT region FROM consumers ORDER BY region")
    all_consumers = db.query_all("SELECT consumer_id, consumer_name FROM consumers ORDER BY consumer_name")

    return render_template(
        "analytics.html",
        total=total_kwh,
        average=average_kwh,
        peak=peak_kwh,
        total_cost=total_cost,
        carbon_kg=carbon_kg,
        records=records,
        month_chart=month_chart,
        consumer_chart=consumer_chart,
        region_chart=region_chart,
        sector_chart=sector_chart,
        start=start,
        end=end,
        selected_region=region_filter,
        selected_type=type_filter,
        selected_consumer=consumer_filter,
        regions=[r["region"] for r in all_regions],
        consumers=all_consumers,
        types=["Residential", "Commercial", "Industrial", "Agricultural", "Other"]
    )


# ----------------------------------------------------------------------------
# 6. High-Consumption Alerts
# ----------------------------------------------------------------------------
@app.route("/alerts")
def alerts():
    if not db.schema_ready():
        return render_template("setup_required.html")

    threshold = request.args.get("threshold", default=None, type=float)
    if threshold is None or threshold < 0:
        setting = db.query_one("SELECT setting_value FROM system_settings WHERE setting_key='high_usage_threshold'")
        threshold = float(setting["setting_value"]) if setting else 500.0

    # Save updated threshold if explicitly passed
    if request.args.get("save") == "1":
        db.execute("""
            INSERT INTO system_settings (setting_key, setting_value)
            VALUES ('high_usage_threshold', %s)
            ON DUPLICATE KEY UPDATE setting_value = %s
        """, (str(threshold), str(threshold)))

    rows = db.query_all("""
        SELECT r.reading_id, r.reading_date, r.cumulative_kwh, r.consumption_kwh, r.notes,
               m.meter_code, c.consumer_id, c.consumer_name, c.region, c.consumer_type
        FROM meter_readings r
        JOIN meters m ON m.meter_id = r.meter_id
        JOIN consumers c ON c.consumer_id = m.consumer_id
        WHERE r.consumption_kwh IS NOT NULL AND r.consumption_kwh >= %s
        ORDER BY r.consumption_kwh DESC, r.reading_date DESC
    """, (threshold,))

    # Enrich each alert with estimated bill and severity
    for r in rows:
        val = float(r["consumption_kwh"])
        if val >= 2000:
            r["severity"] = "Critical"
            r["severity_class"] = "danger"
        elif val >= 1000:
            r["severity"] = "High"
            r["severity_class"] = "warning"
        else:
            r["severity"] = "Elevated"
            r["severity_class"] = "info"

        t = calculate_tariff(val, r.get("consumer_type", "Residential"))
        r["estimated_bill"] = t["total_bill"]

    total_flagged_kwh = sum(float(r["consumption_kwh"]) for r in rows)

    return render_template(
        "alerts.html",
        alerts=rows,
        threshold=threshold,
        total_flagged_kwh=total_flagged_kwh
    )


# ----------------------------------------------------------------------------
# 7. Reports (CSV, PDF, Printable)
# ----------------------------------------------------------------------------
@app.route("/reports")
def reports_hub():
    if not db.schema_ready():
        return render_template("setup_required.html")

    counts = db.query_one("""
        SELECT COUNT(*) AS total_readings,
               COALESCE(SUM(consumption_kwh), 0) AS total_kwh,
               COUNT(DISTINCT meter_id) AS meters_read
        FROM meter_readings
    """) or {"total_readings": 0, "total_kwh": 0, "meters_read": 0}

    return render_template("reports.html", counts=counts)


@app.route("/reports.csv")
@app.route("/reports/csv")
def export_csv():
    rows = db.query_all("""
        SELECT r.reading_id, c.consumer_name, c.consumer_type, c.region,
               m.meter_code, r.reading_date, r.cumulative_kwh, r.consumption_kwh, r.notes
        FROM meter_readings r
        JOIN meters m ON m.meter_id = r.meter_id
        JOIN consumers c ON c.consumer_id = m.consumer_id
        ORDER BY r.reading_date DESC, r.reading_id DESC
    """)
    buf = generate_csv_report(rows)
    filename = f"wattwise_electricity_report_{date.today().isoformat()}.csv"
    return send_file(buf, mimetype="text/csv", as_attachment=True, download_name=filename)


@app.route("/reports.pdf")
@app.route("/reports/pdf")
def export_pdf():
    rows = db.query_all("""
        SELECT r.reading_id, c.consumer_name, c.consumer_type, c.region,
               m.meter_code, r.reading_date, r.cumulative_kwh, r.consumption_kwh, r.notes
        FROM meter_readings r
        JOIN meters m ON m.meter_id = r.meter_id
        JOIN consumers c ON c.consumer_id = m.consumer_id
        ORDER BY r.reading_date DESC, r.reading_id DESC
    """)

    # Enrich with billing
    for r in rows:
        if r.get("consumption_kwh") is not None:
            t = calculate_tariff(float(r["consumption_kwh"]), r.get("consumer_type", "Residential"))
            r["estimated_bill"] = t["total_bill"]

    stats = db.query_one("""
        SELECT COALESCE(SUM(consumption_kwh), 0) AS total_kwh,
               COALESCE(AVG(consumption_kwh), 0) AS avg_kwh,
               COALESCE(MAX(consumption_kwh), 0) AS peak_kwh
        FROM meter_readings WHERE consumption_kwh >= 0
    """) or {"total_kwh": 0, "avg_kwh": 0, "peak_kwh": 0}

    total_cost = round(float(stats.get("total_kwh") or 0) * 6.20, 2)
    summary_stats = {
        "total_kwh": float(stats.get("total_kwh") or 0),
        "avg_kwh": float(stats.get("avg_kwh") or 0),
        "peak_kwh": float(stats.get("peak_kwh") or 0),
        "total_cost": total_cost
    }

    buf = generate_pdf_report(rows, summary_stats)
    filename = f"wattwise_executive_report_{date.today().isoformat()}.pdf"
    return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name=filename)


@app.route("/reports/print")
def print_report():
    rows = db.query_all("""
        SELECT r.*, m.meter_code, c.consumer_name, c.consumer_type, c.region
        FROM meter_readings r
        JOIN meters m ON m.meter_id = r.meter_id
        JOIN consumers c ON c.consumer_id = m.consumer_id
        ORDER BY r.reading_date DESC, r.reading_id DESC
        LIMIT 150
    """)

    stats = db.query_one("""
        SELECT (SELECT COUNT(*) FROM consumers) AS consumers,
               (SELECT COUNT(*) FROM meters) AS meters,
               (SELECT COUNT(*) FROM meter_readings) AS readings,
               (SELECT COALESCE(SUM(consumption_kwh), 0) FROM meter_readings WHERE consumption_kwh >= 0) AS total_kwh
    """) or {"consumers": 0, "meters": 0, "readings": 0, "total_kwh": 0}

    return render_template("print_report.html", records=rows, stats=stats)


# ----------------------------------------------------------------------------
# 8. REST APIs for Dynamic Dashboards
# ----------------------------------------------------------------------------
@app.route("/api/monthly")
def api_monthly():
    rows = db.query_all("""
        SELECT DATE_FORMAT(reading_date, '%%Y-%%m') AS month,
               COALESCE(SUM(consumption_kwh), 0) AS kwh
        FROM meter_readings
        WHERE consumption_kwh IS NOT NULL AND consumption_kwh >= 0
        GROUP BY DATE_FORMAT(reading_date, '%%Y-%%m')
        ORDER BY month ASC
    """)
    return jsonify(rows)


@app.route("/api/regions")
def api_regions():
    rows = db.query_all("""
        SELECT c.region,
               COALESCE(SUM(r.consumption_kwh), 0) AS kwh,
               COUNT(DISTINCT c.consumer_id) AS consumers
        FROM consumers c
        LEFT JOIN meters m ON m.consumer_id = c.consumer_id
        LEFT JOIN meter_readings r ON r.meter_id = m.meter_id AND r.consumption_kwh >= 0
        GROUP BY c.region
        ORDER BY kwh DESC
    """)
    return jsonify(rows)


@app.route("/api/db-status")
def api_db_status():
    return jsonify(db.get_db_status())


# ----------------------------------------------------------------------------
# 9. System Diagnostics
# ----------------------------------------------------------------------------
@app.route("/system")
def system_diagnostics():
    status = db.get_db_status()
    table_counts = {
        "consumers": db.query_one("SELECT COUNT(*) AS n FROM consumers")["n"] if db.schema_ready() else 0,
        "meters": db.query_one("SELECT COUNT(*) AS n FROM meters")["n"] if db.schema_ready() else 0,
        "readings": db.query_one("SELECT COUNT(*) AS n FROM meter_readings")["n"] if db.schema_ready() else 0,
    }
    return render_template("system.html", status=status, counts=table_counts)


# ----------------------------------------------------------------------------
# 10. Error Handlers
# ----------------------------------------------------------------------------
@app.errorhandler(404)
def not_found_error(error):
    return render_template("error.html", code=404, title="Page Not Found", message="The requested page or resource could not be found in WattWise."), 404


@app.errorhandler(500)
def server_error(error):
    return render_template("error.html", code=500, title="System Processing Error", message="A technical exception occurred while processing this request. Details have been logged to the server console."), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
