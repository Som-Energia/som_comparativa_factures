"""Synthetic invoice fragments only; never commit customer invoice data."""

import pytest

from app.services.invoice_costs import extract_component_costs


@pytest.mark.parametrize("text,energy,power", [
    ("Consumo electricidad 200 kWh x 0,150000 €/kWh 30,00 €\nContrato: Subtotal Energía Demandada 30,00 €\nSubtotal Compensación Excedentes -30,00 €\nTérmino potencia P1 10,000 kW x 30 días x 0,100000 €/kW día 30,00 €\nTérmino potencia P2 10,000 kW x 30 días x 0,020000 €/kW día 6,00 €", 30, 36),
    ("Energía P1 10 kWh x 0,30 €/kWh 3,00 €\nEnergía P2 10 kWh x 0,20 €/kWh 2,00 €\nEnergía P3 10 kWh x 0,10 €/kWh 1,00 €\nPotencia punta 10,00 €\nPotencia valle 5,00 €", 6, 15),
    ("Importe de la energía: 1.234,56 EUR\nImporte de potencia: 12,34 EUR", 1234.56, 12.34),
    ("Consumo electricidad 0 kWh x 0,12 €/kWh 0,00 €\nTérmino potencia P1 0,00 €\nTérmino potencia P2 0,00 €", 0, 0),
])
def test_extracts_billed_costs_from_summaries_or_complete_periods(text, energy, power):
    assert extract_component_costs(text) == {"competitor_energy_eur": energy, "competitor_power_eur": power}


@pytest.mark.parametrize("summary", ["", "Energía 6,00 €\n", "Energía 5,40 €\n"])
def test_applies_component_discount_once_even_when_summary_is_already_net(summary):
    text = summary + """Energía P1 3,00 €
Energía P2 2,00 €
Energía P3 1,00 €
Descuento energía 10% -0,60 €
Potencia P1 10,00 €
Potencia P2 5,00 €
Descuento potencia -1,50 €"""
    assert extract_component_costs(text) == {"competitor_energy_eur": 5.4, "competitor_power_eur": 13.5}


@pytest.mark.parametrize("discount", ["Descuento comercial -3,00 €", "Descuento consumo y potencia -3,00 €"])
def test_unallocated_discount_prevents_automatic_cost_attribution(discount):
    result = extract_component_costs(f"Energía 20,00 €\nPotencia 10,00 €\n{discount}")
    assert all(value is None for value in result.values())


def test_ambiguous_energy_discount_does_not_invalidate_power():
    result = extract_component_costs("Energía 20,00 €\nPotencia 10,00 €\nDescuento energía 10%")
    assert result == {"competitor_energy_eur": None, "competitor_power_eur": 10}


def test_does_not_apply_a_discount_to_an_ambiguous_gross_or_net_summary():
    result = extract_component_costs("Energía 20,00 €\nDescuento energía -2,00 €")
    assert result["competitor_energy_eur"] is None


@pytest.mark.parametrize("text", [
    "Cuota fija 70,00 €\nEnergía 30,00 €\nPotencia 20,00 €",
    "Energía 0,15 €/kWh\nPotencia 0,10 €/kW día\nEnergía en el sistema 30,00 €",
    "Peaje de energía P1 3,00 €\nPeaje de energía P2 2,00 €\nPeaje de energía P3 1,00 €\nTérmino cargos potencia 10,00 €",
    "Energía P1 3,00 €\nPotencia P1 1,00 €",  # Missing periods are not zero.
    "Energía 30,00 €\nEnergía 35,00 €\nPotencia 10,00 €\nPotencia 20,00 €",
])
def test_leaves_unsupported_or_conflicting_costs_unset(text):
    assert extract_component_costs(text) == {"competitor_energy_eur": None, "competitor_power_eur": None}


def test_repeated_summary_and_detail_are_not_added_twice():
    text = "Potencia 15,00 €\nPotencia P1 10,00 €\nPotencia P2 5,00 €\n"
    assert extract_component_costs(text * 2)["competitor_power_eur"] == 15


def test_conflicting_detail_and_summary_need_review():
    text = "Potencia 15,00 €\nPotencia P1 20,00 €\nPotencia P2 5,00 €"
    assert extract_component_costs(text)["competitor_power_eur"] is None


def test_reads_columns_without_absorbing_adjacent_explanatory_text():
    text = """Potencia           12,00 €         Forma de pago: Domiciliación bancaria
Peaje de acceso: 2.0TD       Por energía consumida:        50,00 €
Energía consumida de la red ........50,00 €        > 15% Peajes de transporte
Potencia ..........................12,00 €        El importe total tiene este destino
5,90 € Distribución energía                                        0,00€"""
    assert extract_component_costs(text) == {"competitor_energy_eur": 50, "competitor_power_eur": 12}


def test_allocates_discount_using_unique_printed_base_and_sums_price_changes():
    text = """Potencia        12,00 €        Forma de pago: Domiciliación bancaria
Energía        50,00 €
Consumo 100 kWh x 0,20 Eur/kWh ..................20,00 €         > 20% Impuestos
Consumo 100 kWh x 0,30 Eur/kWh ..................30,00 €         > 15% Peajes
Descuento Indefinido 50,00 Eur x -20 % DTO ........-10,00 €         Información adicional"""
    assert extract_component_costs(text) == {"competitor_energy_eur": 40, "competitor_power_eur": 12}


def test_factor_discount_already_included_and_regulatory_continuation():
    text = """App de la comercialitzadora       Energia Activa (El preu inclou el descompte acordat)       120,00 €
Potència         10,00 €
Facturació d'accés: Terme d'energia 5,00 € Càrrec per energia 8,00 €,Terme de
Potència 8,00 € Càrrec per potència 1,00 € Excés potència 0,00 €
Energia Activa (El preu inclou el             120,00 €        Posem a disposició el desglossament
descompte acordat)           conceptes que conformen la factura. P1       100,000x0,500000€/kWh
Potència        10,00 €"""
    assert extract_component_costs(text) == {"competitor_energy_eur": 120, "competitor_power_eur": 10}


def test_repsol_fixed_term_is_not_the_regulatory_fixed_term():
    text = "Terme fix     12,00 €\nEnergia       30,00 €\nPer potència      Per energia      Per terme fix      9,00 €"
    assert extract_component_costs(text) == {"competitor_energy_eur": 30, "competitor_power_eur": 12}


def test_iberdrola_uses_consumption_detail_not_energy_summary_and_never_counts_subtotal_twice():
    text = """ENERGÍA.............12,00 €
Total importe potencia hasta 30/06/2026         12,00 €
Energía consumida       Horas no promocionadas 2 kWh x 0,40 €/kWh       0,80 €
                        Horas promocionadas 10 kWh x 0,02 €/kWh       0,20 €
Total 12 kWh hasta 30/06/2026       1,00 €
Compensación de excedentes         -0,30 €
Financiación bono social fijo      0,50 €
TOTAL ENERGÍA                    13,20 €"""
    assert extract_component_costs(text) == {"competitor_energy_eur": 1, "competitor_power_eur": 12}
    assert extract_component_costs(text + '\n' + text)["competitor_energy_eur"] == 1


def test_iberdrola_incomplete_consumption_block_is_not_a_complete_cost():
    text = """Total importe potencia hasta 30/06/2026    12,00 €
Energía consumida       Horas no promocionadas 2 kWh x 0,40 €/kWh       0,80 €
Bloque no reconocido
Total 12 kWh hasta 30/06/2026      1,00 €"""
    assert extract_component_costs(text) == {"competitor_energy_eur": None, "competitor_power_eur": 12}


def test_multiple_corrective_invoice_summaries_are_not_mixed():
    text = """Por potencia contratada        10,00 €         Dirección de suministro
Por energía consumida         150,00 €
Por potencia contratada         0,00 €
Por energía consumida          40,00 €"""
    assert all(value is None for value in extract_component_costs(text).values())


def test_dotted_leader_does_not_hide_a_negative_amount():
    assert all(value is None for value in extract_component_costs('Energía............-30,00 €\nPotencia........-12,00 €').values())


def test_holaluz_classic_uses_billed_totals_without_adjustments_or_social_bonus():
    text = """Holaluz
Per potència contractada       20,00 €
Per energia utilitzada         35,00 €
Potencia [P1] 4 kW 0,10 €/kW i día 12,00 €
         [P2] 4 kW 0,08 €/kW i día 8,00 €
Energia 250 kWh 0,14 €/kWh 35,00 €
Ajust comp. adequació demanda 3,00 €
Bo social 0,50 €
Peatge d'accés per potència 9,00 €"""
    assert extract_component_costs(text) == {"competitor_energy_eur": 35, "competitor_power_eur": 20}


def test_holaluz_justa_does_not_invent_a_split_from_a_personalized_fee():
    assert extract_component_costs("""Holaluz
Tu tarifa personalizada 60,00 €
TOTAL TARIFA JUSTA 77,00 €
Energía en Holaluz 30,00 €
Potencia 10,00 €""") == {"competitor_energy_eur": None, "competitor_power_eur": None}


def test_iberdrola_payment_plan_does_not_hide_explicit_billed_component_costs():
    text = """Su modalidad de pago es Cuota Fija
CUOTA FIJA A PAGAR 180,00 €
Total importe potencia hasta 30/06/2026          12,00 €
Energía consumida       200,00 kWh x 0,25 €/kWh          50,00 €
CARGOS NORMATIVOS
Financiación bono social fijo 0,50 €
TOTAL ENERGÍA 65,00 €"""
    assert extract_component_costs(text) == {"competitor_energy_eur": 50, "competitor_power_eur": 12}


@pytest.mark.parametrize("adjustment,expected", [("1,50", 40), ("2,50", None)])
def test_plenitude_separately_billed_adjustment_is_excluded_only_if_reconciled(adjustment, expected):
    text = f"""Por energía consumida: 41,50 €
Por potencia contratada: 12,00 €
Consumo Fácil (01-06-2026 - 30-06-2026): 200,00 kWh * 0,200000 €/kWh 40,00 €
Ajuste por variación del coste de los peajes y cargos del sistema (01-06-2026 - 30-06-2026) {adjustment} €"""
    assert extract_component_costs(text) == {"competitor_energy_eur": expected, "competitor_power_eur": 12}


@pytest.fixture
def corrected_invoice():
    return """Energía XXI
Por potencia contratada        10,00 €
Por energía consumida         100,00 €
TOTAL IMPORTE FACTURA          150,00 €
Facturación por potencia contratada ("TÉRMINO FIJO") 8,00 €
Facturación por energía consumida ("TÉRMINO VARIABLE") 80,00 €
TOTAL IMPORTE FACTURA 120,00 €
Facturación por potencia contratada ("TÉRMINO FIJO") -2,00 €
Facturación por energía consumida ("TÉRMINO VARIABLE") -20,00 €
TOTAL IMPORTE FACTURA -30,00 €
Por potencia contratada 2,00 €
Por energía consumida 20,00 €
TOTAL IMPORTE PERIODO 30,00 €
Facturación por potencia contratada ("TÉRMINO FIJO") 4,00 €
Facturación por energía consumida ("TÉRMINO VARIABLE") 40,00 €
TOTAL IMPORTE FACTURA 60,00 €"""


def test_reconciles_corrective_components_against_global_summary(corrected_invoice):
    assert extract_component_costs(corrected_invoice) == {"competitor_energy_eur": 100, "competitor_power_eur": 10}


@pytest.mark.parametrize("old,new", [
    ('VARIABLE") -20,00', 'VARIABLE") -21,00'),
    ('FIJO") 4,00', 'FIJO") 5,00'),
    ('FACTURA 60,00', 'FACTURA 61,00'),
])
def test_inconsistent_corrective_documents_require_review(corrected_invoice, old, new):
    assert extract_component_costs(corrected_invoice.replace(old, new)) == {"competitor_energy_eur": None, "competitor_power_eur": None}


def test_corrective_documents_without_global_total_or_with_repeated_bundle_need_review(corrected_invoice):
    for text in (corrected_invoice.replace("TOTAL IMPORTE FACTURA          150,00 €", ""), corrected_invoice * 2):
        assert extract_component_costs(text) == {"competitor_energy_eur": None, "competitor_power_eur": None}


def test_endesa_nested_hour_discounts_do_not_justify_unallocated_promotional_discount():
    text = """Energía 45,00 €
Potencia 15,00 €
Consumo en horas promocionadas 100 kWh x 0,30 Eur/kWh 30,00 €
Consumo en resto de horas 100 kWh x 0,20 Eur/kWh 20,00 €
Descuento horas de mayor consumo 10,00 Eur x -50 % -5,00 €
Descuento fidelidad 32,00 Eur x -10 % -3,20 €"""
    assert extract_component_costs(text) == {"competitor_energy_eur": None, "competitor_power_eur": None}
