"""
Integration tests for database models, foreign keys, and subsequent recalculations.
"""
import pytest
import db
from app import recalculate_subsequent_readings


def test_consumer_and_meter_foreign_key(client):
    """Verify consumer creation, meter linking, and foreign key constraint."""
    cid = db.execute("""
        INSERT INTO consumers (consumer_name, consumer_type, region, status)
        VALUES ('Test Consumer', 'Residential', 'Tirupati', 'Active')
    """)
    assert cid > 0

    mid = db.execute("""
        INSERT INTO meters (consumer_id, meter_code, meter_capacity, status)
        VALUES (%s, 'TEST-MTR-01', 10000, 'Active')
    """, (cid,))
    assert mid > 0

    # Query with join
    row = db.query_one("""
        SELECT m.meter_code, c.consumer_name, c.region
        FROM meters m
        JOIN consumers c ON c.consumer_id = m.consumer_id
        WHERE m.meter_id = %s
    """, (mid,))
    assert row["meter_code"] == "TEST-MTR-01"
    assert row["consumer_name"] == "Test Consumer"


def test_sequential_reading_recalculation(client):
    """
    Tests that subsequent readings' consumption_kwh are properly recalculated
    when an intermediate or updated reading is processed.
    """
    cid = db.execute("""
        INSERT INTO consumers (consumer_name, consumer_type, region)
        VALUES ('Recalc Test', 'Commercial', 'Nellore')
    """)
    mid = db.execute("""
        INSERT INTO meters (consumer_id, meter_code)
        VALUES (%s, 'RECALC-001')
    """, (cid,))

    # Insert baseline reading: Jan 1 @ 1000 kWh
    r1 = db.execute("""
        INSERT INTO meter_readings (meter_id, reading_date, cumulative_kwh, consumption_kwh)
        VALUES (%s, '2026-01-01', 1000.0, NULL)
    """, (mid,))

    # Insert March 1 reading: Mar 1 @ 1500 kWh (initially, usage is 500)
    r3 = db.execute("""
        INSERT INTO meter_readings (meter_id, reading_date, cumulative_kwh, consumption_kwh)
        VALUES (%s, '2026-03-01', 1500.0, 500.0)
    """, (mid,))

    # Now backfill February 1 reading: Feb 1 @ 1200 kWh
    r2 = db.execute("""
        INSERT INTO meter_readings (meter_id, reading_date, cumulative_kwh, consumption_kwh)
        VALUES (%s, '2026-02-01', 1200.0, 200.0)
    """, (mid,))

    # Run recalculation
    recalculate_subsequent_readings(mid, "2026-01-01")

    # Verify:
    # Jan 1: Baseline (NULL)
    # Feb 1: 1200 - 1000 = 200 kWh
    # Mar 1: 1500 - 1200 = 300 kWh (automatically adjusted from 500!)
    readings = db.query_all("""
        SELECT reading_date, cumulative_kwh, consumption_kwh
        FROM meter_readings
        WHERE meter_id = %s
        ORDER BY reading_date ASC
    """, (mid,))

    assert readings[0]["consumption_kwh"] is None
    assert readings[1]["consumption_kwh"] == 200.0
    assert readings[2]["consumption_kwh"] == 300.0
