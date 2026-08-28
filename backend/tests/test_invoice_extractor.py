import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch
from pathlib import Path

from app.services.invoice_extractor import extract_billing_days, extract_contracted_powers, extract_directory, extract_electricity_tax, extract_electricity_tax_rate, extract_energy_by_periods, extract_from_text, extract_igic, extract_meter_rental, extract_surplus_kwh, extract_titular, extract_total_amount, extract_vat_amount, extract_vat_rate, normalize_number

# All fixtures in this file are synthetic. Never add customer invoice data here.

class ExtractionTests(unittest.TestCase):
    def test_normalize_number_accepts_spanish_thousands_separator(self):
        self.assertEqual(normalize_number("1.234,56"), 1234.56)

    def test_extracts_complete_invoice_contract(self):
        text = """
        IBERDROLA CLIENTES, S.A.U.
        Titular del contrato: Persona Persona
        CUPS: ES0000000000000000TEST
        Días facturados: 30
        Energía consumida (kWh)
        P1 34,41 kWh
        P2 41,55 kWh
        P3 88,63 kWh
        Potencia punta: 3,45 kW
        Potencia valle: 3,45 kW
        Alquiler equipos medida                                                30 días x 0,00826 €/día                                                        0,25 €
        IVA                                                                21 % s/54,00 €                                                              11,34 €
        Impuesto sobre electricidad                                        2,5 % s/54,00 €                                                            1,35 €
        Total a pagar: 54,00 EUR
        """
        result = extract_from_text(text)

        self.assertEqual(result["retailer"], "Iberdrola")
        self.assertEqual(result["cups"], "ES0000000000000000TEST")
        self.assertEqual(result["titular"], "Persona Persona")
        self.assertEqual(result["billing_days"], 30)
        self.assertEqual(result["competitor_invoice_amount"], 54.0)
        self.assertEqual(result["energy_by_periods"], {"P1": 34.41, "P2": 41.55, "P3": 88.63})
        self.assertEqual(result["contracted_power_kw_by_periods"], {"P1": 3.45, "P2": 3.45, "P3": 3.45})
        self.assertEqual(result["meter_rental_eur"], 0.25)
        self.assertEqual(result["vat_amount"], 11.34)
        self.assertEqual(result["vat_rate_percent"], 21.0)
        self.assertEqual(result["electricity_tax"], 1.35)
        self.assertEqual(result["electric_tax_rate_percent"], 2.5)
        self.assertEqual(result["data_quality"]["status"], "verified")

    def test_prefers_retailer_from_the_top_left_header(self):
        words = [
            (0, 30, 40, 75, 48, "Energía", 0, 0, 0),
            (0, 80, 40, 100, 48, "XXI", 0, 0, 1),
            (0, 400, 40, 440, 48, "Endesa", 0, 0, 2),
        ]

        result = extract_from_text("Energía XXI Endesa", words)

        self.assertEqual(result["retailer"], "Energía XXI")

    def test_prefers_holaluz_before_its_iberdrola_distributor(self):
        text = "Holaluz\nDistribuidora: IBERDROLA DISTRIBUCIÓN ELÉCTRICA"

        self.assertEqual(extract_from_text(text)["retailer"], "Holaluz")

    def test_detects_factor_energia_retailer(self):
        self.assertEqual(
            extract_from_text("Factor Energía - Factura de electricitat")["retailer"],
            "Factor Energia",
        )

    def test_extracts_factor_energia_holder_from_apellidos_nombre(self):
        text = "Titular: ARAGON VERNET, CARLOS\nCUPS: ES0000000000000000TEST"

        self.assertEqual(extract_from_text(text)["titular"], "Carlos Aragon Vernet")

    def test_extracts_factor_energia_billing_days_from_del_al(self):
        text = "Període de facturació: Del 28/02/2026 al 31/03/2026"

        self.assertEqual(extract_billing_days(text), (31, False))

    def test_extracts_factor_energia_consumption_by_period(self):
        text = "Consum (kWh)\n115,050\n75,150\n148,060"

        self.assertEqual(
            extract_energy_by_periods(text),
            {"P1": 115.05, "P2": 75.15, "P3": 148.06},
        )

    def test_detects_naturgy_retailer(self):
        self.assertEqual(
            extract_from_text("Naturgy Clientes, S.A.U. - Estás en mercado libre.")["retailer"],
            "Naturgy",
        )

    def test_normalizes_a_cups_written_with_spaces(self):
        result = extract_from_text(
            "Identificación punto de suministro (CUPS): ES 0000 0000 0000 0000 TEST"
        )

        self.assertEqual(result["cups"], "ES0000000000000000TEST")

    def test_uses_layout_for_a_cups_on_the_same_row_as_its_label(self):
        words = [
            (0, 200, 329, 230, 337, "(CUPS):", 0, 0, 0),
            (0, 236, 329, 360, 337, "ES0000000000000000TEST", 0, 0, 1),
        ]

        result = extract_from_text("(CUPS):", words)

        self.assertEqual(result["cups"], "ES0000000000000000TEST")

    def test_uses_layout_to_read_titular_instead_of_the_next_text_line(self):
        words = [
            (0, 40, 184, 66, 192, "Titular", 0, 0, 0),
            (0, 153, 184, 193, 192, "Potencia:", 0, 0, 1),
            (0, 40, 197, 80, 205, "Persona", 0, 1, 0),
            (0, 82, 197, 127, 205, "Sintètica", 0, 1, 1),
        ]

        result = extract_from_text("Titular\nPotencia: C/ exemple", words)

        self.assertEqual(result["titular"], "Persona Sintètica")

    def test_extracts_multiline_iberdrola_holder_below_its_label(self):
        words = [
            (0, 40, 184, 66, 192, "Titular", 0, 0, 0),
            (0, 153, 184, 193, 192, "Potencia:", 0, 0, 1),
            (0, 40, 197, 80, 205, "Persona", 0, 1, 0),
            (0, 82, 197, 127, 205, "Sintètica", 0, 1, 1),
            (0, 40, 206, 95, 214, "Exemple", 0, 2, 0),
            (0, 153, 197, 193, 205, "Potencia", 0, 1, 2),
        ]

        self.assertEqual(
            extract_titular("Titular\nNIF titular del contrato: 00000000X", words),
            "Persona Sintètica Exemple",
        )

    def test_limits_iberdrola_holder_to_first_line_before_supply_address(self):
        words = [
            (0, 40, 184, 66, 192, "Titular", 0, 0, 0),
            (0, 153, 184, 193, 192, "Potencia:", 0, 0, 1),
            (0, 40, 197, 80, 205, "Persona", 0, 1, 0),
            (0, 82, 197, 127, 205, "Sintètica", 0, 1, 1),
            (0, 40, 206, 115, 214, "Dirección", 0, 2, 0),
            (0, 120, 206, 145, 214, "de", 0, 2, 1),
            (0, 150, 206, 245, 214, "suministro:", 0, 2, 2),
        ]

        self.assertEqual(extract_titular("Titular", words), "Persona Sintètica")

    def test_does_not_treat_nif_as_a_contract_holder(self):
        self.assertIsNone(extract_titular("NIF titular del contrato: 00000000X"))

    def test_skips_numeric_endesa_holder_candidate_for_labeled_value(self):
        words = [
            (1, 40, 100, 75, 108, "Titular", 0, 0, 0),
            (1, 40, 114, 115, 122, "B00000000", 0, 1, 0),
        ]
        text = "Titular del contrato: Empresa Sintética SL\nNIF: B00000000"

        self.assertEqual(extract_titular(text, words), "Empresa Sintética SL")

    def test_extracts_endesa_contract_holder_without_the_nif(self):
        text = "Titular del contrato: Persona Sintética Ejemplo NIF: 00000000X"

        result = extract_from_text(text)

        self.assertEqual(result["titular"], "Persona Sintética Ejemplo")

    def test_extracts_endesa_meter_rental(self):
        text = "Alquiler del contador ( 30 días x 0,026943 Eur/día ) ........................................0,81 €"
        self.assertEqual(extract_meter_rental(text), 0.81)

    def test_extracts_energia_xxi_meter_rental(self):
        text = "Alquiler del contador:                                         ( 30 días x 0,026943 Eur/día ) ....................................................................................................................0,81 €"
        self.assertEqual(extract_meter_rental(text), 0.81)

    def test_extracts_iberdrola_meter_rental(self):
        text = "Alquiler equipos medida                                                30 días x 0,00826 €/día                                                        0,25 €"
        self.assertEqual(extract_meter_rental(text), 0.25)

    def test_extracts_naturgy_meter_rental(self):
        text = "Alquiler de contador            26 días      x 0,026944 €/día                     0,70 €"
        self.assertEqual(extract_meter_rental(text), 0.70)

    def test_extracts_repsol_catalan_meter_rental(self):
        text = "Lloguer de comptadors                  1,23 €"
        self.assertEqual(extract_meter_rental(text), 1.23)

    def test_extracts_repsol_spanish_meter_rental(self):
        text = "Alquiler de contador                     0,81 €"
        self.assertEqual(extract_meter_rental(text), 0.81)

    def test_extracts_factor_energia_meter_rental(self):
        text = "Lloguer d' Equip                                                            0,81 €"
        self.assertEqual(extract_meter_rental(text), 0.81)

    def test_extracts_endesa_vat_amount(self):
        text = "IVA normal 21 %   s/ 190,41 .................................................................................39,99 €"
        self.assertEqual(extract_vat_amount(text), 39.99)

    def test_extracts_vat_rate_endesa(self):
        self.assertEqual(extract_vat_rate("IVA normal 21 %   s/ 190,41 ....39,99 €"), 21.0)

    def test_extracts_vat_rate_reduced(self):
        self.assertEqual(extract_vat_rate("IVA (10%) 100,00 €  x 10%  10,00 €"), 10.0)

    def test_extracts_endesa_igic_lines_and_total(self):
        text = """
        IGIC reducido 0 % s/ 1,09 .....................................................................................
        0,00 €
        IGIC reducido 0% s/ 133,44 .................................................................................. 0,00 € Lectura Lectura
        IGIC normal 7 % s/ 1,52 ......................................................................................... 0,11 € real real
        """

        lines, total = extract_igic(text)

        self.assertEqual(
            lines,
            [
                {"name": "reducido", "percent": 0.0, "taxable_base_eur": 1.09, "amount_eur": 0.0},
                {"name": "reducido", "percent": 0.0, "taxable_base_eur": 133.44, "amount_eur": 0.0},
                {"name": "normal", "percent": 7.0, "taxable_base_eur": 1.52, "amount_eur": 0.11},
            ],
        )
        self.assertEqual(total, 0.11)

    def test_extracts_electricity_tax_rate_endesa(self):
        text = "Impuesto electricidad ( 190,41 Eur X 5,1 %) .......................................................9,71 €"
        self.assertEqual(extract_electricity_tax_rate(text), 5.1)

    def test_extracts_electricity_tax_rate_iberdrola(self):
        text = "Impuesto sobre electricidad                                        2,5 % s/54,32 €                                                            1,36 €"
        self.assertEqual(extract_electricity_tax_rate(text), 2.5)

    def test_extracts_electricity_tax_rate_naturgy(self):
        text = "Impuesto electricidad              364,34 €    x 5,1 %                     18,58 €"
        self.assertEqual(extract_electricity_tax_rate(text), 5.1)

    def test_extracts_electricity_tax_rate_repsol(self):
        text = "Impost elèctric                          2,34 €  85,23 x 2,74680851%"
        self.assertEqual(extract_electricity_tax_rate(text), 2.74680851)

    def test_extracts_factor_energia_electricity_tax_rate_from_import_iee(self):
        text = "Import IEE 0,50000001 % s/(154,09)= 0,77 €"
        self.assertEqual(extract_electricity_tax_rate(text), 0.50000001)

    def test_extracts_factor_energia_reduced_electricity_tax_rate(self):
        text = (
            "L'impost especial sobre\n"
            "l'electricitat aplicable a la seva factura es troba reduït del\n"
            "5,11269632% al 0,500000000%"
        )
        self.assertEqual(extract_electricity_tax_rate(text), 0.5)

    def test_extracts_endesa_electricity_tax(self):
        text = "Impuesto electricidad ( 190,41 Eur X 5,1 %) .......................................................9,71 €"
        self.assertEqual(extract_electricity_tax(text), 9.71)

    def test_extracts_energia_xxi_electricity_tax_first_positive(self):
        text = (
            "Impuesto electricidad:             ( -120,00 Eur X 5,1 %) ......................................................-6,12 €\n"
            "Impuesto electricidad:                                        ( 120,00 Eur X 5,1 %) ......................................................6,12 €"
        )
        self.assertEqual(extract_electricity_tax(text), 6.12)

    def test_extracts_iberdrola_electricity_tax(self):
        text = "Impuesto sobre electricidad                                        2,5 % s/54,32 €                                                            1,36 €"
        self.assertEqual(extract_electricity_tax(text), 1.36)

    def test_extracts_naturgy_electricity_tax(self):
        text = "Impuesto electricidad              364,34 €    x 5,1 %                     18,58 €"
        self.assertEqual(extract_electricity_tax(text), 18.58)

    def test_extracts_factor_energia_electricity_tax_from_import_iee(self):
        text = "Import IEE 0,50000000 % s/(154,09)= 0,77 €"
        self.assertEqual(extract_electricity_tax(text), 0.77)

    def test_extracts_repsol_catalan_electricity_tax(self):
        text = "Impost elèctric                          2,34 €  85,23 x 2,74680851%"
        self.assertEqual(extract_electricity_tax(text), 2.34)

    def test_extracts_repsol_spanish_electricity_tax(self):
        text = "Impuesto Eléctrico                      1,98 €  72,15 x 2,74680851%"
        self.assertEqual(extract_electricity_tax(text), 1.98)

    def test_extracts_endesa_surplus_kwh(self):
        text = "Compensación excedente 155,333 kWh x -0,126842 Eur/kWh ..................-19,70 €"
        self.assertEqual(extract_surplus_kwh(text), 155.333)

    def test_extracts_iberdrola_surplus_kwh_as_absolute_value(self):
        text = "Compensación de excedentes (1)                                      -44,5 kWh x 0,123456 €/kWh"
        self.assertEqual(extract_surplus_kwh(text), 44.5)

    def test_extracts_naturgy_surplus_kwh_as_absolute_value(self):
        text = "Valoración excedentes             -26 kWh     x 0,126842 €/kWh"
        self.assertEqual(extract_surplus_kwh(text), 26.0)

    def test_returns_none_when_no_surplus(self):
        self.assertIsNone(extract_surplus_kwh("Factura sense excedents"))

    def test_extracts_iberdrola_vat_amount(self):
        text = "IVA                                                                21 % s/54,32 €                                                              11,41 €"
        self.assertEqual(extract_vat_amount(text), 11.41)

    def test_extracts_naturgy_vat_amount(self):
        text = "IVA (21%)                       364,34 €     x 21%                            76,51 €"
        self.assertEqual(extract_vat_amount(text), 76.51)

    def test_extracts_repsol_vat_amount(self):
        text = "IVA (21 %) de 85,23                    17,90 €"
        self.assertEqual(extract_vat_amount(text), 17.90)

    def test_extracts_factor_energia_vat_amount(self):
        text = "Import IVA                              21,00 % s/ (182,37) =                38,30 €"
        self.assertEqual(extract_vat_amount(text), 38.30)

    def test_extracts_endesa_contracted_powers_punta_llano_valle(self):
        text = "Potencias contratadas: punta-llano 13,900 kW; valle 13,900 kW"

        self.assertEqual(
            extract_contracted_powers(text),
            {"P1": 13.9, "P2": 13.9, "P3": 13.9},
        )

    def test_extracts_energia_xxi_contracted_powers_inline(self):
        text = "Potencia contratada en punta-llano: 3,300 kW  Potencia contratada en valle: 3,300 kW"

        self.assertEqual(
            extract_contracted_powers(text),
            {"P1": 3.3, "P2": 3.3, "P3": 3.3},
        )

    def test_extracts_iberdrola_contracted_powers_punta_valle(self):
        text = "Potencia punta: 4,60 kW\nPotencia valle: 4,60 kW"

        self.assertEqual(
            extract_contracted_powers(text),
            {"P1": 4.6, "P2": 4.6, "P3": 4.6},
        )

    def test_extracts_naturgy_contracted_powers_by_period(self):
        text = "Potencia contratada P1: 10,392 kW\nPotencia contratada P2: 10,392 kW"

        self.assertEqual(
            extract_contracted_powers(text),
            {"P1": 10.392, "P2": 10.392, "P3": 10.392},
        )

    def test_extracts_repsol_contracted_powers_inline(self):
        text = "Potència contractada                   3,5kW     3,5kW"

        self.assertEqual(
            extract_contracted_powers(text),
            {"P1": 3.5, "P2": 3.5, "P3": 3.5},
        )

    def test_extracts_repsol_contracted_powers_from_punta_vall_labels(self):
        text = "Punta: 3,5kW\nVall: 3,5kW"

        self.assertEqual(
            extract_contracted_powers(text),
            {"P1": 3.5, "P2": 3.5, "P3": 3.5},
        )

    def test_extracts_holaluz_contracted_powers_by_period(self):
        text = "P1: 3,45 kW        P2: 3,45 kW"

        self.assertEqual(
            extract_contracted_powers(text),
            {"P1": 3.45, "P2": 3.45, "P3": None},
        )

    def test_extracts_spanish_holaluz_customer_name(self):
        text = "Nombre y apellidos:\nPersona Sintética\nNIF:\n00000000X"

        self.assertEqual(extract_from_text(text)["titular"], "Persona Sintética")

    def test_extracts_catalan_holaluz_supply_holder(self):
        text = "Titular del subministrament:\nPersona Sintètica\nNIF:\n00000000X"

        self.assertEqual(extract_from_text(text)["titular"], "Persona Sintètica")

    def test_extracts_multiline_naturgy_holder(self):
        text = "Nombre: Persona Sintética\nSegundo Apellido\nDoc. Identidad: 00000000X"

        self.assertEqual(extract_from_text(text)["titular"], "Persona Sintética Segundo Apellido")

    def test_extracts_naturgy_holder_from_layout_before_next_column(self):
        words = [
            (0, 111, 608, 154, 616, "Nombre:", 0, 0, 0),
            (0, 198, 608, 225, 616, "Persona", 0, 0, 1),
            (0, 228, 608, 254, 616, "Sintética", 0, 0, 2),
            (0, 256, 608, 298, 616, "Ejemplo", 0, 0, 3),
            (0, 432, 608, 465, 616, "CNAE:", 0, 0, 4),
        ]

        self.assertEqual(extract_titular("Nombre:", words), "Persona Sintética Ejemplo")

    def test_extracts_contract_holder_ending_at_line_break(self):
        text = "Titular del contrato: Cliente Sintético\nDirección de suministro: Calle Ejemplo"

        result = extract_from_text(text)

        self.assertEqual(result["titular"], "Cliente Sintético")

    def test_extracts_contract_holder_before_a_visual_column_gap(self):
        text = "Titular del contrato: Persona Sintética Ejemplo    Campo posterior"

        result = extract_from_text(text)

        self.assertEqual(result["titular"], "Persona Sintética Ejemplo")

    def test_extracts_repsol_holder_in_catalan_and_spanish(self):
        catalan = "Nom i Cognoms del titular\nPersona Sintètica Catalana\nDNI"
        spanish = "Nombre y Apellidos del titular\nPersona Sintética Española\nDNI"

        self.assertEqual(extract_from_text(catalan)["titular"], "Persona Sintètica Catalana")
        self.assertEqual(extract_from_text(spanish)["titular"], "Persona Sintética Española")

    def test_extracts_repsol_holder_from_the_right_payment_block(self):
        words = [
            (2, 383, 115, 410, 123, "Nombre", 0, 0, 0),
            (2, 415, 115, 422, 123, "y", 0, 0, 1),
            (2, 427, 115, 473, 123, "Apellidos", 0, 0, 2),
            (2, 478, 115, 495, 123, "del", 0, 0, 3),
            (2, 500, 115, 535, 123, "titular", 0, 0, 4),
            (2, 383, 138, 432, 146, "Persona", 0, 1, 0),
            (2, 437, 138, 490, 146, "Sintética", 0, 1, 1),
            (2, 383, 170, 405, 178, "DNI", 0, 2, 0),
        ]

        text = "Repsol Comercializadora de Electricidad y Gas, S.L.U. Mercado libre"

        self.assertEqual(extract_titular(text, words), "Persona Sintética")

    def test_uses_total_label_and_currency_on_the_same_visual_row(self):
        words = [
            (0, 40, 521, 77, 532, "TOTAL", 0, 0, 0),
            (0, 198, 516, 230, 524, "123,45", 0, 0, 1),
            (0, 264, 516, 270, 524, "€", 0, 0, 2),
        ]

        self.assertEqual(extract_total_amount("TOTAL", words), 123.45)

    def test_prefers_total_to_pay_below_its_label(self):
        text = "Total a pagar\n45,34 €\nElectricidad 32,75 €"

        self.assertEqual(extract_total_amount(text), 45.34)

    def test_uses_days_facturados_value_below_its_label(self):
        words = [
            (0, 40, 397, 59, 405, "DIAS", 0, 0, 0),
            (0, 61, 397, 112, 405, "FACTURADOS:", 0, 0, 1),
            (0, 40, 407, 52, 415, "31", 0, 1, 0),
            (0, 165, 407, 180, 415, "12", 1, 1, 1),
        ]

        self.assertEqual(extract_billing_days("DIAS FACTURADOS:", words), (31, False))

    def test_extracts_catalan_and_spanish_billed_days(self):
        self.assertEqual(extract_billing_days("Dies facturats 31 Dies"), (31, False))
        self.assertEqual(extract_billing_days("Días facturados 31 Días"), (31, False))

    def test_calculates_inclusive_days_from_holaluz_header_period(self):
        text = "Factura emesa dels dies\n1 de juny 2026 - 30 de juny 2026"

        self.assertEqual(extract_billing_days(text), (30, False))

    def test_calculates_days_from_spanish_holaluz_header_period(self):
        text = "Factura emitida de los días\n1 de junio 2026 - 30 de junio 2026"

        self.assertEqual(extract_billing_days(text), (30, False))

    def test_extracts_printed_days_from_endesa_period(self):
        text = "Periodo: del 11/02/2026 a 09/03/2026 (26 días)"

        self.assertEqual(extract_billing_days(text), (26, False))

    def test_extracts_printed_days_from_endesa_billing_period(self):
        text = "Periodo de facturación: del 09/06/2026 a 09/07/2026 (30 días)"

        self.assertEqual(extract_billing_days(text), (30, False))

    def test_extracts_printed_days_from_naturgy_electricity_period(self):
        text = "Contrato:\n123456\n26 días\nPeríodo electricidad del 06/01/2026 al 31/01/2026"

        self.assertEqual(extract_billing_days(text), (26, False))

    def test_extracts_naturgy_days_from_electricity_period_layout(self):
        words = [
            (0, 75, 218, 108, 226, "Período", 0, 0, 0),
            (0, 112, 218, 180, 226, "electricidad:", 0, 0, 1),
            (0, 75, 229, 88, 237, "del", 0, 1, 0),
            (0, 91, 229, 150, 237, "06/01/2026", 0, 1, 1),
            (0, 156, 229, 164, 237, "al", 0, 1, 2),
            (0, 167, 229, 226, 237, "31/01/2026", 0, 1, 3),
        ]

        self.assertEqual(extract_billing_days("Período electricidad:", words), (26, False))

    def test_derives_days_from_catalan_and_spanish_billing_periods(self):
        catalan = "Període de facturació 15/05/2026 - 15/06/2026"
        spanish = "Periodo de facturación 21/05/2026 - 21/06/2026"

        self.assertEqual(extract_billing_days(catalan), (31, True))
        self.assertEqual(extract_billing_days(spanish), (31, True))

    def test_extracts_endesa_consumption_table_by_period(self):
        words = [
            (1, 323, 298, 360, 306, "Punta", 0, 0, 0),
            (1, 363, 298, 400, 306, "10.000,000", 0, 0, 1),
            (1, 413, 298, 450, 306, "10.100,000", 0, 0, 2),
            (1, 515, 298, 540, 306, "1,000", 0, 0, 3),
            (1, 554, 298, 580, 306, "58,992", 0, 0, 4),
            (1, 323, 306, 360, 314, "Llano", 0, 1, 0),
            (1, 363, 306, 400, 314, "10.000,000", 0, 1, 1),
            (1, 413, 306, 450, 314, "10.100,000", 0, 1, 2),
            (1, 515, 306, 540, 314, "1,000", 0, 1, 3),
            (1, 554, 306, 580, 314, "64,992", 0, 1, 4),
            (1, 323, 314, 360, 322, "Valle", 0, 2, 0),
            (1, 367, 314, 400, 322, "7.000,000", 0, 2, 1),
            (1, 417, 314, 450, 322, "7.100,000", 0, 2, 2),
            (1, 515, 314, 540, 322, "1,000", 0, 2, 3),
            (1, 550, 314, 580, 322, "122,998", 0, 2, 4),
        ]

        self.assertEqual(
            extract_energy_by_periods("", words),
            {"P1": 58.992, "P2": 64.992, "P3": 122.998},
        )

    def test_extracts_endesa_consumption_from_the_last_table_column(self):
        text = """
        Periodo 31/03/2026 30/04/2026 Multipl. Ajuste Consumo
        Punta 19.208,89 19.225,36 1,00 -4,85 11,62
        Llano 10.178,52 10.288,42 1,00 -3,39 106,51
        Valle 28.687,49 29.219,35 1,00 -1,99 529,87
        """

        self.assertEqual(
            extract_energy_by_periods(text),
            {"P1": 11.62, "P2": 106.51, "P3": 529.87},
        )

    def test_extracts_endesa_two_decimal_consumption_from_layout(self):
        words = [
            (1, 323, 298, 360, 306, "Punta", 0, 0, 0),
            (1, 363, 298, 400, 306, "19.208,89", 0, 0, 1),
            (1, 413, 298, 450, 306, "19.225,36", 0, 0, 2),
            (1, 465, 298, 490, 306, "1,00", 0, 0, 3),
            (1, 500, 298, 530, 306, "-4,85", 0, 0, 4),
            (1, 540, 298, 580, 306, "11,62", 0, 0, 5),
            (1, 323, 306, 360, 314, "Llano", 0, 1, 0),
            (1, 363, 306, 400, 314, "10.178,52", 0, 1, 1),
            (1, 413, 306, 450, 314, "10.288,42", 0, 1, 2),
            (1, 465, 306, 490, 314, "1,00", 0, 1, 3),
            (1, 500, 306, 530, 314, "-3,39", 0, 1, 4),
            (1, 540, 306, 580, 314, "106,51", 0, 1, 5),
            (1, 323, 314, 360, 322, "Valle", 0, 2, 0),
            (1, 367, 314, 400, 322, "28.687,49", 0, 2, 1),
            (1, 417, 314, 450, 322, "29.219,35", 0, 2, 2),
            (1, 465, 314, 490, 322, "1,00", 0, 2, 3),
            (1, 500, 314, 530, 322, "-1,99", 0, 2, 4),
            (1, 540, 314, 580, 322, "529,87", 0, 2, 5),
        ]

        self.assertEqual(
            extract_energy_by_periods("", words),
            {"P1": 11.62, "P2": 106.51, "P3": 529.87},
        )

    def test_extracts_energia_xxi_billed_consumption_by_period(self):
        text = """
        P1 (punta) 164,000 kWh x 0,097553 Eur/kWh
        P2 (llano) 186,640 kWh x 0,029267 Eur/kWh
        P3 (valle) 472,270 kWh x 0,003292 Eur/kWh
        """

        self.assertEqual(
            extract_energy_by_periods(text),
            {"P1": 164.0, "P2": 186.64, "P3": 472.27},
        )

    def test_extracts_naturgy_billed_consumption_by_period(self):
        text = """
        Consumo electricidad Punta 270 kWh x 0,190465 €/kWh
        Consumo electricidad Llano 712 kWh x 0,117512 €/kWh
        Consumo electricidad Valle 2.046 kWh x 0,082673 €/kWh
        """

        self.assertEqual(
            extract_energy_by_periods(text),
            {"P1": 270.0, "P2": 712.0, "P3": 2046.0},
        )

    def test_extracts_naturgy_consumption_to_bill_table(self):
        text = """
        Fecha Tipo de lectura (hasta) Lectura Consumo a facturar
        22/06/2026 Punta real 4.321 123 kWh
        22/06/2026 Llano real 5.432 456 kWh
        22/06/2026 Valle real 6.543 1.234 kWh
        """

        self.assertEqual(
            extract_energy_by_periods(text),
            {"P1": 123.0, "P2": 456.0, "P3": 1234.0},
        )

    def test_extracts_iberdrola_declared_consumption_by_period(self):
        text = """
        Las lecturas desagregadas tomadas el 31/08/2025 son: punta: 1.697 kWh;
        llano: 1.896 kWh; valle 4.289 kWh. Sus consumos desagregados han sido
        punta: 39 kWh; llano: 41 kWh; valle 75 kWh.
        """

        self.assertEqual(
            extract_energy_by_periods(text),
            {"P1": 39.0, "P2": 41.0, "P3": 75.0},
        )

    def test_extracts_repsol_detailed_energy_by_period(self):
        text = """
        Per energia
        41,234 kWh x 0,111111 €/kWh + 58,67 kWh x
        0,022222 €/kWh + 92,345 kWh x 0,003333 €/
        kWh = 7,89 €
        """

        self.assertEqual(
            extract_energy_by_periods(text),
            {"P1": 41.234, "P2": 58.67, "P3": 92.345},
        )

    def test_extracts_repsol_energy_when_columns_are_interleaved(self):
        text = """
        Per energia                         Per terme fix
        3,3 kW x 31 dies x 27,704413 €/kWany + 41,234 kWh x 0,111111 €/kWh + 58,67 kWh x
        3,3 kW x 31 dies x 0,725423 €/kWany = 7,96 € 0,022222 €/kWh + 92,345 kWh x 0,003333 €/kWh
        """

        self.assertEqual(
            extract_energy_by_periods(text),
            {"P1": 41.234, "P2": 58.67, "P3": 92.345},
        )

    def test_extract_directory_returns_ordered_results_with_source_files(self):
        with TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            (directory / "B.pdf").touch()
            (directory / "a.pdf").touch()
            (directory / "ignored.txt").touch()
            with patch(
                "app.services.invoice_extractor.extract_pdf",
                side_effect=[
                    {"cups": "ES0000000000000000TEST"},
                    {"cups": "ES0000000000000000DEMO"},
                ],
            ):
                results = extract_directory(directory)

        self.assertEqual([result["source_file"] for result in results], ["a.pdf", "B.pdf"])
        self.assertEqual(results[0]["cups"], "ES0000000000000000TEST")
        self.assertEqual(results[1]["cups"], "ES0000000000000000DEMO")

    def test_extract_directory_recurses_into_subdirectories(self):
        with TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            sub = directory / "sub"
            sub.mkdir()
            (directory / "root.pdf").touch()
            (sub / "child.pdf").touch()
            with patch(
                "app.services.invoice_extractor.extract_pdf",
                side_effect=[
                    {"cups": "ES0000000000000000ROOT"},
                    {"cups": "ES0000000000000000CHLD"},
                ],
            ):
                results = extract_directory(directory)

        self.assertEqual(
            [result["source_file"] for result in results],
            ["root.pdf", "sub/child.pdf"],
        )

    def test_extract_directory_rejects_a_pdf_that_cannot_be_processed(self):
        with TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            (directory / "broken.pdf").touch()
            with patch("app.services.invoice_extractor.extract_pdf", side_effect=ValueError("synthetic failure")):
                results = extract_directory(directory)

        self.assertEqual(results[0]["data_quality"]["status"], "rejected")
        self.assertEqual(results[0]["data_quality"]["issues"][0]["code"], "processing_error")

    def test_marks_missing_fields_for_review(self):
        result = extract_from_text("HOLALUZ\nTotal a pagar: 54,00 EUR")

        self.assertEqual(result["competitor_invoice_amount"], 54.0)
        self.assertEqual(result["data_quality"]["status"], "needs_review")
        self.assertTrue(result["data_quality"]["issues"])


if __name__ == "__main__":
    unittest.main()
