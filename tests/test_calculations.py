"""
Unit tests for WattWise Calculation Engine.
Tests consumption calculations, tiered tariffs, emissions, and averages.
"""
import pytest
from services.calculator import (
    calculate_period_consumption,
    calculate_tariff,
    calculate_carbon_footprint,
    calculate_daily_average
)


def test_period_consumption_baseline():
    """First reading establishes the baseline; period consumption must be None."""
    assert calculate_period_consumption(None, 1250.0) is None


def test_period_consumption_normal_progression():
    """Valid sequential progression: 1350.50 - 1200.00 = 150.50 kWh."""
    usage = calculate_period_consumption(1200.00, 1350.50)
    assert usage == 150.50


def test_period_consumption_zero_usage():
    """Vacant property with zero consumption: 1000.00 to 1000.00 = 0.00 kWh."""
    usage = calculate_period_consumption(1000.00, 1000.00)
    assert usage == 0.00


def test_period_consumption_decreasing_raises_value_error():
    """Cumulative meter value cannot decrease without rollover exception."""
    with pytest.raises(ValueError) as excinfo:
        calculate_period_consumption(500.0, 480.0)
    assert "cannot be lower" in str(excinfo.value)


def test_tariff_residential_slabs():
    """
    Residential Tariff Verification:
    For 250 kWh:
    - Tier 1: First 100 units @ Rs 3.30 = Rs 330.00
    - Tier 2: Next 100 units @ Rs 4.80 = Rs 480.00
    - Tier 3: Next 50 units @ Rs 6.50 = Rs 325.00
    - Energy charges = Rs 1,135.00
    - Fixed charges = Rs 50.00
    - Duty (6% of 1135) = Rs 68.10
    - Total = 1135 + 50 + 68.10 = Rs 1,253.10
    """
    res = calculate_tariff(250.0, "Residential")
    assert res["energy_charges"] == 1135.00
    assert res["fixed_charges"] == 50.00
    assert res["duty"] == 68.10
    assert res["total_bill"] == 1253.10
    assert len(res["slab_breakdown"]) == 3


def test_tariff_commercial():
    """Commercial rates: 150 kWh should use commercial tiers and fixed charge 150."""
    res = calculate_tariff(150.0, "Commercial")
    # 100 @ 7.50 = 750; 50 @ 9.80 = 490 -> energy = 1240.00
    assert res["energy_charges"] == 1240.00
    assert res["fixed_charges"] == 150.00
    assert res["duty"] == round(1240.00 * 0.06, 2)
    assert res["total_bill"] == round(1240.00 + 150.00 + (1240.00 * 0.06), 2)


def test_carbon_footprint_calculation():
    """100 kWh @ 0.82 kg CO2/kWh = 82.00 kg CO2."""
    assert calculate_carbon_footprint(100.0) == 82.00
    assert calculate_carbon_footprint(0) == 0.0
    assert calculate_carbon_footprint(None) == 0.0


def test_daily_average_calculation():
    """300 kWh over 30 days = 10.0 kWh/day."""
    assert calculate_daily_average(300.0, 30) == 10.0
    assert calculate_daily_average(0, 30) == 0.0
    assert calculate_daily_average(100, 0) == 0.0
