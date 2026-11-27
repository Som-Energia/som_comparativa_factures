"""Bonpreu billed sections and two-column contract, using synthetic identities."""

from io import BytesIO

import fitz
import pytest

from app import create_app
from app.services.invoice_extractor import extract_from_text


@pytest.fixture
def bonpreu_text():
    return """Bon Preu, Sau
Període de facturació: del 22/09/2026 al 25/10/2026 (Dies: 34)
Per l'electricitat que has fet servir 16,78 €
Per la potència contractada 18,50 €
L'impost per l'electricitat que pagues a l'Estat 1,80 €
El lloguer del comptador 0,91 €
Altres conceptes 0,84 €
IVA 21% 8,15 €
Import total de la factura 46,98 €
Dades del contracte
Titular: Persona Sintètica Exemple         Tarifa d'accés: 2.0TD
NIF: 00000000X                            Número que identifica el teu punt de subministrament (CUPS):
Data alta: 22/02/2023                      ES0000000000000000TT
Potència contractada (kW): 3,400 kW - 3,400 kW
Informació del consum elèctric
Període 1
Lectura anterior: 1.898 kWh
Lectura actual: 1.927 kWh
Consum total del període: 29 kWh
Període 2
Consum total del període: 25 kWh
Període 3
Consum total del període: 52 kWh
Total consum dels períodes 106 kWh
Detall de la factura
Per la potència contractada
Període 1
La potència que tens contractada 3,400 kW
Els dies que comprèn aquesta factura 34 dies
El preu del peatge d'accés per dia 0,079999 €/kW/dia
Període 2
La potència que tens contractada 3,400 kW
Els dies que comprèn aquesta factura 34 dies
El preu del peatge d'accés per dia 0,079999 €/kW/dia
El que et costa aquest mes la potència contractada (Total €) 18,50 €
Per l'electricitat que has fet servir
Energia consumida
Període 1
El preu que té l'electricitat 0,125299 €/kWh
El que has consumit aquest mes 28,542 kWh
Període 2
El preu que té l'electricitat 0,125299 €/kWh
El que has consumit aquest mes 25,278 kWh
Període 3
El preu que té l'electricitat 0,125299 €/kWh
El que has consumit aquest mes 52,114 kWh
Cost d'ajustament per Red Elèctrica Espanyola 3,50 €
El cost dels serveis d'ajust és de 0,032994 €/kWh.
El que et costa aquest mes l'energia consumida (Total €) 13,28 €
Subtotal 1: Base Imposable de l'Impost Elèctric 31,78 €
L'impost per l'electricitat que pagues a l'Estat 1,80 €
Impost especial del 5,11269632 % sobre el Subtotal 1
Lloguer del comptador 0,91 €
Repercussió bo social 0,84 €
Subtotal 2: Base Imposable de l'IVA 38,83 €
IVA 21% 8,15 €
Import total de la factura
Total que et toca pagar 46,98 €
Repartiment de la factura
Energia 23,43 €
Impostos aplicats 9,95 €
Lloguer comptador 0,91 €
"""


def assert_bonpreu_fields(result):
    assert result["retailer"] == "Bonpreu Esclat Energia"
    assert result["titular"] == "Persona Sintètica Exemple"
    assert result["cups"] == "ES0000000000000000TT"
    assert result["billing_days"] == 34
    assert result["competitor_invoice_amount"] == 46.98
    assert result["competitor_energy_eur"] == 13.28
    assert result["competitor_power_eur"] == 18.50
    assert result["energy_by_periods"] == {"P1": 28.542, "P2": 25.278, "P3": 52.114}
    assert result["contracted_power_kw_by_periods"] == {"P1": 3.4, "P2": 3.4, "P3": None}
    assert result["meter_rental_eur"] == 0.91
    assert result["electricity_tax"] == 1.80
    assert result["electric_tax_rate_percent"] == 5.11269632
    assert result["vat_amount"] == 8.15
    assert result["vat_rate_percent"] == 21
    assert result["self_consumption_surplus_kwh"] is None
    assert result["data_quality"] == {"status": "verified", "issues": []}


@pytest.mark.parametrize("retailer", ["Bon Preu, Sau", "Bonpreu Esclat Energia", "BonpreuEsclat Energia"])
def test_bonpreu_billed_values(bonpreu_text, retailer):
    assert_bonpreu_fields(extract_from_text(bonpreu_text.replace("Bon Preu, Sau", retailer)))


@pytest.mark.parametrize("old,new,field,expected", [
    ("(Dies: 34)", "(Dies: 33)", "billing_days", None),
    ("El que has consumit aquest mes 28,542 kWh", "", "energy_by_periods.P1", None),
    ("El que has consumit aquest mes 28,542 kWh", "El que has consumit aquest mes 0,000 kWh", "energy_by_periods.P1", 0),
    (" 13,28 €", " 14,28 €", "competitor_energy_eur", None),
    (" 18,50 €", " 19,50 €", "competitor_power_eur", 19.5),
    ("Impost especial del 5,11269632 % sobre el Subtotal 1", "", "electric_tax_rate_percent", None),
    ("ES0000000000000000TT", "ES0000000000000000AA", "cups", None),
    ("Persona Sintètica Exemple", "", "titular", None),
    ("Cost d'ajustament per Red Elèctrica Espanyola 3,50 €", "", "competitor_energy_eur", None),
    ("El que et costa aquest mes l'energia consumida (Total €) 13,28 €", "", "competitor_energy_eur", None),
    ("L'impost per l'electricitat que pagues a l'Estat 1,80 €", "", "electricity_tax", None),
    ("del comptador 0,91 €", "del comptador", "meter_rental_eur", None),
    ("Potència contractada (kW): 3,400 kW - 3,400 kW", "Potència contractada (kW): 4,400 kW - 3,400 kW", "contracted_power_kw_by_periods.P1", None),
])
def test_bonpreu_missing_or_conflicting_values(bonpreu_text, old, new, field, expected):
    result = extract_from_text(bonpreu_text.replace(old, new))
    value = result
    for part in field.split("."):
        value = value[part]
    assert value == expected
    if expected is None:
        assert result["data_quality"]["status"] == "needs_review"


@pytest.mark.parametrize("extra,field", [
    ("\nImport total de la factura 99,00 €", "competitor_invoice_amount"),
    ("\nTitular: Una Altra Persona", "titular"),
    ("\nNúmero que identifica el teu punt de subministrament (CUPS):\nES0000000000000001TR", "cups"),
    ("\nLloguer del comptador 1,91 €", "meter_rental_eur"),
    ("\nL'impost per l'electricitat que pagues a l'Estat 2,80 €", "electricity_tax"),
])
def test_bonpreu_rejects_ambiguous_fields(bonpreu_text, extra, field):
    result = extract_from_text(bonpreu_text + extra)
    assert result[field] is None
    assert any(issue["field"] == field and issue["code"] == "conflicting_values"
               for issue in result["data_quality"]["issues"])


def test_bonpreu_invoice_total_must_reconcile(bonpreu_text):
    result = extract_from_text(bonpreu_text.replace("46,98 €", "47,98 €"))
    assert result["data_quality"]["status"] == "needs_review"
    assert any(issue["code"] == "invoice_total_mismatch" for issue in result["data_quality"]["issues"])


def test_bonpreu_distinct_power_periods(bonpreu_text):
    text = bonpreu_text.replace("3,400 kW - 3,400 kW", "4,100 kW - 6,200 kW")
    text = text.replace("La potència que tens contractada 3,400 kW", "La potència que tens contractada 4,100 kW", 1)
    text = text.replace("La potència que tens contractada 3,400 kW", "La potència que tens contractada 6,200 kW", 1)
    assert extract_from_text(text)["contracted_power_kw_by_periods"] == {"P1": 4.1, "P2": 6.2, "P3": None}


def bonpreu_pdf(text, variant="valid", spanish=False):
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((35, 40), "Bon Preu, Sau", fontsize=8)
        page.insert_text((35, 70), "Dades del contracte", fontsize=8)
        name = "Persona Sintética Ejemplo" if spanish else "Persona Sintètica Exemple"
        holder = "Titular:" if variant == "missing_holder" else f"Titular: {name}"
        page.insert_text((35, 90), holder, fontsize=8)
        page.insert_text((300, 90), "Tarifa de acceso: 2.0TD" if spanish else "Tarifa d'accés: 2.0TD", fontsize=8)
        page.insert_text((35, 106), "NIF: 00000000X", fontsize=8)
        cups_label = ("Número que identifica tu punto de suministro (CUPS):" if spanish
                      else "Número que identifica el teu punt de subministrament (CUPS):")
        if variant != "missing_cups":
            page.insert_text((300, 106), cups_label, fontsize=8)
            cups = "ES0000000000000000AA" if variant == "invalid_cups" else "ES0000000000000000TT"
            page.insert_text((300, 122), cups, fontsize=8)
        page.insert_text((35, 122), "Data alta: 22/02/2023", fontsize=8)
        if variant == "ambiguous_cups":
            page.insert_text((300, 150), "Número que identifica el teu punt de subministrament (CUPS):", fontsize=8)
            page.insert_text((300, 166), "ES0000000000000001TR", fontsize=8)
        if variant == "ambiguous_holder":
            page.insert_text((35, 150), "Titular: Una Altra Persona", fontsize=8)
            page.insert_text((300, 150), "Tarifa d'accés: 2.0TD", fontsize=8)
        page.insert_text((15, 300), "Text legal del marge", fontsize=8, rotate=90)
        # Keep contract identity only on the two-column page.
        lines = [line for line in text.splitlines()
                 if not any(label in line for label in ("Titular:", "NIF:", "Data alta:", "Fecha alta:"))]
        for start in range(0, len(lines), 30):
            page = document.new_page()
            for index, line in enumerate(lines[start:start + 30]):
                page.insert_text((20, 30 + index * 20), line.replace("€", "EUR"), fontsize=7)
        return document.tobytes()


@pytest.mark.parametrize("variant", ["valid", "missing_cups", "invalid_cups", "ambiguous_cups", "missing_holder", "ambiguous_holder"])
def test_bonpreu_two_column_pdf_populates_form(bonpreu_text, variant):
    response = create_app().test_client().post(
        "/api/invoices/extract-for-comparison",
        data={"pdf": (BytesIO(bonpreu_pdf(bonpreu_text, variant)), "bonpreu-synthetic.pdf")},
    )
    assert response.status_code == 200
    payload = response.get_json()
    form = payload["comparison_input"]
    assert form["titular"] == (None if variant in {"missing_holder", "ambiguous_holder"} else "Persona Sintètica Exemple")
    assert form["cups"] == (None if variant in {"missing_cups", "invalid_cups", "ambiguous_cups"} else "ES0000000000000000TT")
    assert form["contracted_power_kw_by_periods"] == {"P1": 3.4, "P2": 3.4}
    if variant == "valid":
        assert_bonpreu_fields(payload["extraction"])
    else:
        assert payload["extraction"]["data_quality"]["status"] == "needs_review"


@pytest.fixture
def bonpreu_spanish_text():
    # Labels transcribed from the supplied screenshots; identity is synthetic.
    return """Bonpreu Esclat Energia
Período de facturación: del 18/11/2023 al 17/12/2023 (Días: 30)
Por la electricidad que has consumido 0,00 €
Por la potencia contratada 15,96 €
El impuesto por la electricidad que pagas al
Estado 0,00 €
El alquiler del contador 0,80 €
Otros conceptos 1,16 €
IVA 10% 1,79 €
Importe total de la factura 19,71 €
Datos del contrato
Titular: Persona Sintética Ejemplo         Tarifa de acceso: 2.0TD
NIF: 00000000X                            Número que identifica tu punto de suministro (CUPS):
Fecha alta: 17/02/2023                     ES0000000000000000TT
Potencia contratada (kW): 5,500 kW - 5,500 kW
Información del consumo eléctrico
Número de contador: 000000001
Este número hace referencia al aparato, no al CUPS.
Período 1
Lectura anterior 17/11/2023 (Real): 542 kWh
Lectura actual 17/12/2023 (Real): 542 kWh
Consumo total del período: 0 kWh
Período 2
Lectura anterior 17/11/2023 (Real): 671 kWh
Lectura actual 17/12/2023 (Real): 671 kWh
Consumo total del período: 0 kWh
Período 3
Lectura anterior 17/11/2023 (Real): 618 kWh
Lectura actual 17/12/2023 (Real): 618 kWh
Consumo total del período: 0 kWh
Total consumo de los períodos 0 kWh
Detalle de la factura
Por la potencia contratada
Período 1
La potencia que tienes contratada 5,500 kW
Los días que comprende esta factura 30 días
El precio del peaje de acceso por día 0,077762 €/kW/día
Período 2
La potencia que tienes contratada 5,500 kW
Los días que comprende esta factura 30 días
El precio del peaje de acceso por día 0,018943 €/kW/día
Lo que te cuesta este mes la potencia contratada (Total €) 15,96 €
Por la electricidad que has consumido
Energía consumida
El precio que tiene la electricidad 0,000000 €/kWh
Lo que has consumido este mes 0 kWh
Lo que te cuesta este mes la energía consumida (Total €) 0,00 €
Subtotal 1 15,96 €
Energía consumida + potencia contratada
El impuesto por la electricidad que pagas al Estado 0,00 €
Impuesto especial del sobre el precio de la energía consumida y la potencia
contratada
Alquiler del contador 0,80 €
Repercusión bono social 1,16 €
Subtotal 2 17,92 €
IVA 10% 1,79 €
Importe total de la factura
El total que te toca pagar 19,71 €
"""


def assert_spanish_values(result):
    assert result["retailer"] == "Bonpreu Esclat Energia"
    assert result["titular"] == "Persona Sintética Ejemplo"
    assert result["cups"] == "ES0000000000000000TT"
    assert result["billing_days"] == 30
    assert result["energy_by_periods"] == {"P1": 0, "P2": 0, "P3": 0}
    assert result["contracted_power_kw_by_periods"] == {"P1": 5.5, "P2": 5.5, "P3": None}
    assert result["competitor_energy_eur"] == 0
    assert result["competitor_power_eur"] == 15.96
    assert result["competitor_invoice_amount"] == 19.71
    assert result["meter_rental_eur"] == 0.8
    assert result["electricity_tax"] == 0
    assert result["vat_rate_percent"] == 10
    assert result["vat_amount"] == 1.79


@pytest.mark.parametrize("rate_text,expected", [("", None), ("2,5 %", 2.5), ("5,11269632 %", 5.11269632), ("\n0,5\n%", 0.5)])
@pytest.mark.parametrize("as_pdf", [False, True])
def test_bonpreu_spanish_tax_rate_only_when_stated(bonpreu_spanish_text, rate_text, expected, as_pdf):
    text = bonpreu_spanish_text.replace("Impuesto especial del sobre", f"Impuesto especial del {rate_text} sobre")
    if as_pdf:
        response = create_app().test_client().post(
            "/api/invoices/extract-for-comparison",
            data={"pdf": (BytesIO(bonpreu_pdf(text, spanish=True)), "bonpreu-es-synthetic.pdf")},
        )
        assert response.status_code == 200
        payload = response.get_json()
        result = payload["extraction"]
        assert payload["comparison_input"]["electric_tax_rate_percent"] == expected
        assert payload["comparison_input"]["cups"] == "ES0000000000000000TT"
        assert payload["comparison_input"]["titular"] == "Persona Sintética Ejemplo"
    else:
        result = extract_from_text(text)
    assert_spanish_values(result)
    assert result["electric_tax_rate_percent"] == expected
    issues = result["data_quality"]["issues"]
    if expected is None:
        assert result["data_quality"]["status"] == "needs_review"
        assert [(issue["field"], issue["code"]) for issue in issues] == [("electric_tax_rate_percent", "missing_or_unverified")]
    else:
        assert result["data_quality"] == {"status": "verified", "issues": []}


def test_bonpreu_spanish_missing_consumption_is_not_zero(bonpreu_spanish_text):
    text = bonpreu_spanish_text.replace("Consumo total del período: 0 kWh", "", 1)
    assert extract_from_text(text)["energy_by_periods"] == {"P1": None, "P2": 0, "P3": 0}


def test_bonpreu_spanish_positive_readings_are_consumption_not_meter_values(bonpreu_spanish_text):
    text = bonpreu_spanish_text
    for value in ("28,542", "25,278", "52,114"):
        text = text.replace("Consumo total del período: 0 kWh", f"Consumo total del período: {value} kWh", 1)
    assert extract_from_text(text)["energy_by_periods"] == {"P1": 28.542, "P2": 25.278, "P3": 52.114}


@pytest.mark.parametrize("adjustment,summary,expected", [("", "13,28", 13.28), ("", "16,78", None), ("Coste de ajuste por Red Eléctrica Española 3,50 €", "16,78", 13.28)])
def test_bonpreu_spanish_billed_periods_take_precedence(bonpreu_spanish_text, adjustment, summary, expected):
    text = bonpreu_spanish_text.replace("Por la electricidad que has consumido 0,00 €", f"Por la electricidad que has consumido {summary} €")
    text = text.replace("Lo que has consumido este mes 0 kWh", """Período 1
Lo que has consumido este mes 28,542 kWh
Período 2
Lo que has consumido este mes 25,278 kWh
Período 3
Lo que has consumido este mes 52,114 kWh
""" + adjustment)
    text = text.replace("energía consumida (Total €) 0,00 €", "energía consumida (Total €) 13,28 €")
    result = extract_from_text(text)
    assert result["energy_by_periods"] == {"P1": 28.542, "P2": 25.278, "P3": 52.114}
    assert result["competitor_energy_eur"] == expected
    # An incomplete billed breakdown must not be filled with rounded readings.
    text = text.replace("Lo que has consumido este mes 28,542 kWh", "")
    assert extract_from_text(text)["energy_by_periods"]["P1"] is None
