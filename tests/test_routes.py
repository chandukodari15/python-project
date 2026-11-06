"""
Functional and Integration tests for WattWise Web Routes.
Tests dashboard, CRUD endpoints, reports, analytics, and error handling.
"""
import db


def test_dashboard_page(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"Electricity Consumption" in res.data


def test_consumer_flow(client):
    """Test adding consumer, listing, and viewing details."""
    # 1. Add consumer
    post_res = client.post("/consumers/add", data={
        "consumer_name": "Integrated Test Facility",
        "consumer_type": "Industrial",
        "region": "Chittoor",
        "phone": "+91 99999 11111",
        "email": "test@integrated.org"
    }, follow_redirects=True)
    assert post_res.status_code == 200
    assert b"Integrated Test Facility" in post_res.data

    # 2. Query consumer ID
    c = db.query_one("SELECT consumer_id FROM consumers WHERE consumer_name = 'Integrated Test Facility'")
    assert c is not None
    cid = c["consumer_id"]

    # 3. View Detail page
    detail_res = client.get(f"/consumers/{cid}")
    assert detail_res.status_code == 200
    assert b"Integrated Test Facility" in detail_res.data

    # 4. Toggle status
    toggle_res = client.post(f"/consumers/{cid}/status", follow_redirects=True)
    assert toggle_res.status_code == 200
    c_updated = db.query_one("SELECT status FROM consumers WHERE consumer_id = %s", (cid,))
    assert c_updated["status"] == "Inactive"


def test_meter_registration_and_toggle(client):
    # Add consumer first
    cid = db.execute("INSERT INTO consumers (consumer_name, region) VALUES ('Meter Owner', 'Tirupati')")
    
    # Register meter
    res = client.post("/meters/add", data={
        "consumer_id": cid,
        "meter_code": "TEST-ROUTE-M1",
        "meter_capacity": 50000
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b"TEST-ROUTE-M1" in res.data

    # Verify in DB
    m = db.query_one("SELECT meter_id, status FROM meters WHERE meter_code = 'TEST-ROUTE-M1'")
    assert m is not None
    assert m["status"] == "Active"


def test_readings_submission_and_validation(client):
    cid = db.execute("INSERT INTO consumers (consumer_name, region) VALUES ('Reading Consumer', 'Nellore')")
    mid = db.execute("INSERT INTO meters (consumer_id, meter_code) VALUES (%s, 'MTR-READ-01')", (cid,))

    # First baseline reading
    r1 = client.post("/readings/add", data={
        "meter_id": mid,
        "reading_date": "2026-01-01",
        "cumulative_kwh": 500.0,
        "notes": "Baseline"
    }, follow_redirects=True)
    assert r1.status_code == 200
    assert b"Meter reading saved successfully" in r1.data

    # Second valid reading: 750 kWh (usage 250)
    r2 = client.post("/readings/add", data={
        "meter_id": mid,
        "reading_date": "2026-02-01",
        "cumulative_kwh": 750.0,
        "notes": "Feb Reading"
    }, follow_redirects=True)
    assert r2.status_code == 200
    assert b"Meter reading saved successfully" in r2.data

    # Invalid duplicate date
    r_dup = client.post("/readings/add", data={
        "meter_id": mid,
        "reading_date": "2026-02-01",
        "cumulative_kwh": 800.0,
    }, follow_redirects=True)
    assert r_dup.status_code == 200
    assert b"already exists" in r_dup.data

    # Invalid decreasing value
    r_dec = client.post("/readings/add", data={
        "meter_id": mid,
        "reading_date": "2026-03-01",
        "cumulative_kwh": 700.0,
    }, follow_redirects=True)
    assert r_dec.status_code == 200
    assert b"cannot decrease" in r_dec.data or b"lower than the previous" in r_dec.data


def test_analytics_and_alerts_routes(client):
    res_analytics = client.get("/analytics")
    assert res_analytics.status_code == 200
    assert b"Consumption Analytics" in res_analytics.data

    res_alerts = client.get("/alerts?threshold=400")
    assert res_alerts.status_code == 200
    assert b"High-Usage Alerts" in res_alerts.data


def test_reports_exports(client):
    # Test CSV with headers even when empty
    res_empty_csv = client.get("/reports.csv")
    assert res_empty_csv.status_code == 200
    assert b"Consumer Name" in res_empty_csv.data

    # Add a sample record to test populated exports
    cid = db.execute("INSERT INTO consumers (consumer_name, region) VALUES ('Report Consumer', 'Tirupati')")
    mid = db.execute("INSERT INTO meters (consumer_id, meter_code) VALUES (%s, 'MTR-REP-01')", (cid,))
    db.execute("""
        INSERT INTO meter_readings (meter_id, reading_date, cumulative_kwh, consumption_kwh)
        VALUES (%s, '2026-01-01', 500.0, 150.0)
    """, (mid,))

    # Populated CSV download
    res_csv = client.get("/reports.csv")
    assert res_csv.status_code == 200
    assert res_csv.content_type == "text/csv; charset=utf-8"
    assert b"Consumer Name" in res_csv.data
    assert b"Report Consumer" in res_csv.data

    # PDF download
    res_pdf = client.get("/reports.pdf")
    assert res_pdf.status_code == 200
    assert res_pdf.content_type == "application/pdf"
    assert res_pdf.data.startswith(b"%PDF")

    # Printable HTML view
    res_print = client.get("/reports/print")
    assert res_print.status_code == 200
    assert b"WattWise Printable Executive View" in res_print.data


def test_rest_api_endpoints(client):
    res_monthly = client.get("/api/monthly")
    assert res_monthly.status_code == 200
    assert res_monthly.is_json

    res_regions = client.get("/api/regions")
    assert res_regions.status_code == 200
    assert res_regions.is_json

    res_status = client.get("/api/db-status")
    assert res_status.status_code == 200
    assert res_status.is_json
    assert "engine" in res_status.get_json()


def test_system_diagnostics_page(client):
    res = client.get("/system")
    assert res.status_code == 200
    assert b"Database Engine Status" in res.data


def test_404_error_page(client):
    res = client.get("/this-route-does-not-exist-404")
    assert res.status_code == 404
    assert b"Page Not Found" in res.data
