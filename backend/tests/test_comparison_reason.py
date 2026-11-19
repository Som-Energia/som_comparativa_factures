from decimal import Decimal

import pytest

from app.services.comparison_reason import suggest_comparison_reason


@pytest.mark.parametrize("savings,energy,power,reason,status", [
    (10, 40, 10, "energy", "suggested"),
    (10, 30, 20, "power", "suggested"),
    (10, 35, 15, "both", "suggested"),
    (-10, 20, 10, "energy", "suggested"),
    (-10, 30, 0, "power", "suggested"),
    (-10, 25, 5, "both", "suggested"),
    (5, 40, 5, "energy", "suggested"),  # Opposing components: net saving still explains total.
    (-5, 20, 15, "energy", "suggested"),
    (10, 30, 10, "", "other_costs"),  # Only other costs differ.
    (10, 29, 10, "", "other_costs"),  # Components contradict overall outcome.
    (-10, 31, 10, "", "other_costs"),
    (100, 35, 10, "", "other_costs"),  # Components cannot be called the principal cause.
    (10, 40, None, "", "missing_data"),
    (-10, None, 0, "", "missing_data"),
    (10, None, None, "", "missing_data"),
    (0, 40, 10, "", "no_difference"),
    (0.02, 40, 10, "", "no_difference"),
    (1, 30.01, 11, "power", "suggested"),  # One-cent differences are noise.
])
def test_suggests_only_supported_directions_and_ignores_rounding(savings, energy, power, reason, status):
    decimal = lambda value: None if value is None else Decimal(str(value))
    result = suggest_comparison_reason(decimal(savings), decimal(energy), decimal(power), Decimal("30"), Decimal("10"))
    assert result["reason"] == reason
    assert result["status"] == status
