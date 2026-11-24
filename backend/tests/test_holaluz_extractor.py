"""Synthetic Holaluz layouts: never include customer invoice data here."""

from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
import pytest

from app.services.invoice_extractor import extract_from_text, extract_pdf


@pytest.fixture
def classic_text():
    return """
Holaluz
Factura dels dies 1 d'octubre 2026 - 31 d’octubre 2026
Aquest mes has utilitzat 360 kWh
La teva potència màxima utilitzada
P1: 8,10 kW P2: 7,40 kW
Titular del subministrament:
PERSONA EXEMPLE PRIMER-
SEGON
NIF:
00000000T
CUPS:
ES0000000000000000TT
Tarifa d'accés: 20TD
Potència contractada:
P1 5,50 kW P2 4,40 kW
Les teves lectures d'aquest mes
Última lectura Lectura actual Consum
calculada calculada total
Total 8.000 kWh 8.360 kWh 360 kWh
P1 2.000 kWh 2.080 kWh 80 kWh
P2 2.000 kWh 2.060 kWh 60 kWh
P3 4.000 kWh 4.220 kWh 220 kWh
Impost elèctric i bo social 5,00 €
Impost Elèctric 80,00 € 5,11 % 4,09 €
Lloguer de comptador 0,90 €
IVA 84,99 € 21,00 % 17,85 €
TOTAL FACTURA 102,84 €
"""


@pytest.fixture
def justa_text():
    return """
Holaluz
Factura de los días 1 de octubre 2026 - 31 de octubre 2026
Este mes has consumido 120 kWh
Tu potencia máxima utilizada
P1: 4,10 kW P2: 4,80 kW
Nombre y apellidos:
PERSONA EJEMPLO
Titular del suministro:
PERSONA EJEMPLO
NIF:
00000000T
CUPS:
ES0000000000000001TR
Tarifa acceso: 20TD
Potencia contratada:
P1 3,50 kW P2 3,50 kW
Tu tarifa personalizada 60,00 €
Impuesto Eléctrico 60,00 € 5,11 % 3,07 €
Alquiler de contador 0,90 €
IVA 63,97 € 21,00 % 13,43 €
TOTAL TARIFA JUSTA 77,40 €
Información extra
Resumen de tu consumo estimado. Períodos Octubre 2026.
Consumo en Punta: 35 kWh. Consumo en Llano: 25 kWh.
Consumo en Valle: 60 kWh. Total: 120 kWh. Nº Contador: 123456789.
La última lectura real que tenemos es de 12345 kWh en el Periodo 1,
6789 kWh en el Periodo 2, y 4567 kWh en el Periodo 3 del día 28-09-2026.
"""


def test_classic_extracts_consumption_instead_of_readings(classic_text):
    result = extract_from_text(classic_text)
    assert result["billing_days"] == 31
    assert result["titular"] == "PERSONA EXEMPLE PRIMER- SEGON"
    assert result["cups"] == "ES0000000000000000TT"
    assert result["energy_by_periods"] == {"P1": 80, "P2": 60, "P3": 220}
    assert result["contracted_power_kw_by_periods"] == {"P1": 5.5, "P2": 4.4, "P3": None}
    assert result["competitor_invoice_amount"] == 102.84
    assert result["meter_rental_eur"] == 0.9
    assert result["electricity_tax"] == 4.09
    assert result["electric_tax_rate_percent"] == 5.11
    assert result["vat_amount"] == 17.85
    assert result["vat_rate_percent"] == 21
    assert {"field": "energy_by_periods", "code": "estimated_consumption", "message": "El consum indicat a la factura és estimat"} in result["data_quality"]["issues"]
    assert not any(issue["field"] == "contracted_power_kw_by_periods.P3" for issue in result["data_quality"]["issues"])


def test_justa_extracts_estimates_and_warns(justa_text):
    result = extract_from_text(justa_text)
    assert result["billing_days"] == 31
    assert result["titular"] == "PERSONA EJEMPLO"
    assert result["cups"] == "ES0000000000000001TR"
    assert result["energy_by_periods"] == {"P1": 35, "P2": 25, "P3": 60}
    assert result["contracted_power_kw_by_periods"] == {"P1": 3.5, "P2": 3.5, "P3": None}
    assert result["competitor_invoice_amount"] == 77.4
    assert result["electricity_tax"] == 3.07
    assert result["vat_amount"] == 13.43
    assert result["data_quality"]["status"] == "needs_review"
    assert any(issue["code"] == "estimated_consumption" for issue in result["data_quality"]["issues"])
    assert not any(issue["field"] == "contracted_power_kw_by_periods.P3" for issue in result["data_quality"]["issues"])


def test_real_readings_do_not_trigger_estimated_notice(classic_text):
    result = extract_from_text(classic_text.replace("calculada", "real"))
    assert not any(issue["code"] == "estimated_consumption" for issue in result["data_quality"]["issues"])


@pytest.mark.parametrize("rate", [5, 10, 21])
def test_vat_rate_with_left_column_text(justa_text, rate):
    text = justa_text.replace(
        "IVA 63,97 € 21,00 % 13,43 €",
        f"DISTRIBUIDORA EXEMPLE    IVA    63,97 €    {rate},00 %    13,43 €",
    )
    result = extract_from_text(text)
    assert result["vat_rate_percent"] == rate
    assert not any(issue["field"].startswith("vat_") for issue in result["data_quality"]["issues"])


def test_missing_vat_amount_does_not_require_review(justa_text):
    result = extract_from_text(justa_text.replace("IVA 63,97 € 21,00 % 13,43 €", "IVA 21 %"))
    assert result["vat_rate_percent"] == 21
    assert result["vat_amount"] is None
    assert not any(issue["field"].startswith("vat_") for issue in result["data_quality"]["issues"])


def test_missing_vat_rate_still_requires_review(justa_text):
    result = extract_from_text(justa_text.replace("IVA 63,97 € 21,00 % 13,43 €", ""))
    assert result["vat_rate_percent"] is None
    assert any(issue["field"] == "vat_rate_percent" for issue in result["data_quality"]["issues"])


def test_missing_p3_warning_is_preserved_outside_20td(classic_text):
    result = extract_from_text(classic_text.replace("20TD", "3.0TD"))
    assert any(issue["field"] == "contracted_power_kw_by_periods.P3" for issue in result["data_quality"]["issues"])


@pytest.mark.parametrize("tariff", ["20TD", "2.0TD", "3.0TD"])
@pytest.mark.parametrize("label", ["d'accés:", "acceso:"])
def test_tariff_token_survives_meter_number_concatenation(classic_text, tariff, label):
    text = classic_text.replace("Tarifa d'accés: 20TD", f"Tarifa {label}\n123456789{tariff}")
    words = [
        (1, 30, 100, 60, 110, "Tarifa"),
        (1, 65, 100, 110, 110, label),
        (1, 30, 120, 65, 130, tariff),
        (1, 300, 118, 360, 128, "123456789"),
    ]
    result = extract_from_text(text, words)
    missing_p3 = any(issue["field"] == "contracted_power_kw_by_periods.P3" for issue in result["data_quality"]["issues"])
    assert missing_p3 == (tariff == "3.0TD")
    assert result["contracted_power_kw_by_periods"] == {"P1": 5.5, "P2": 4.4, "P3": None}


@pytest.mark.parametrize("fixture_name", ["classic_text", "justa_text"])
def test_consumption_total_mismatch_is_flagged(fixture_name, request):
    text = request.getfixturevalue(fixture_name)
    text = text.replace("220 kWh", "221 kWh").replace("35 kWh", "36 kWh")
    result = extract_from_text(text)
    assert any(issue["code"] == "consumption_total_mismatch" for issue in result["data_quality"]["issues"])


def test_incomplete_estimated_summary_does_not_use_historical_readings(justa_text):
    result = extract_from_text(justa_text.replace("Consumo en Llano: 25 kWh.", ""))
    assert result["energy_by_periods"] == {"P1": 35, "P2": None, "P3": 60}


@pytest.mark.parametrize("justa", [False, True])
def test_digital_pdf_with_two_columns(justa):
    with TemporaryDirectory() as directory:
        path = Path(directory) / "synthetic.pdf"
        with fitz.open() as document:
            page = document.new_page()
            page.insert_text((30, 40), "Holaluz")
            page.insert_text((260, 60), "de los días 1 de octubre 2026 - 31 de octubre 2026", fontsize=9)
            page.insert_text((30, 100), "P1: 9,00 kW P2: 8,00 kW")
            page = document.new_page()
            page.insert_text((30, 50), "Titular del suministro:", fontsize=9)
            page.insert_text((30, 64), "PERSONA EJEMPLO PRIMER-", fontsize=9)
            page.insert_text((30, 78), "SEGUNDO", fontsize=9)
            page.insert_text((30, 98), "NIF:", fontsize=9)
            page.insert_text((30, 125), "CUPS:", fontsize=9)
            page.insert_text((30, 140), "ES0000000000000000TT", fontsize=9)
            page.insert_text((30, 170), "Potencia contratada:", fontsize=9)
            page.insert_text((30, 185), "P1 3,50 kW P2 3,50 kW", fontsize=9)
            page.insert_text((240, 64), "Desglose de tu factura", fontsize=9)
            page.insert_text((240, 98), "Impuesto Eléctrico 60,00 € 5,11 % 3,07 €", fontsize=9)
            page.insert_text((240, 120), "IVA 63,97 € 21,00 % 13,43 €", fontsize=9)
            page.insert_text((240, 145), "TOTAL TARIFA JUSTA" if justa else "TOTAL", fontsize=9)
            page.insert_text((520, 145), "77,40 EUR", fontsize=9)
            if not justa:
                page.insert_text((240, 200), "Les teves lectures d'aquest mes", fontsize=9)
                for index, (period, consumption) in enumerate((("P1", 35), ("P2", 25), ("P3", 60))):
                    page.insert_text((240, 225 + index * 18), f"{period} 2.000 kWh 2.100 kWh {consumption} kWh", fontsize=9)
            else:
                document.new_page()
                page = document.new_page()
                page.insert_text((30, 50), "Resumen de tu consumo estimado. Períodos Octubre 2026.", fontsize=9)
                page.insert_text((30, 65), "Consumo en Punta: 35 kWh. Consumo en Llano: 25 kWh.", fontsize=9)
                page.insert_text((30, 80), "Consumo en Valle: 60 kWh. Total: 120 kWh.", fontsize=9)
            document.save(path)
        result = extract_pdf(path)
    assert result["cups"] == "ES0000000000000000TT"
    assert result["titular"] == "PERSONA EJEMPLO PRIMER- SEGUNDO"
    assert result["billing_days"] == 31
    assert result["energy_by_periods"] == {"P1": 35, "P2": 25, "P3": 60}
    assert result["contracted_power_kw_by_periods"]["P1"] == 3.5
    assert result["competitor_invoice_amount"] == 77.4
