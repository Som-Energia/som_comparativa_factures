"""Synthetic surplus billing blocks; no customer invoice data."""

import fitz
import pytest

from app.services.invoice_extractor import extract_from_text, extract_pdf, extract_surplus_kwh


def surplus_block(values=("-101,125", "-82,25", "-64,375")):
    rows = [
        f"Periodo P{index} ({label}) - 0,005782 EUR/kWh × {value} kWh -0,50 EUR"
        for index, (label, value) in enumerate(zip(("Punta", "Llano", "Valle"), values), 1)
    ]
    return "Excedentes de energía generada -1,50 EUR\nPrecio kWh excedentes generados\n" + "\n".join(rows)


@pytest.mark.parametrize("values,expected", [
    (("-101,125", "-82,25", "-64,375"), 247.75),
    (("101,125", "82,25", "64,375"), 247.75),
    (("-0,1", "-0,2", "-0,3"), 0.6),
    (("0", "0", "0"), 0),
    (("-1.234,567", "-1000,125", "-20"), 2254.692),
])
def test_sums_billed_pepeenergy_period_quantities_as_positive_kwh(values, expected):
    assert extract_surplus_kwh(surplus_block(values)) == expected


def test_consumption_and_cumulative_readings_outside_the_block_are_ignored():
    text = """Pepeenergy
Energía consumida
Periodo P1 (Punta) - 0,20 EUR/kWh × 30,00 kWh 6,00 EUR
""" + surplus_block() + """
Cuota Pepeenergy 0,00 EUR
Generación
Periodo P1 (Punta) - 0,01 EUR/kWh × 900,00 kWh -9,00 EUR
Lectura P2 1000 -> 2000 (1000 kWh)
Lectura P3 2000 -> 3000 (1000 kWh)
"""
    assert extract_surplus_kwh(text) == 247.75


@pytest.mark.parametrize("change", ["missing_period", "duplicate_period", "missing_quantity", "unit_price_only"])
def test_incomplete_block_does_not_fall_back_to_unrelated_kwh(change):
    text = surplus_block()
    if change == "missing_period":
        text = "\n".join(line for line in text.splitlines() if "P2" not in line)
    elif change == "duplicate_period":
        text = text.replace("P2", "P1")
    elif change == "missing_quantity":
        text = text.replace("-82,25 kWh", "quantitat desconeguda")
    else:
        text = text.replace("× -82,25 kWh", "")
    text += "\nCuota Pepeenergy 0,00 EUR\nCompensación de excedentes -999,00 kWh"
    result = extract_from_text(text)
    assert result["self_consumption_surplus_kwh"] is None
    assert any(issue["field"] == "self_consumption_surplus_kwh" for issue in result["data_quality"]["issues"])


@pytest.mark.parametrize("label", [
    "Compensación excedente", "Compensación de excedentes", "Valoración excedentes",
    "Excedentes de autoconsumo", "Compensació d'excedents",
])
def test_financial_surplus_label_without_quantity_is_flagged(label):
    result = extract_from_text(f"{label} -2,00 EUR")
    assert result["self_consumption_surplus_kwh"] is None
    assert any(issue["field"] == "self_consumption_surplus_kwh" for issue in result["data_quality"]["issues"])


def test_no_surplus_and_explicit_zero_do_not_need_review():
    for text, expected in [("Factura sense excedents", None), (surplus_block(("0", "0", "0")), 0)]:
        result = extract_from_text(text)
        assert result["self_consumption_surplus_kwh"] == expected
        assert not any(issue["field"] == "self_consumption_surplus_kwh" for issue in result["data_quality"]["issues"])


def test_digital_pdf_keeps_period_quantities_separate_from_prices_and_amounts(tmp_path):
    pdf = tmp_path / "synthetic-surplus.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((30, 40), "Pepeenergy")
        page.insert_text((30, 70), "Excedentes de energia generada", fontsize=9)
        page.insert_text((520, 70), "-1,50 EUR", fontsize=8)
        for index, value in enumerate(("-101,125", "-82,25", "-64,375"), 1):
            y = 90 + index * 20
            page.insert_text((30, y), f"Periodo P{index} (Punta)", fontsize=8)
            page.insert_text((180, y), f"0,005782 EUR/kWh x {value} kWh", fontsize=8)
            page.insert_text((520, y), "-0,50 EUR", fontsize=8)
        page.insert_text((30, 180), "Cuota Pepeenergy", fontsize=9)
        doc.save(pdf)
    assert extract_pdf(pdf)["self_consumption_surplus_kwh"] == 247.75
