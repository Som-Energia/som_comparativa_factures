import fitz

from app import create_app


def _payload():
    return {
        "cups": "ES0210002100000000ZN0F",
        "titular": "Persona de prova",
        "billing_days": 30,
        "competitor_invoice_amount": 54.0,
        "energy_by_periods": {"P1": 34.41, "P2": 41.55, "P3": 88.63},
        "contracted_power_kw_by_periods": {"P1": 2.3, "P2": 2.3},
        "self_consumption_surplus_kwh": 2000,
        "meter_rental_eur": 0.81,
        "vat_rate_percent": 21,
        "electric_tax_rate_percent": 5.11,
        "template_version": "v3",
    }


def test_reference_template_pdf_preserves_static_pages_and_renders_calculation_page():
    client = create_app().test_client()

    response = client.post("/api/reports/comparison.pdf", json=_payload())

    assert response.status_code == 200
    document = fitz.open(stream=response.data, filetype="pdf")
    assert document.page_count == 5
    assert all(abs(page.rect.width - 595.28) < 1 for page in document)
    assert all(abs(page.rect.height - 841.89) < 1 for page in document)

    calculation_page = document[2]
    calculation_text = calculation_page.get_text()
    assert "Persona de prova" in calculation_text
    assert "ES0210002100000000ZN0F" in calculation_text
    assert "Cost per l'energia utilitzada" in calculation_text
    assert "Sols (€) acumulats al Flux Solar" in calculation_text
    assert "21,78 €" in calculation_text

    links = calculation_page.get_links()
    assert {link["uri"] for link in links} == {
        "https://ca.support.somenergia.coop/article/1397-que-son-els-excedents-no-compensats",
        "https://ca.support.somenergia.coop/article/1371-que-es-el-flux-solar",
    }
    assert sum(len(page.get_links()) for page in document) == 17

    words = calculation_page.get_text("words")
    power_label = next(word for word in words if word[4] == "Potències" and word[0] < 100)
    energy_label = next(word for word in words if word[4] == "Energia" and word[0] < 100)
    power_values = [word for word in words if word[4] == "2,30"]
    energy_values = [word for word in words if word[4] in {"34,41", "41,55", "88,63"}]

    assert len(power_values) == 2
    assert len(energy_values) == 3
    assert all(abs(word[1] - power_label[1]) < 1 for word in power_values)
    assert all(abs(word[1] - energy_label[1]) < 1 for word in energy_values)
