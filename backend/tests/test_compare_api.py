from io import BytesIO
from unittest.mock import patch

import pytest

from app import create_app


pytestmark = pytest.mark.usefixtures("reference_pricing")


def build_payload(**overrides):
    payload = {
        "cups": "ES0210002100000000ZN0F",
        "titular": "Persona Persona",
        "billing_days": 30,
        "competitor_invoice_amount": 54.0,
        "energy_by_periods": {
            "P1": 34.41,
            "P2": 41.55,
            "P3": 88.63,
        },
        "contracted_power_kw_by_periods": {
            "P1": 2.3,
            "P2": 2.3,
        },
        "self_consumption_surplus_kwh": 0,
        "meter_rental_eur": 0.81,
        "vat_rate_percent": 21,
        "electric_tax_rate_percent": 5.11,
    }
    payload.update(overrides)
    return payload


def test_compare_returns_report_summary_for_valid_payload():
    app = create_app()
    client = app.test_client()

    response = client.post("/api/compare", json=build_payload())

    assert response.status_code == 200
    body = response.get_json()
    assert body["customer"] == {
        "cups": "ES0210002100000000ZN0F",
        "titular": "Persona Persona",
    }
    assert body["comparison"] == {
        "competitor_total": 54.0,
        "som_total": 41.62,
        "savings": 12.38,
        "savings_label": "Estalvi",
    }
    assert len(body["breakdown"]["energy"]) == 3
    assert body["breakdown"]["totals"][-1] == {
        "label": "Total",
        "amount": 41.62,
        "is_total": True,
    }


def test_comparison_input_defaults_only_returns_editable_values():
    client = create_app().test_client()

    response = client.get("/api/comparison-input-defaults")

    assert response.status_code == 200
    assert response.get_json() == {
        "electric_tax_rate_percent": 5.11269632,
    }


def test_pricing_returns_the_configuration_used_for_calculations():
    client = create_app().test_client()

    response = client.get("/api/pricing")

    assert response.status_code == 200
    assert response.get_json() == {
        "tariff_name": "2.0TD Periodes",
        "effective_date": "2026-05-01",
        "currency": "EUR",
        "energy_prices_eur_per_kwh": {"P1": 0.226, "P2": 0.15, "P3": 0.124},
        "contracted_power_prices_eur_per_kw_day": {
            "P1": 0.0820109589041096,
            "P2": 0.0080958904109589,
        },
        "self_consumption_surplus_price_eur_per_kwh": 0.03,
        "adjustment_service_prices_eur_per_kwh": {"P1": 0, "P2": 0, "P3": 0},
        "adjustment_service_price_date": "2026-04-01",
        "social_bonus_eur_per_day": 0.024688,
        "meter_rental_eur": 0.81,
        "electric_tax_rate": 0.0511269632,
        "vat_rate": 0.21,
    }


def test_compare_returns_validation_errors_for_invalid_payload():
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/api/compare",
        json=build_payload(cups="", billing_days=0, energy_by_periods={"P1": -1, "P2": 1, "P3": 1}),
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "errors": {
            "billing_days": "Els dies facturats han de ser un enter positiu.",
            "cups": "El CUPS és obligatori.",
            "energy_by_periods.P1": "El consum del període P1 ha de ser positiu o zero.",
        }
    }


def test_comparison_html_preview_renders_submitted_payload():
    app = create_app()
    client = app.test_client()

    response = client.post("/api/reports/comparison.preview", json=build_payload(titular="Persona JSON"))

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert "Persona JSON" in response.get_data(as_text=True)


def test_comparison_pdf_rejects_an_unsupported_locale():
    client = create_app().test_client()

    response = client.post("/api/reports/comparison.pdf", json=build_payload(locale="en"))

    assert response.status_code == 400
    assert response.get_json() == {"errors": {"locale": "L'idioma del PDF ha de ser 'ca' o 'es'."}}


def test_compare_does_not_compensate_power_when_there_is_no_energy_cost():
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/api/compare",
        json=build_payload(
            billing_days=1,
            energy_by_periods={"P1": 0, "P2": 0, "P3": 0},
            contracted_power_kw_by_periods={"P1": 1, "P2": 0},
            self_consumption_surplus_kwh=2,
            meter_rental_eur=0,
            vat_rate_percent=0,
            electric_tax_rate_percent=0,
        ),
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["comparison"]["som_total"] == 0.10
    assert body["breakdown"]["totals"][-4] == {"label": "Compensació d'excedents", "amount": 0}
    assert body["breakdown"]["flux_solar_kwh"] == 2.0
    assert body["breakdown"]["non_compensated_surplus_eur"] == 0.06
    assert body["breakdown"]["flux_solar_eur"] == 0.05


def test_compare_includes_adjustment_service_in_electric_tax_base(reference_pricing, monkeypatch):
    app = create_app()
    client = app.test_client()

    base_response = client.post(
        "/api/compare",
        json=build_payload(
            billing_days=1,
            energy_by_periods={"P1": 100, "P2": 0, "P3": 0},
            contracted_power_kw_by_periods={"P1": 0, "P2": 0},
            meter_rental_eur=0,
            vat_rate_percent=21,
            electric_tax_rate_percent=5,
        ),
    )
    reference_pricing["adjustment_service_prices_eur_per_kwh"] = {"P1": 0.01, "P2": 0, "P3": 0}
    monkeypatch.setattr("app.services.calculator.load_pricing_config", lambda: reference_pricing)
    response = client.post(
        "/api/compare",
        json=build_payload(
            billing_days=1,
            energy_by_periods={"P1": 100, "P2": 0, "P3": 0},
            contracted_power_kw_by_periods={"P1": 0, "P2": 0},
            meter_rental_eur=0,
            vat_rate_percent=21,
            electric_tax_rate_percent=5,
        ),
    )

    assert base_response.status_code == 200
    assert response.status_code == 200
    base = base_response.get_json()
    body = response.get_json()
    assert "adjustment_service_eur_per_kwh" not in body["input"]
    assert body["breakdown"]["costs"]["adjustment_services_eur"] == 1.0
    assert round(body["breakdown"]["costs"]["electric_tax_eur"] - base["breakdown"]["costs"]["electric_tax_eur"], 2) == 0.05
    assert round(body["breakdown"]["costs"]["vat_eur"] - base["breakdown"]["costs"]["vat_eur"], 2) == 0.22
    assert round(body["comparison"]["som_total"] - base["comparison"]["som_total"], 2) == 1.27


def test_compare_includes_social_bonus_but_not_meter_rental_in_electric_tax_base():
    client = create_app().test_client()

    response = client.post(
        "/api/compare",
        json=build_payload(
            billing_days=30,
            energy_by_periods={"P1": 0, "P2": 0, "P3": 0},
            contracted_power_kw_by_periods={"P1": 0, "P2": 0},
            meter_rental_eur=10,
            vat_rate_percent=21,
            electric_tax_rate_percent=5,
        ),
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["breakdown"]["costs"]["social_bonus_eur"] == 0.74
    assert body["breakdown"]["costs"]["electric_tax_eur"] == 0.04
    assert body["breakdown"]["costs"]["vat_eur"] == 2.26
    assert body["comparison"]["som_total"] == 13.04


def test_compare_uses_server_adjustment_prices_by_period(reference_pricing, monkeypatch):
    prices = {"P1": 0.012345, "P2": 0, "P3": 0.034567}
    reference_pricing["adjustment_service_prices_eur_per_kwh"] = prices
    monkeypatch.setattr("app.services.calculator.load_pricing_config", lambda: reference_pricing)
    client = create_app().test_client()
    payload = build_payload(energy_by_periods={"P1": 10, "P2": 50, "P3": 20})

    response = client.post("/api/compare", json=payload)
    assert response.status_code == 200
    report = response.get_json()
    assert report["breakdown"]["costs"]["adjustment_services_eur"] == 0.81
    assert report["pricing"]["adjustment_service_prices_eur_per_kwh"] == prices
    assert report["pricing"]["adjustment_service_price_date"] == "2026-04-01"
    assert report["pricing"]["adjustment_service_weighted_price_eur_per_kwh"] == pytest.approx(0.010184875)
    assert "adjustment_service_eur_per_kwh" not in report["input"]

    payload["adjustment_service_eur_per_kwh"] = 999
    payload["adjustment_service_prices_eur_per_kwh"] = {"P1": 999, "P2": 999, "P3": 999}
    assert client.post("/api/compare", json=payload).get_json() == report


def test_compare_adjustment_weighted_price_is_zero_without_consumption():
    response = create_app().test_client().post(
        "/api/compare", json=build_payload(energy_by_periods={"P1": 0, "P2": 0, "P3": 0}),
    )
    assert response.status_code == 200
    assert response.get_json()["pricing"]["adjustment_service_weighted_price_eur_per_kwh"] == 0


def test_compare_subtracts_surplus_compensation_from_electric_tax_base():
    app = create_app()
    client = app.test_client()

    base_response = client.post(
        "/api/compare",
        json=build_payload(
            billing_days=1,
            energy_by_periods={"P1": 100, "P2": 0, "P3": 0},
            contracted_power_kw_by_periods={"P1": 0, "P2": 0},
            meter_rental_eur=0,
            vat_rate_percent=0,
            electric_tax_rate_percent=5,
        ),
    )
    response = client.post(
        "/api/compare",
        json=build_payload(
            billing_days=1,
            energy_by_periods={"P1": 100, "P2": 0, "P3": 0},
            contracted_power_kw_by_periods={"P1": 0, "P2": 0},
            self_consumption_surplus_kwh=10,
            meter_rental_eur=0,
            vat_rate_percent=0,
            electric_tax_rate_percent=5,
        ),
    )

    assert base_response.status_code == 200
    assert response.status_code == 200
    base = base_response.get_json()
    body = response.get_json()
    assert base["breakdown"]["costs"]["electric_tax_eur"] == 1.13
    assert body["breakdown"]["costs"]["electric_tax_eur"] == 1.12


def test_compare_rounds_power_total_after_summing_periods():
    client = create_app().test_client()

    response = client.post(
        "/api/compare",
        json=build_payload(
            billing_days=1,
            energy_by_periods={"P1": 0, "P2": 0, "P3": 0},
            contracted_power_kw_by_periods={"P1": 0.1, "P2": 0.75},
            meter_rental_eur=0,
            vat_rate_percent=0,
            electric_tax_rate_percent=0,
        ),
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["breakdown"]["power"] == [
        {"period": "P1", "kw": 0.1, "unit_price": 0.0820109589041096, "amount": 0.01},
        {"period": "P2", "kw": 0.75, "unit_price": 0.0080958904109589, "amount": 0.01},
    ]
    assert body["breakdown"]["costs"]["power_eur"] == 0.01


def test_compare_keeps_social_bonus_and_returns_all_surplus_to_flux_solar():
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/api/compare",
        json=build_payload(
            billing_days=1,
            energy_by_periods={"P1": 0, "P2": 0, "P3": 0},
            contracted_power_kw_by_periods={"P1": 0, "P2": 0},
            self_consumption_surplus_kwh=6,
            meter_rental_eur=0,
            vat_rate_percent=0,
            electric_tax_rate_percent=0,
        ),
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["comparison"]["som_total"] == 0.02
    assert body["breakdown"]["flux_solar_kwh"] == 6.0
    assert body["breakdown"]["non_compensated_surplus_eur"] == 0.18
    assert body["breakdown"]["flux_solar_eur"] == 0.14


def test_compare_excess_surplus_does_not_produce_negative_taxes_or_total():
    client = create_app().test_client()

    response = client.post(
        "/api/compare",
        json=build_payload(
            billing_days=30,
            energy_by_periods={"P1": 0, "P2": 0, "P3": 0},
            contracted_power_kw_by_periods={"P1": 0, "P2": 0},
            self_consumption_surplus_kwh=1000,
            meter_rental_eur=0.81,
            vat_rate_percent=21,
            electric_tax_rate_percent=5.11269632,
        ),
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["breakdown"]["costs"]["surplus_compensation_eur"] == 0
    assert body["breakdown"]["costs"]["electric_tax_eur"] == 0.04
    assert body["breakdown"]["costs"]["vat_eur"] == 0.33
    assert body["comparison"]["som_total"] == 1.92
    assert body["breakdown"]["non_compensated_surplus_eur"] == 30
    assert body["breakdown"]["flux_solar_eur"] == 24


@pytest.mark.parametrize(
    "surplus_kwh, compensation, non_compensated, sols, electric_tax, vat, total",
    [
        (0, 0, 0, 0, 0.28, 1.40, 8.09),
        (50, 1.50, 0, 0, 0.21, 1.08, 6.20),
        (100, 3, 0, 0, 0.13, 0.74, 4.28),
        (150, 3, 1.50, 1.20, 0.13, 0.74, 4.28),
    ],
)
def test_compare_limits_compensation_to_energy_cost(
    surplus_kwh, compensation, non_compensated, sols, electric_tax, vat, total,
):
    pricing = {
        "tariff_name": "Tarifa de prova",
        "effective_date": "2026-01-01",
        "currency": "EUR",
        "energy_prices_eur_per_kwh": {"P1": 0.03},
        "adjustment_service_prices_eur_per_kwh": {"P1": 0.01, "P2": 0, "P3": 0},
        "contracted_power_prices_eur_per_kw_day": {"P1": 0.1},
        "social_bonus_eur_per_day": 0.02,
        "self_consumption_surplus_price_eur_per_kwh": 0.03,
    }
    client = create_app().test_client()

    with patch("app.services.calculator.load_pricing_config", return_value=pricing):
        response = client.post(
            "/api/compare",
            json=build_payload(
                billing_days=30,
                energy_by_periods={"P1": 100, "P2": 0, "P3": 0},
                contracted_power_kw_by_periods={"P1": 1 / 3, "P2": 0},
                self_consumption_surplus_kwh=surplus_kwh,
                meter_rental_eur=0.81,
                electric_tax_rate_percent=5,
                vat_rate_percent=21,
            ),
        )

    assert response.status_code == 200
    body = response.get_json()
    costs = body["breakdown"]["costs"]
    assert costs["energy_eur"] == 3
    assert costs["power_eur"] == 1
    assert costs["surplus_compensation_eur"] == compensation
    assert body["breakdown"]["non_compensated_surplus_eur"] == non_compensated
    assert body["breakdown"]["flux_solar_eur"] == sols
    assert body["breakdown"]["flux_solar_kwh"] == max(0, surplus_kwh - 100)
    assert costs["electric_tax_eur"] == electric_tax
    assert costs["vat_eur"] == vat
    assert body["comparison"]["som_total"] == total


@pytest.mark.parametrize(
    "energy_cost, surplus_kwh, expected_compensation, expected_surplus_kwh, expected_uncompensated, expected_sols",
    [
        (33.19, 539.80, 16.19, 0, 0, 0),
        (33.19, 539.88, 16.20, 0, 0, 0),
        (33.19, 539.99, 16.20, 0, 0, 0),
        (16.19, 539.80, 16.19, 0.13, 0, 0),
        (16.19, 539.88, 16.19, 0.21, 0.01, 0.01),
        (16.19, 539.99, 16.19, 0.32, 0.01, 0.01),
    ],
)
def test_compare_surplus_kwh_are_not_derived_from_rounded_compensation(
    energy_cost, surplus_kwh, expected_compensation, expected_surplus_kwh, expected_uncompensated, expected_sols,
):
    pricing = {
        "tariff_name": "Tarifa de prova",
        "effective_date": "2026-01-01",
        "currency": "EUR",
        "energy_prices_eur_per_kwh": {"P1": energy_cost},
        "adjustment_service_prices_eur_per_kwh": {"P1": 0, "P2": 0, "P3": 0},
        "contracted_power_prices_eur_per_kw_day": {},
        "social_bonus_eur_per_day": 0,
        "self_consumption_surplus_price_eur_per_kwh": 0.03,
    }
    client = create_app().test_client()

    with patch("app.services.calculator.load_pricing_config", return_value=pricing):
        response = client.post(
            "/api/compare",
            json=build_payload(
                energy_by_periods={"P1": 1, "P2": 0, "P3": 0},
                contracted_power_kw_by_periods={"P1": 0, "P2": 0},
                self_consumption_surplus_kwh=surplus_kwh,
            ),
        )

    assert response.status_code == 200
    breakdown = response.get_json()["breakdown"]
    assert breakdown["costs"]["surplus_compensation_eur"] == expected_compensation
    assert breakdown["flux_solar_kwh"] == expected_surplus_kwh
    assert breakdown["non_compensated_surplus_eur"] == expected_uncompensated
    assert breakdown["flux_solar_eur"] == expected_sols


def test_compare_rejects_negative_billing_values_and_invalid_percentages():
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/api/compare",
        json=build_payload(
            contracted_power_kw_by_periods={"P1": -1, "P2": 1},
            self_consumption_surplus_kwh=-1,
            meter_rental_eur=-1,
            vat_rate_percent=101,
            electric_tax_rate_percent=-1,
        ),
    )

    assert response.status_code == 400
    assert response.get_json()["errors"] == {
        "contracted_power_kw_by_periods.P1": "La potència contractada del període P1 ha de ser positiva o zero.",
        "electric_tax_rate_percent": "El tipus d'impost elèctric ha de ser entre 0 i 100.",
        "meter_rental_eur": "El lloguer del comptador ha de ser positiu o zero.",
        "self_consumption_surplus_kwh": "Els excedents d'autoconsum han de ser positius o zero.",
        "vat_rate_percent": "El tipus d'IVA ha de ser entre 0 i 100.",
    }


def build_extraction():
    return {
        "retailer": "Iberdrola",
        "cups": "ES0210002100000000ZN0F",
        "titular": "Persona Persona",
        "billing_days": 30,
        "competitor_invoice_amount": 54.0,
        "energy_by_periods": {"P1": 34.41, "P2": 41.55, "P3": 88.63},
        "contracted_power_kw_by_periods": {"P1": 2.3, "P2": 2.3, "P3": 2.3},
        "meter_rental_eur": 0.81,
        "vat_amount": 11.34,
        "vat_rate_percent": 21.0,
        "igic_lines": [],
        "igic_total_eur": None,
        "electricity_tax": 1.35,
        "electric_tax_rate_percent": 5.11,
        "self_consumption_surplus_kwh": None,
        "data_quality": {"status": "needs_review", "issues": []},
    }


def test_external_extraction_requires_a_bearer_token(monkeypatch):
    monkeypatch.setenv("INVOICE_EXTRACTOR_API_TOKEN", "test-token")
    client = create_app().test_client()

    response = client.post("/api/invoices/extract", data={"pdf": (BytesIO(b"pdf"), "invoice.pdf")})

    assert response.status_code == 401


def test_external_extraction_returns_extracted_data(monkeypatch):
    monkeypatch.setenv("INVOICE_EXTRACTOR_API_TOKEN", "test-token")
    client = create_app().test_client()

    with patch("app.routes.extract_pdf", return_value=build_extraction()):
        response = client.post(
            "/api/invoices/extract",
            data={"pdf": (BytesIO(b"pdf"), "invoice.pdf")},
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    assert response.get_json() == build_extraction()


def test_internal_extraction_returns_the_comparison_input():
    client = create_app().test_client()

    with patch("app.routes.extract_pdf", return_value=build_extraction()):
        response = client.post(
            "/api/invoices/extract-for-comparison",
            data={"pdf": (BytesIO(b"pdf"), "invoice.pdf")},
        )

    assert response.status_code == 200
    assert response.get_json()["comparison_input"] == {
        "cups": "ES0210002100000000ZN0F",
        "titular": "Persona Persona",
        "billing_days": 30,
        "competitor_invoice_amount": 54.0,
        "energy_by_periods": {"P1": 34.41, "P2": 41.55, "P3": 88.63},
        "contracted_power_kw_by_periods": {"P1": 2.3, "P2": 2.3},
        "self_consumption_surplus_kwh": None,
        "meter_rental_eur": 0.81,
        "vat_rate_percent": 21.0,
        "electric_tax_rate_percent": 5.11,
    }
