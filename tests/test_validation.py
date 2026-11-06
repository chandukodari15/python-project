"""
Unit tests for Reading Input and Sequence Validation.
"""
from services.calculator import validate_reading_input


def test_valid_reading_input():
    previous = {"reading_date": "2026-01-01", "cumulative_kwh": 1000.0}
    next_read = {"reading_date": "2026-03-01", "cumulative_kwh": 1300.0}
    
    is_valid, err = validate_reading_input(
        meter_id=1,
        reading_date_str="2026-02-01",
        cumulative_val=1150.0,
        previous_reading=previous,
        next_reading=next_read
    )
    assert is_valid is True
    assert err is None


def test_duplicate_date_validation():
    previous = {"reading_date": "2026-02-01", "cumulative_kwh": 1000.0}
    
    is_valid, err = validate_reading_input(
        meter_id=1,
        reading_date_str="2026-02-01",
        cumulative_val=1100.0,
        previous_reading=previous,
        next_reading=None
    )
    assert is_valid is False
    assert "already exists" in err


def test_decreasing_cumulative_reading():
    previous = {"reading_date": "2026-01-01", "cumulative_kwh": 1000.0}
    
    is_valid, err = validate_reading_input(
        meter_id=1,
        reading_date_str="2026-02-01",
        cumulative_val=950.0,
        previous_reading=previous,
        next_reading=None
    )
    assert is_valid is False
    assert "lower than the previous" in err


def test_higher_than_future_reading():
    next_read = {"reading_date": "2026-03-01", "cumulative_kwh": 1200.0}
    
    is_valid, err = validate_reading_input(
        meter_id=1,
        reading_date_str="2026-02-01",
        cumulative_val=1250.0,
        previous_reading=None,
        next_reading=next_read
    )
    assert is_valid is False
    assert "higher than the subsequent" in err


def test_negative_reading_value():
    is_valid, err = validate_reading_input(
        meter_id=1,
        reading_date_str="2026-02-01",
        cumulative_val=-50.0,
        previous_reading=None,
        next_reading=None
    )
    assert is_valid is False
    assert "cannot be negative" in err
