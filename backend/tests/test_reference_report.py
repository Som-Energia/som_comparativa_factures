from pathlib import Path
import json
from html import unescape
from unittest.mock import Mock

import fitz
import pytest

from app import create_app
from app.services import reporting


pytestmark = pytest.mark.usefixtures("reference_pricing")


@pytest.fixture(autouse=True)
def report_adjustment_prices(reference_pricing, tmp_path):
    reference_pricing["adjustment_service_prices_eur_per_kwh"] = {"P1": 0.02, "P2": 0.02, "P3": 0.02}
    (tmp_path / "pricing.json").write_text(json.dumps(reference_pricing), encoding="utf-8")


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
    assert "3,29 €" in calculation_text
    assert "Sols (€) acumulats al Flux Solar" in calculation_text
    assert "28,00 €" in calculation_text
    assert "14,01 €" in calculation_text

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


def test_reference_page_resolves_outfit_fonts_from_assets_root(monkeypatch):
    html = Mock()
    html.return_value.write_pdf.return_value = b"simulation"
    reference_pdf = Mock()
    reference_pdf.tobytes.return_value = b"reference"
    monkeypatch.setattr(reporting, "ASSETS_DIR", Path("/app/assets"))
    monkeypatch.setattr(reporting, "HTML", html)
    monkeypatch.setattr(reporting, "_reference_pdf_path", lambda locale, audience: Path("reference.pdf"))
    monkeypatch.setattr(reporting, "_render_reference_simulation_html", lambda report, bundle, locale, audience: "<html></html>")
    monkeypatch.setattr(reporting.fitz, "open", Mock(side_effect=[reference_pdf, Mock()]))

    reporting._render_reference_report_pdf({}, None, "ca")

    assert html.call_args.kwargs["base_url"] == "file:///app/assets/"


def test_reference_template_pdf_renders_spanish_calculation_page():
    client = create_app().test_client()

    response = client.post("/api/reports/comparison.pdf", json=_payload() | {"locale": "es"})

    assert response.status_code == 200
    document = fitz.open(stream=response.data, filetype="pdf")
    assert document.page_count == 5

    calculation_page = document[2]
    calculation_text = calculation_page.get_text()
    assert "Persona de prova" in calculation_text
    assert "Coste por la energía utilizada" in calculation_text
    assert "Sols (€) acumulados en el Flux Solar" in calculation_text
    assert "28,00 €" in calculation_text
    assert "14,01 €" in calculation_text
    assert {link["uri"] for link in calculation_page.get_links()} == {
        "https://es.support.somenergia.coop/article/1398-que-son-los-excedentes-no-compensados",
        "https://es.support.somenergia.coop/article/1372-que-es-el-flux-solar",
    }


@pytest.mark.parametrize("locale", ["ca", "es"])
@pytest.mark.parametrize("audience", ["individual", "business"])
def test_pdf_audience_preserves_master_pages_and_calculated_amounts(locale, audience):
    client = create_app().test_client()
    payload = _payload() | {"locale": locale, "audience": audience}
    response = client.post("/api/reports/comparison.pdf", json=payload)

    assert response.status_code == 200
    with fitz.open(stream=response.data, filetype="pdf") as document, fitz.open(
        reporting._reference_pdf_path(locale, audience)
    ) as master:
        assert document.page_count == master.page_count == 5
        for index in (0, 1, 3, 4):
            assert document[index].get_text() == master[index].get_text()
            assert document[index].get_pixmap().samples == master[index].get_pixmap().samples
            assert [link.get("uri") for link in document[index].get_links()] == [
                link.get("uri") for link in master[index].get_links()
            ]
        text = document[2].get_text()
        assert payload["titular"] in text
        assert payload["cups"] in text
        assert "28,00 €" in text
        assert "14,01 €" in text
        title = (
            "Resum de la simulació" if locale == "ca" else "Resumen de la simulación"
        ) if audience == "business" else (
            "Simulació de cost de la factura" if locale == "ca" else "Simulación del coste de la factura"
        )
        assert title in text
        assert len(document[2].get_links()) == 2

    preview = client.post("/api/reports/comparison.preview", json=payload)
    assert preview.status_code == 200
    assert title in preview.get_data(as_text=True)


@pytest.mark.parametrize("audience", [None, [], "company", 1])
@pytest.mark.parametrize("endpoint", ["comparison.pdf", "comparison.preview"])
def test_report_rejects_invalid_audience(audience, endpoint):
    response = create_app().test_client().post(
        f"/api/reports/{endpoint}", json=_payload() | {"audience": audience}
    )
    assert response.status_code == 400
    assert "audience" in response.get_json()["errors"]


@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
@pytest.mark.parametrize("locale", ["ca", "es"])
@pytest.mark.parametrize("audience", ["individual", "business"])
def test_all_pdf_variants_include_weighted_adjustment_notice(version, locale, audience, reference_pricing, monkeypatch):
    reference_pricing["adjustment_service_prices_eur_per_kwh"] = {"P1": 0.012345, "P2": 0, "P3": 0.034567}
    monkeypatch.setattr("app.services.calculator.load_pricing_config", lambda: reference_pricing)
    payload = _payload() | {
        "template_version": version, "locale": locale, "audience": audience,
        "energy_by_periods": {"P1": 10, "P2": 50, "P3": 20},
    }
    expected = (
        "El preu del servei d'ajust 0,010185 € està fixat per Red Eléctrica Española (REE) "
        "i és el valor mitjà de l'últim mes."
    ) if locale == "ca" else (
        "El precio del servicio de ajuste 0,010185 € está fijado por Red Eléctrica Española (REE) "
        "y es el valor medio del último mes."
    )
    client = create_app().test_client()
    response = client.post("/api/reports/comparison.pdf", json=payload)
    assert response.status_code == 200
    with fitz.open(stream=response.data, filetype="pdf") as document:
        pages = [page for page in document if "Red Eléctrica Española" in page.get_text()]
        assert len(pages) == 1
        page = pages[0]
        text = " ".join(page.get_text().split())
        assert expected in text
        assert text.index("Total") < text.index(expected)
        if version == "v3" or audience == "business":
            assert document.page_count == 5
            footer_text = "www.somenergia.coop" if audience == "business" else (
                "Simulació factura Som Energia" if locale == "ca" else "Simulación factura Som Energia"
            )
            footer_top = min(rect.y0 for rect in page.search_for(footer_text))
            for block in page.get_text("blocks"):
                if "Red Eléctrica Española" in block[4] or "solo es válida" in block[4] or "només és vàlida" in block[4]:
                    assert block[3] < footer_top

    preview = client.post("/api/reports/comparison.preview", json=payload)
    assert preview.status_code == 200
    assert expected in unescape(preview.get_data(as_text=True))


@pytest.mark.parametrize("price, expected", [(0, "0 €"), (0.025, "0,025 €")])
def test_adjustment_notice_formats_zero_and_trims_decimal_zeros(price, expected):
    report = {"pricing": {"adjustment_service_weighted_price_eur_per_kwh": price}}
    assert expected in reporting._adjustment_notice(report, "ca")
