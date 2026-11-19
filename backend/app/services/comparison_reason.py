"""Suggest an editable email reason from comparable, pre-tax component costs."""

from decimal import Decimal


TOLERANCE = Decimal("0.02")


def suggest_comparison_reason(savings, current_energy, current_power, som_energy, som_power):
    suggestion = {"reason": "", "status": "missing_data", "energy_difference_eur": None, "power_difference_eur": None}
    if abs(savings) <= TOLERANCE:
        return {**suggestion, "status": "no_difference"}
    if current_energy is None or current_power is None:
        return suggestion
    energy = current_energy - som_energy
    power = current_power - som_power
    suggestion.update(energy_difference_eur=float(energy), power_difference_eur=float(power))
    direction = Decimal("1") if savings > 0 else Decimal("-1")
    contribution = (energy + power) * direction
    # Conservative attribution: the net pre-tax contribution must account for
    # at least half the total difference, without assuming the rival's tax bases.
    # The total can also include services, surplus compensation or other discounts.
    if contribution <= TOLERANCE or contribution * 2 < abs(savings) - TOLERANCE:
        return {**suggestion, "status": "other_costs"}
    energy_matches = energy * direction > TOLERANCE
    power_matches = power * direction > TOLERANCE
    reason = "both" if energy_matches and power_matches else "energy" if energy_matches else "power"
    return {**suggestion, "reason": reason, "status": "suggested"}
