"""Synthetic Endesa tables: no customer invoice data is stored in fixtures."""

import fitz
import pytest

from app.services.invoice_extractor import extract_from_text, extract_meter_rental, extract_pdf


@pytest.mark.parametrize("spanish", [False, True])
@pytest.mark.parametrize("table_x", [40, 320])
@pytest.mark.parametrize("cell", ["present", "missing", "ambiguous"])
def test_endesa_consumption_is_confined_to_its_table(tmp_path, spanish, table_x, cell):
    pdf = tmp_path / "endesa-synthetic.pdf"
    with fitz.open() as document:
        page = document.new_page(width=900)
        page.insert_text((20, 30), "Endesa", fontsize=7)
        for offset, text in [
            (0, "Periodo" if spanish else "Període"),
            (42, "01/01/2026"), (92, "31/01/2026"),
            (144, "Multipl."), (190, "Ajuste" if spanish else "Ajust"),
            (222, "Consumo" if spanish else "Consum"),
        ]:
            page.insert_text((table_x + offset, 60), text, fontsize=7)
        page.insert_text((table_x + 42, 70), "Lectura real", fontsize=7)
        page.insert_text((table_x + 92, 70), "Lectura real", fontsize=7)
        page.insert_text((table_x, 90), "Energía" if spanish else "Energia", fontsize=7)
        page.insert_text((table_x + 240, 90), "kWh", fontsize=7)
        names = ("Punta", "Llano", "Valle") if spanish else ("Punta", "Pla", "Vall")
        for index, (name, value) in enumerate(zip(names, ("12,125", "23,250", "34,375"))):
            y = 105 + index * 12
            page.insert_text((table_x, y), name, fontsize=7)
            for offset, text in [(42, "1.000,000"), (92, "2.000,000"),
                                 (155, "1,00"), (195, "0,000")]:
                page.insert_text((table_x + offset, y), text, fontsize=7)
            if index != 0 or cell != "missing":
                page.insert_text((table_x + 232, y), value, fontsize=7)
            if index == 0 and cell == "ambiguous":
                page.insert_text((table_x + 222, y), "9", fontsize=7)
            # A last-number heuristic would select this unrelated right-hand value.
            page.insert_text((table_x + 300, y), "999,999", fontsize=7)
            if table_x == 320:
                # Reproduce the real failure: euros in a different column on the same row.
                page.insert_text((20, y), "Peajes 2,00 EUR y potencia 3,00 EUR", fontsize=7)
        page.insert_text((table_x, 150), "Información", fontsize=7)
        # A later section must not replace a missing/ambiguous Punta consumption.
        page.insert_text((table_x, 170), "Punta", fontsize=7)
        page.insert_text((table_x + 232, 170), "88,888", fontsize=7)
        document.save(pdf)

    result = extract_pdf(pdf)
    assert result["energy_by_periods"] == {
        "P1": 12.125 if cell == "present" else None, "P2": 23.25, "P3": 34.375,
    }
    issues = {issue["field"] for issue in result["data_quality"]["issues"]}
    assert ("energy_by_periods.P1" in issues) == (cell != "present")


@pytest.mark.parametrize("label", ["Alquiler del contador", "Lloguer del comptador"])
@pytest.mark.parametrize("separator", ["", ":"])
def test_meter_rental_sums_billed_segments_without_adding_summary(label, separator):
    text = f"""Endesa
{label} 1,57 €
{label}{separator} ( 1 días x 0,026630 Eur/día ) ........0,03 €
{label}{separator} ( 58 días x 0,026630 Eur/día ) ........1,54 €
> 1,79% Alquiler de contador
El precio del alquiler del contador ha sido publicado en la Orden IET 1491/2013.
"""
    assert extract_from_text(text)["meter_rental_eur"] == 1.57


def test_meter_rental_keeps_distinct_segments_with_equal_billed_amounts():
    text = """Alquiler del contador ( 28 días x 0,026630 Eur/día ) ........0,75 €
Alquiler del contador ( 28 días x 0,026630 Eur/día ) ........0,75 €"""
    # Sum the rounded charges as printed, not 56 days times the unit rate (1.49).
    assert extract_meter_rental(text) == 1.50


def test_meter_rental_never_uses_the_daily_price_as_a_billed_amount():
    assert extract_meter_rental("Alquiler del contador (30 días x 0,026630 Eur/día)") is None
