"""Octopus regression coverage with synthetic, non-personal invoice data."""

from io import BytesIO

import fitz
import pytest

from app import create_app
from app.services.invoice_extractor import extract_from_text


@pytest.fixture
def octopus_text():
    return """Octopus Energy
Periodo: 11-03-2026 a 14-04-2026 (33 días)
Total a pagar 54,27 €
Potencia: 23,22 €
Energía Activa: 79,45 €
Alquiler de
Equipos: 0,91 €
Total factura 115,38 €
Crédito usado: -61,11 €
Datos del Contrato:                       Datos del Punto de Suministro:
Cliente: Persona Sintética Ejemplo        CUPS: ES0210002100000000ZN0F
NIF: 00000000X                            Tarifa Acceso: 2.0TD
Distribuidora: I-DE Redes Eléctricas
Potencia 23,22 €
Punta 5,50 kW * 34 días 0,097 €/kW/día 18,16 €
  Peaje de distribución 5,50 kW * 34 días 0,064 €/ kW/día 11,95 €
Valle 5,50 kW * 34 días 0,027 €/kW/día 5,06 €
Energía Activa 79,45 €
Punta 213,00 kWh 0,188 €/kWh 40,09 €
  Peaje de distribución 213,00 kWh 0,033 €/ kWh 7,08 €
Llano 199,00 kWh 0,109 €/kWh 21,76 €
Valle 246,00 kWh 0,072 €/kWh 17,60 €
Otros conceptos 1,56 €
Bono Social 34 días 0,019 €/días 0,65 €
Alquiler de Equipos 34 días 0,027 €/días 0,91 €
Impuesto Eléctrico (REDUCIDO) 660,00 kWh 0,001 €/kWh 0,66 €
IVA (REDUCIDO) 104,89 € 10,00 % 10,49 €
Total factura 115,38 €
Crédito usado -61,11 €
Total a pagar 54,27 €
Según el RDL 7/2026, el tipo impositivo del IEE queda reducido al 0,5%; estableciendo como mínimos los 0,5 €/MWh para usos
industriales y el 1 €/MWh para el resto de los casos.
Periodo P1 P2 P3 P4 P5 P6 Total
Lectura Anterior 16.650 15.565 8.181 0 0 0 40.396
Lectura Actual 16.863 15.764 8.427 0 0 0 41.054
Consumo kWh 213 199 246 0 0 0 658,000
Potencia Máx. Demandada (kW) 9,10 8,20 0 0 0 0
Potencia Facturada (kW) 5,50 5,50 5,50 5,50 5,50 5,50
Potencia Contratada (kW) 5,50 5,50 5,50 5,50 5,50 5,50
"""


def test_octopus_extracts_billed_values_and_explicit_review_reasons(octopus_text):
    result = extract_from_text(octopus_text)
    assert result["retailer"] == "Octopus Energy"
    assert result["titular"] == "Persona Sintética Ejemplo"
    assert result["cups"] == "ES0210002100000000ZN0F"
    assert result["billing_days"] == 34
    assert result["competitor_invoice_amount"] == 115.38
    assert result["competitor_energy_eur"] == 79.45
    assert result["competitor_power_eur"] == 23.22
    assert result["energy_by_periods"] == {"P1": 213, "P2": 199, "P3": 246}
    assert result["contracted_power_kw_by_periods"] == {"P1": 5.5, "P2": 5.5, "P3": None}
    assert result["meter_rental_eur"] == 0.91
    assert result["vat_rate_percent"] == 10
    assert result["vat_amount"] == 10.49
    assert result["electricity_tax"] == 0.66
    assert result["electric_tax_rate_percent"] == 0.5
    assert result["self_consumption_surplus_kwh"] is None
    assert result["data_quality"]["status"] == "needs_review"
    assert {issue["code"] for issue in result["data_quality"]["issues"]} == {
        "billing_days_mismatch", "credit_excluded", "minimum_electricity_tax",
    }


@pytest.mark.parametrize("old,new,field,expected", [
    ("Llano 199,00 kWh 0,109 €/kWh 21,76 €", "", "energy_by_periods", {"P1": 213, "P2": None, "P3": 246}),
    ("Punta 213,00 kWh", "Punta 0,00 kWh", "energy_by_periods", {"P1": 0, "P2": 199, "P3": 246}),
    ("Total factura 115,38 €", "", "competitor_invoice_amount", None),
    ("Potencia Contratada (kW) 5,50 5,50", "Potencia Contratada (kW) 4,10 6,20", "contracted_power_kw_by_periods", {"P1": 4.1, "P2": 6.2, "P3": None}),
    ("Tarifa Acceso: 2.0TD", "Tarifa Acceso: 3.0TD", "contracted_power_kw_by_periods", {"P1": None, "P2": None, "P3": None}),
    ("Alquiler de Equipos 34 días", "Alquiler de Equipos 35 días", "billing_days", None),
])
def test_octopus_does_not_fill_missing_or_conflicting_values_from_unrelated_rows(octopus_text, old, new, field, expected):
    assert extract_from_text(octopus_text.replace(old, new))[field] == expected


def test_octopus_rejects_conflicting_totals(octopus_text):
    result = extract_from_text(octopus_text + "\nTotal factura 120,00 €\n")
    assert result["competitor_invoice_amount"] is None


def test_octopus_coherent_days_do_not_trigger_mismatch(octopus_text):
    result = extract_from_text(octopus_text.replace("(33 días)", "(34 días)"))
    assert result["billing_days"] == 34
    assert not any(issue["code"] == "billing_days_mismatch" for issue in result["data_quality"]["issues"])


def test_octopus_digital_pdf_populates_comparison_form(octopus_text):
    with fitz.open() as document:
        # Multiple pages exercise the same native-text and word-coordinate path
        # as the supplied PDF, without storing customer data in the repository.
        lines = octopus_text.splitlines()
        for start in range(0, len(lines), 25):
            page = document.new_page()
            for index, line in enumerate(lines[start:start + 25]):
                page.insert_text((20, 30 + index * 20), line.replace("€", "EUR"), fontsize=6)
        pdf = document.tobytes()

    response = create_app().test_client().post(
        "/api/invoices/extract-for-comparison",
        data={"pdf": (BytesIO(pdf), "octopus-synthetic.pdf")},
    )
    assert response.status_code == 200
    payload = response.get_json()
    form = payload["comparison_input"]
    assert form["titular"] == "Persona Sintética Ejemplo"
    assert form["billing_days"] == 34
    assert form["competitor_invoice_amount"] == 115.38
    assert form["competitor_energy_eur"] == 79.45
    assert form["competitor_power_eur"] == 23.22
    assert form["energy_by_periods"] == {"P1": 213, "P2": 199, "P3": 246}
    assert form["contracted_power_kw_by_periods"] == {"P1": 5.5, "P2": 5.5}
    assert form["meter_rental_eur"] == 0.91
    assert form["vat_rate_percent"] == 10
    assert form["electric_tax_rate_percent"] == 0.5
    assert {issue["code"] for issue in payload["extraction"]["data_quality"]["issues"]} == {
        "billing_days_mismatch", "credit_excluded", "minimum_electricity_tax",
    }
