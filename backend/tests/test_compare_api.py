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
        "som_total": 30.92,
        "savings": 23.08,
        "savings_label": "Estalvi",
    }
    assert len(body["breakdown"]["energy"]) == 3
    assert body["breakdown"]["totals"][-1] == {
        "label": "Total",
        "amount": 30.92,
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
