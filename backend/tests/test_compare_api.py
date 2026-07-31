from io import BytesIO
from unittest.mock import patch

from app import create_app


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
        "adjustment_service_eur_per_kwh": 0,
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
        "som_total": 41.67,
        "savings": 12.33,
        "savings_label": "Estalvi",
    }
    assert len(body["breakdown"]["energy"]) == 3
    assert body["breakdown"]["totals"][-1] == {
        "label": "Total",
        "amount": 41.67,
        "is_total": True,
    }


def test_comparison_input_defaults_returns_adjustment_service_price():
    client = create_app().test_client()

    response = client.get("/api/comparison-input-defaults")

    assert response.status_code == 200
    assert response.get_json() == {"adjustment_service_eur_per_kwh": 0.019}


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


def test_compare_applies_surplus_compensation_beyond_energy_cost():
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
    assert body["comparison"]["som_total"] == 0.04
    assert body["breakdown"]["totals"][-4] == {"label": "Compensació d'excedents", "amount": -0.06}
    assert body["breakdown"]["flux_solar_kwh"] == 0.0


def test_compare_adds_adjustment_service_to_the_taxable_subtotal():
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
    response = client.post(
        "/api/compare",
        json=build_payload(
            billing_days=1,
            energy_by_periods={"P1": 100, "P2": 0, "P3": 0},
            contracted_power_kw_by_periods={"P1": 0, "P2": 0},
            adjustment_service_eur_per_kwh=0.01,
            meter_rental_eur=0,
            vat_rate_percent=21,
            electric_tax_rate_percent=5,
        ),
    )

    assert base_response.status_code == 200
    assert response.status_code == 200
    base = base_response.get_json()
    body = response.get_json()
    assert body["input"]["adjustment_service_eur_per_kwh"] == 0.01
    assert body["breakdown"]["costs"]["adjustment_services_eur"] == 1.0
    assert round(body["breakdown"]["costs"]["electric_tax_eur"] - base["breakdown"]["costs"]["electric_tax_eur"], 2) == 0.05
    assert round(body["breakdown"]["costs"]["vat_eur"] - base["breakdown"]["costs"]["vat_eur"], 2) == 0.22
    assert round(body["comparison"]["som_total"] - base["comparison"]["som_total"], 2) == 1.27


def test_compare_limits_total_to_zero_and_returns_flux_solar():
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
    assert body["comparison"]["som_total"] == 0.0
    assert body["breakdown"]["flux_solar_kwh"] == 5.33
    assert body["breakdown"]["non_compensated_surplus_eur"] == 0.16
    assert body["breakdown"]["flux_solar_eur"] == 0.13


def test_compare_rejects_negative_billing_values_and_invalid_percentages():
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/api/compare",
        json=build_payload(
            contracted_power_kw_by_periods={"P1": -1, "P2": 1},
            self_consumption_surplus_kwh=-1,
            adjustment_service_eur_per_kwh=-1,
            meter_rental_eur=-1,
            vat_rate_percent=101,
            electric_tax_rate_percent=-1,
        ),
    )

    assert response.status_code == 400
    assert response.get_json()["errors"] == {
        "contracted_power_kw_by_periods.P1": "La potència contractada del període P1 ha de ser positiva o zero.",
        "adjustment_service_eur_per_kwh": "El servei d'ajust per kWh ha de ser positiu o zero.",
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
