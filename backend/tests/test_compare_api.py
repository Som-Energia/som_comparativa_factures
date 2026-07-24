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
        "som_total": 38.83,
        "savings": 15.17,
        "savings_label": "Estalvi",
    }
    assert len(body["breakdown"]["energy"]) == 3
    assert body["breakdown"]["totals"][-1] == {
        "label": "Total",
        "amount": 38.83,
        "is_total": True,
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
    assert body["comparison"]["som_total"] == 0.07
    assert body["breakdown"]["totals"][-4] == {"label": "Compensació d'excedents", "amount": -0.12}
    assert body["breakdown"]["flux_solar_kwh"] == 0.0


def test_compare_limits_total_to_zero_and_returns_flux_solar():
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/api/compare",
        json=build_payload(
            billing_days=1,
            energy_by_periods={"P1": 0, "P2": 0, "P3": 0},
            contracted_power_kw_by_periods={"P1": 0, "P2": 0},
            self_consumption_surplus_kwh=3,
            meter_rental_eur=0,
            vat_rate_percent=0,
            electric_tax_rate_percent=0,
        ),
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["comparison"]["som_total"] == 0.0
    assert body["breakdown"]["flux_solar_kwh"] == 0.67


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
