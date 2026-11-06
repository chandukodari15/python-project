"""
WattWise Calculation Engine
Core analytical calculations for electricity consumption, tiered tariffs,
daily load metrics, and carbon emissions.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, Optional, Tuple


# Standard Grid Emission Factor (India / CEA average: ~0.82 kg CO2 per kWh)
CARBON_FACTOR_KG_PER_KWH = 0.82

# Tiered Tariff Structures by Consumer Type (Andhra Pradesh / Southern Grid standard model)
TARIFF_SLABS = {
    "Residential": [
        (100, 3.30),   # 0 to 100 kWh @ Rs 3.30
        (100, 4.80),   # 101 to 200 kWh @ Rs 4.80
        (200, 6.50),   # 201 to 400 kWh @ Rs 6.50
        (None, 8.20),  # Above 400 kWh @ Rs 8.20
    ],
    "Commercial": [
        (100, 7.50),   # 0 to 100 kWh @ Rs 7.50
        (None, 9.80),  # Above 100 kWh @ Rs 9.80
    ],
    "Industrial": [
        (None, 7.40),  # Uniform commercial industrial power tariff @ Rs 7.40
    ],
    "Agricultural": [
        (None, 1.50),  # Subsidized farm feeder tariff @ Rs 1.50
    ],
    "Other": [
        (None, 6.00),  # General utility rate
    ]
}

FIXED_CHARGES = {
    "Residential": 50.00,
    "Commercial": 150.00,
    "Industrial": 350.00,
    "Agricultural": 20.00,
    "Other": 75.00
}

ELECTRICITY_DUTY_RATE = 0.06  # 6% state electricity duty / tax


def calculate_period_consumption(previous_cumulative: Optional[float], current_cumulative: float) -> Optional[float]:
    """
    Calculates the consumed energy (kWh) between the previous reading and current reading.
    Returns None if this is the first (baseline) reading for a meter.
    Raises ValueError if current is lower than previous (non-monotonic).
    """
    if previous_cumulative is None:
        return None
    
    prev = float(previous_cumulative)
    curr = float(current_cumulative)
    
    if curr < prev:
        raise ValueError(
            f"Current cumulative reading ({curr:.2f} kWh) cannot be lower than "
            f"the previous reading ({prev:.2f} kWh)."
        )
    
    return round(curr - prev, 2)


def calculate_tariff(kwh: Optional[float], consumer_type: str = "Residential") -> Dict[str, Any]:
    """
    Calculates detailed electricity bill breakdown based on tiered slabs:
    - Energy charges by tier
    - Fixed meter charge
    - Electricity duty / tax
    - Total estimated bill amount
    """
    if kwh is None or kwh < 0:
        return {
            "energy_charges": 0.0,
            "fixed_charges": 0.0,
            "duty": 0.0,
            "total_bill": 0.0,
            "effective_rate": 0.0,
            "slab_breakdown": []
        }

    units = float(kwh)
    remaining_units = units
    slabs = TARIFF_SLABS.get(consumer_type, TARIFF_SLABS["Residential"])
    fixed_charge = FIXED_CHARGES.get(consumer_type, FIXED_CHARGES["Residential"])
    
    energy_charge = 0.0
    slab_breakdown = []

    for slab_limit, rate in slabs:
        if remaining_units <= 0:
            break
            
        if slab_limit is None:
            # Final open-ended slab
            charge = remaining_units * rate
            slab_breakdown.append({
                "units": round(remaining_units, 2),
                "rate": rate,
                "amount": round(charge, 2)
            })
            energy_charge += charge
            remaining_units = 0
        else:
            consumed_in_slab = min(remaining_units, slab_limit)
            charge = consumed_in_slab * rate
            slab_breakdown.append({
                "units": round(consumed_in_slab, 2),
                "rate": rate,
                "amount": round(charge, 2)
            })
            energy_charge += charge
            remaining_units -= consumed_in_slab

    duty = round(energy_charge * ELECTRICITY_DUTY_RATE, 2)
    total_bill = round(energy_charge + fixed_charge + duty, 2)
    effective_rate = round(total_bill / units, 2) if units > 0 else 0.0

    return {
        "energy_charges": round(energy_charge, 2),
        "fixed_charges": round(fixed_charge, 2),
        "duty": duty,
        "total_bill": total_bill,
        "effective_rate": effective_rate,
        "slab_breakdown": slab_breakdown
    }


def calculate_carbon_footprint(kwh: Optional[float]) -> float:
    """
    Estimates greenhouse gas emissions (in kg CO2) associated with electricity consumption.
    """
    if not kwh or kwh <= 0:
        return 0.0
    return round(float(kwh) * CARBON_FACTOR_KG_PER_KWH, 2)


def calculate_daily_average(consumption_kwh: Optional[float], days: int) -> float:
    """
    Calculates average daily consumption over a given number of days.
    """
    if not consumption_kwh or days <= 0:
        return 0.0
    return round(float(consumption_kwh) / days, 2)


def validate_reading_input(
    meter_id: int,
    reading_date_str: str,
    cumulative_val: float,
    previous_reading: Optional[Dict[str, Any]],
    next_reading: Optional[Dict[str, Any]]
) -> Tuple[bool, Optional[str]]:
    """
    Validates chronological order, non-decreasing values, and duplicate dates.
    Returns (is_valid, error_message).
    """
    if meter_id is None or meter_id <= 0:
        return False, "A valid meter must be selected."
        
    if cumulative_val is None or cumulative_val < 0:
        return False, "Cumulative kWh reading cannot be negative."

    if not reading_date_str:
        return False, "Reading date is required."

    # Duplicate date check with previous or next
    if previous_reading and str(previous_reading.get("reading_date")) == reading_date_str:
        return False, f"A meter reading on {reading_date_str} already exists for this meter."

    if next_reading and str(next_reading.get("reading_date")) == reading_date_str:
        return False, f"A meter reading on {reading_date_str} already exists for this meter."

    # Monotonicity check against previous
    if previous_reading:
        prev_val = float(previous_reading.get("cumulative_kwh", 0))
        if cumulative_val < prev_val:
            return False, (
                f"Reading value ({cumulative_val:,.2f} kWh) is lower than the previous reading "
                f"({prev_val:,.2f} kWh on {previous_reading.get('reading_date')}). "
                f"Cumulative meter meters cannot decrease unless a rollover occurred."
            )

    # Monotonicity check against future reading
    if next_reading:
        next_val = float(next_reading.get("cumulative_kwh", 0))
        if cumulative_val > next_val:
            return False, (
                f"Reading value ({cumulative_val:,.2f} kWh) is higher than the subsequent reading "
                f"({next_val:,.2f} kWh on {next_reading.get('reading_date')}). Check the reading value."
            )

    return True, None
