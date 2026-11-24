"""Synthetic 2.0TD power layouts: peak P1 and valley P2, independently of energy."""

import pytest

from app.routes import _build_comparison_input
from app.services.invoice_extractor import extract_contracted_powers, extract_from_text


@pytest.mark.parametrize("layout", [
    "Endesa\nPotencias contratadas: punta-llano {peak} kW; valle {valley} kW",
    "Endesa\nPotències contractades: punta-pla {peak} kW; vall {valley} kW",
    "Energía XXI\nPotencia contratada en punta-llano: {peak} kW  Potencia contratada en valle: {valley} kW",
    "Iberdrola\nPotencia punta: {peak} kW\nPotencia valle: {valley} kW",
    "Naturgy\nPotencia contratada P1: {peak} kW\nPotencia contratada P2: {valley} kW",
    "Repsol\nPotència contractada {peak} kW {valley} kW",
    "Repsol\nPunta: {peak} kW\nVall: {valley} kW",
    "Holaluz\nPotència contractada: P1 {peak} kW P2 {valley} kW",
    "Plenitude\nP1 {peak} kW P2 {valley} kW",
    "Pepeenergy\nPotencia contratada en P1 (Punta): {peak} kW\nPotencia contratada en P2 (Valle): {valley} kW",
])
def test_20td_layouts_preserve_both_power_periods(layout):
    text = "Tarifa de acceso: 2.0TD\n" + layout.format(peak="4,1", valley="5,2")
    expected = {"P1": 4.1, "P2": 5.2, "P3": None}
    assert extract_contracted_powers(text) == expected
    result = extract_from_text(text)
    assert result["contracted_power_kw_by_periods"] == expected
    assert not any(
        issue["field"].startswith("contracted_power_kw_by_periods")
        for issue in result["data_quality"]["issues"]
    )
    assert _build_comparison_input(result)["contracted_power_kw_by_periods"] == {
        "P1": 4.1, "P2": 5.2,
    }


@pytest.mark.parametrize("tariff,valley,expected_valley", [
    ("20TD", "5,2", 5.2),
    ("2.0TD", "4,1", 4.1),
])
def test_named_power_mapping_supports_tariff_alias_and_equal_powers(tariff, valley, expected_valley):
    text = f"Tarifa de acceso: {tariff}\nPotencias contratadas: punta-llano 4,1 kW; valle {valley} kW"
    assert extract_contracted_powers(text) == {"P1": 4.1, "P2": expected_valley, "P3": None}


@pytest.mark.parametrize("period,expected", [
    ("P1", {"P1": 4.1, "P2": None, "P3": None}),
    ("P2", {"P1": None, "P2": 4.1, "P3": None}),
])
def test_20td_missing_power_is_not_copied_and_only_missing_period_is_flagged(period, expected):
    result = extract_from_text(
        f"Naturgy\nTarifa de acceso: 2.0TD\nPotencia contratada {period}: 4,1 kW"
    )
    assert result["contracted_power_kw_by_periods"] == expected
    issues = {
        issue["field"] for issue in result["data_quality"]["issues"]
        if issue["field"].startswith("contracted_power_kw_by_periods")
    }
    missing = "P2" if period == "P1" else "P1"
    assert issues == {f"contracted_power_kw_by_periods.{missing}"}


@pytest.mark.parametrize("tariff", ["2.0TD", "20TD", "3.0TD", None])
def test_power_period_validation_depends_on_tariff_not_retailer(tariff):
    text = "Comercialitzadora exemple\nPotencia contratada en P1: 4,1 kW\nPotencia contratada en P2: 5,2 kW"
    if tariff:
        text += f"\nTarifa de acceso: {tariff}"
    result = extract_from_text(text)
    issues = {issue["field"] for issue in result["data_quality"]["issues"]}
    assert ("contracted_power_kw_by_periods.P3" in issues) == (tariff not in {"2.0TD", "20TD"})


@pytest.mark.parametrize("tariff", ["3.0TD", None])
def test_explicit_third_power_is_not_removed_for_other_or_unknown_tariffs(tariff):
    text = "P1 4,1 kW P2 5,2 kW P3 6,3 kW"
    if tariff:
        text += f"\nTarifa de acceso: {tariff}"
    assert extract_from_text(text)["contracted_power_kw_by_periods"] == {
        "P1": 4.1, "P2": 5.2, "P3": 6.3,
    }


def test_factor_20td_power_column_keeps_two_different_values():
    words = [
        (0, 100, 20, 110, 28, "P."),
        (0, 115, 20, 160, 28, "Contractada"),
        (0, 100, 40, 125, 48, "4,1"),
        (0, 100, 60, 125, 68, "5,2"),
    ]
    result = extract_from_text("Factor Energia\nTarifa de acceso: 2.0TD", words)
    assert result["contracted_power_kw_by_periods"] == {"P1": 4.1, "P2": 5.2, "P3": None}
    assert _build_comparison_input(result)["contracted_power_kw_by_periods"] == {"P1": 4.1, "P2": 5.2}
