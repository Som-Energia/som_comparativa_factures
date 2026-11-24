"""Synthetic layouts for Factor Energia, Plenitude and Pepeenergy invoices."""

import fitz
import pytest

from app.services.invoice_extractor import (
    extract_billing_days,
    extract_contracted_powers,
    extract_energy_by_periods,
    extract_from_text,
    extract_meter_rental,
    extract_pdf,
    extract_retailer,
    extract_titular,
)


@pytest.mark.parametrize("brand,retailer", [
    ("Eni Plenitude Iberia", "Plenitude"),
    ("Pepeenergy", "Pepeenergy"),
    ("La energía verde de Pepephone", "Pepeenergy"),
])
def test_retailer_is_not_its_iberdrola_distributor(brand, retailer):
    assert extract_retailer(f"{brand}\nDistribuidora: i-DE (Grupo Iberdrola)") == retailer


@pytest.mark.parametrize("label", ["Alquiler equipos:", "Alquiler de equipos de medida y control"])
def test_plenitude_rental_is_a_billed_amount_not_the_unit_rate(label):
    assert extract_meter_rental(f"{label} 0,91 €") == 0.91
    assert extract_meter_rental(f"{label} (34 días * 0,02663 €/día) 0,91 €") == 0.91
    assert extract_meter_rental(f"{label} 0,02663 €/día") is None


@pytest.mark.parametrize("formula,expected", [
    ("Alquiler de equipos de medida y control (34 días * 0,02663 €/día) 0,91 €", 34),
    ("Alquiler contador 0,026630 €/día × 28 0,75 €", 28),
])
def test_billed_rental_days_take_precedence_over_date_difference(formula, expected):
    text = f"Periodo de facturación 01/02/2026 - 28/02/2026\n{formula}"
    assert extract_billing_days(text) == (expected, False)


def test_unrelated_or_conflicting_day_counts_are_not_used():
    assert extract_billing_days("Plazo de pago 15 días\nAlquiler equipos 0,91 €") == (None, False)
    text = """Alquiler equipos (12 días * 0,02663 €/día) 0,32 €
Alquiler equipos (16 días * 0,02663 €/día) 0,43 €"""
    assert extract_billing_days(text) == (None, False)


def test_pepeenergy_powers_are_explicit_and_not_copied_to_missing_periods():
    text = """Potencia contratada en P1 (Punta): 4,100 kW
Potencia contratada en P2 (Valle): 5,200 kW
Las potencias máximas demandadas fueron P1: 8,9 kW P2: 9,8 kW"""
    assert extract_contracted_powers(text) == {"P1": 4.1, "P2": 5.2, "P3": None}
    assert extract_contracted_powers(text.splitlines()[0]) == {"P1": 4.1, "P2": None, "P3": None}


def test_pepeenergy_customer_name_stops_before_next_column():
    text = "Datos cliente      Potencia contratada 9,00 €\nPersona Sintética Ejemplo      Precio\nNIF: 00000000X"
    assert extract_titular(text) == "Persona Sintética Ejemplo"


def test_pepeenergy_customer_block_without_adjacent_column_or_name():
    assert extract_titular("Datos cliente\nPersona Sintética Ejemplo\nNIF: 00000000X") == "Persona Sintética Ejemplo"
    assert extract_titular("Datos cliente\nNIF:\n00000000X") is None


@pytest.mark.parametrize("retailer", ["Plenitude", "Pepeenergy"])
@pytest.mark.parametrize("tariff", ["2.0TD", "3.0TD"])
def test_missing_power_p3_warning_depends_on_tariff(retailer, tariff):
    result = extract_from_text(f"""{retailer}
Tarifa de acceso: {tariff}
Potencia contratada en P1 (Punta): 4,1 kW
Potencia contratada en P2 (Valle): 5,2 kW""")
    issues = {issue["field"] for issue in result["data_quality"]["issues"]}
    assert ("contracted_power_kw_by_periods.P3" in issues) == (tariff != "2.0TD")


@pytest.mark.parametrize("spanish", [False, True])
@pytest.mark.parametrize("missing_p2", [False, True])
def test_factor_table_is_read_by_column_and_period_in_a_digital_pdf(tmp_path, spanish, missing_p2):
    pdf = tmp_path / "factor-synthetic.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((20, 30), "Factor Energia")
        # This advert used to accidentally select the Holaluz-only extractor.
        page.insert_text((20, 55), "Envia les teves lectures i descarrega les factures")
        page = doc.new_page()
        for x, label in [
            (20, "Periodo" if spanish else "Període"), (80, "Lectura Anterior (kWh)"),
            (185, "Lectura Actual (kWh)"), (300, "Consumo" if spanish else "Consum"),
            (335, "(kWh)"), (380, "Reactiva (kVArh)"), (470, "P.Demandada (kW)"),
        ]:
            page.insert_text((x, 45), label, fontsize=7)
        # Rows are deliberately spaced further than 80pt from the header and reordered.
        for index, (period, value) in enumerate(((3, "140,125"), (1, "0,000"), (2, "82,750"))):
            y = 80 + index * 40
            page.insert_text((20, y), f"{'Periodo' if spanish else 'Període'} {period}", fontsize=7)
            page.insert_text((100, y), "5000,000 R", fontsize=7)
            page.insert_text((205, y), "5100,000 E", fontsize=7)
            if not (missing_p2 and period == 2):
                # Right-aligned values extend beyond the word "Consum".
                page.insert_text((343, y), value, fontsize=7)
            page.insert_text((420, y), "0,000", fontsize=7)
            page.insert_text((530, y), "7,123", fontsize=7)
        page.insert_text((20, 200), "Total Activa", fontsize=7)
        page.insert_text((343, 200), "222,875", fontsize=7)
        doc.save(pdf)
    result = extract_pdf(pdf)
    assert result["energy_by_periods"] == {"P1": 0, "P2": None if missing_p2 else 82.75, "P3": 140.125}
    if missing_p2:
        assert any(issue["field"] == "energy_by_periods.P2" for issue in result["data_quality"]["issues"])


def test_factor_advert_does_not_select_holaluz_text_rules():
    assert extract_energy_by_periods("""Factor Energia
Envia les teves lectures i descarrega les teves factures
Consum (kWh)
10,125
20,250
30,375""") == {"P1": 10.125, "P2": 20.25, "P3": 30.375}


def test_pepeenergy_customer_block_in_a_two_column_pdf(tmp_path):
    pdf = tmp_path / "pepeenergy-synthetic.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((320, 40), "La energia verde de Pepephone", fontsize=9)
        page = doc.new_page()
        page.insert_text((30, 60), "Datos cliente", fontsize=10)
        page.insert_text((315, 60), "Potencia contratada", fontsize=9)
        page.insert_text((30, 78), "Persona Sintetica Ejemplo", fontsize=9)
        page.insert_text((315, 78), "Precio", fontsize=9)
        page.insert_text((30, 93), "NIF: 00000000X", fontsize=9)
        page.insert_text((30, 130), "Potencia contratada en P1 (Punta): 4,1 kW", fontsize=9)
        page.insert_text((30, 150), "Potencia contratada en P2 (Valle): 5,2 kW", fontsize=9)
        page.insert_text((30, 170), "Tarifa de acceso: 2.0TD", fontsize=9)
        page.insert_text((30, 190), "Distribuidora: i-DE (Grupo Iberdrola)", fontsize=9)
        page.insert_text((315, 220), "Alquiler contador 0,026630 EUR/dia x 28  0,75 EUR", fontsize=8)
        doc.save(pdf)
    result = extract_pdf(pdf)
    assert result["retailer"] == "Pepeenergy"
    assert result["titular"] == "Persona Sintetica Ejemplo"
    assert result["billing_days"] == 28
    assert result["contracted_power_kw_by_periods"] == {"P1": 4.1, "P2": 5.2, "P3": None}
