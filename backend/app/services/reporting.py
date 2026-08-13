from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

from flask import render_template
import fitz
from weasyprint import HTML

from app.config import ASSETS_DIR, TemplateResolutionError, TemplateValidationError, resolve_comparison_template_bundle

REFERENCE_COPY = {
    "ca": {
        "summary_title": "Simulació de cost de la factura",
        "current_cost": "Cost actual",
        "som_cost": "Cost amb Som Energia",
        "tariff_cost": "Cost calculat amb la tarifa {tariff_name}",
        "prices_effective": "Preus vigents a partir de l'{effective_date}",
        "detail_title": "Detall de la simulació de la teva factura amb Som Energia",
        "holder": "Titular:",
        "invoice_data": "Dades de la factura",
        "tariff_periods": "Períodes tarifaris",
        "contracted_power": "Potències contractades (kW)",
        "energy_used": "Energia utilitzada (kWh)",
        "self_consumption_surplus": "Excedents d'autoconsum (kWh)",
        "adjustment_services": "Serveis d'ajust en línia a part (€)",
        "meter_rental": "Lloguer del comptador (€)",
        "billing_days": "Dies del període facturat",
        "invoice_cost": "Cost calculat amb la tarifa {tariff_name}",
        "power_cost": "Cost per la potència contractada",
        "energy_cost": "Cost per l'energia utilitzada",
        "surplus_compensation": "Compensació d'excedents",
        "adjustment_cost": "Cost Serveis d'Ajust",
        "social_bonus": "Bo Social",
        "electric_tax": "Impost elèctric",
        "meter_rental_cost": "Cost del lloguer del comptador",
        "non_compensated_surplus": "Import dels {link} (ajust límit de compensació)",
        "non_compensated_surplus_link": "excedents no compensats",
        "flux_solar": "Sols (€) acumulats al {link}: el 80% de l'import dels excedents no compensats. Es descomptarà a les següents factures.",
        "flux_solar_link": "Flux Solar",
        "notice": "Aquesta simulació només és vàlida per aquesta factura i el resultat no és extrapolable a una altra factura ni tampoc al cost anual de la llum.",
        "footer": "Simulació factura Som Energia",
        "non_compensated_surplus_url": "https://ca.support.somenergia.coop/article/1397-que-son-els-excedents-no-compensats",
        "flux_solar_url": "https://ca.support.somenergia.coop/article/1371-que-es-el-flux-solar",
        "months": {5: "maig"},
        "date_format": "l'{day} de {month} de {year}",
    },
    "es": {
        "summary_title": "Simulación del coste de la factura",
        "current_cost": "Coste actual",
        "som_cost": "Coste con Som Energia",
        "tariff_cost": "Coste calculado con la tarifa {tariff_name}",
        "prices_effective": "Precios vigentes a partir del {effective_date}",
        "detail_title": "Detalle de la simulación de tu factura con Som Energia",
        "holder": "Titular:",
        "invoice_data": "Datos de la factura",
        "tariff_periods": "Períodos tarifarios",
        "contracted_power": "Potencias contratadas (kW)",
        "energy_used": "Energía utilizada (kWh)",
        "self_consumption_surplus": "Excedentes de autoconsumo (kWh)",
        "adjustment_services": "Servicios de ajuste en línea a parte (€)",
        "meter_rental": "Alquiler del contador (€)",
        "billing_days": "Días del período facturado",
        "invoice_cost": "Coste de la factura con la tarifa {tariff_name}",
        "power_cost": "Coste por la potencia contratada",
        "energy_cost": "Coste por la energía utilizada",
        "surplus_compensation": "Compensación de excedentes",
        "adjustment_cost": "Coste Servicios de Ajuste",
        "social_bonus": "Bono Social",
        "electric_tax": "Impuesto eléctrico",
        "meter_rental_cost": "Coste del alquiler del contador",
        "non_compensated_surplus": "Importe de los {link} (ajuste límite de compensación)",
        "non_compensated_surplus_link": "excedentes no compensados",
        "flux_solar": "Sols (€) acumulados en el {link}: el 80% del importe de los excedentes no compensados. Se descontará en las siguientes facturas.",
        "flux_solar_link": "Flux Solar",
        "notice": "Esta simulación solo es válida para esta factura y el resultado no es extrapolable a otra factura ni tampoco al coste anual de la luz.",
        "footer": "Simulación factura Som Energia",
        "non_compensated_surplus_url": "https://es.support.somenergia.coop/article/1398-que-son-los-excedentes-no-compensados",
        "flux_solar_url": "https://es.support.somenergia.coop/article/1372-que-es-el-flux-solar",
        "months": {5: "mayo"},
        "date_format": "{day} de {month} de {year}",
    },
}


def render_report_pdf(report: dict, template_version: str | None = None, locale: str = "ca") -> bytes:
    template_bundle = resolve_comparison_template_bundle(version=template_version)
    if template_bundle.version == "v3":
        return _render_reference_report_pdf(report, template_bundle, locale)

    html = _render_report_html(report, template_bundle, asset_mode="pdf")
    return HTML(string=html, base_url=template_bundle.assets_dir.as_uri()).write_pdf()


def render_report_html(report: dict, template_version: str | None = None, locale: str = "ca") -> str:
    template_bundle = resolve_comparison_template_bundle(version=template_version)
    return render_report_html_for_bundle(report, template_bundle, locale=locale)


def render_report_html_for_bundle(report: dict, template_bundle, locale: str = "ca") -> str:
    if template_bundle.version == "v3":
        return _render_reference_simulation_html(report, template_bundle, locale)

    return _render_report_html(report, template_bundle, asset_mode="html")


def euro(amount: float) -> str:
    return f"{amount:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _render_report_html(report: dict, template_bundle, *, asset_mode: str) -> str:
    content = _resolve_template_content(template_bundle.content, report)
    assets = _resolve_render_assets(template_bundle.assets, mode=asset_mode)
    return render_template(
        "reports/comparison_report.html",
        report=report,
        content=content,
        assets=assets,
        theme=template_bundle.theme,
        euro=euro,
        template_bundle=template_bundle,
    )


def _render_reference_report_pdf(report: dict, template_bundle, locale: str) -> bytes:
    reference_pdf = _reference_pdf_path(locale)
    simulation_html = _render_reference_simulation_html(report, template_bundle, locale)
    simulation_pdf = HTML(string=simulation_html, base_url=f"{ASSETS_DIR.as_uri()}/").write_pdf()

    document = fitz.open(reference_pdf)
    replacement_page = fitz.open(stream=simulation_pdf, filetype="pdf")
    document.delete_page(2)
    document.insert_pdf(replacement_page, from_page=0, to_page=0, start_at=2)
    return document.tobytes(garbage=4, deflate=True)


def _render_reference_simulation_html(report: dict, template_bundle, locale: str) -> str:
    copy = _reference_copy(locale)
    return render_template(
        "reports/comparison_reference_page.html",
        report=report,
        euro=euro,
        locale=locale,
        copy=copy,
        effective_date=_format_effective_date(report["pricing"]["effective_date"], copy),
    )


def _reference_pdf_path(locale: str) -> Path:
    deployed_path = ASSETS_DIR / "reference" / f"comparison-v3-{locale}.pdf"
    if deployed_path.is_file():
        return deployed_path

    # Running the backend directly from the checkout uses the tracked design source.
    filenames = {
        "ca": "CA_PLANTILLA_Domèstic_Simulació_Factura_Som Energia.pdf",
        "es": "ES_PLANTILLA_Domèstic_Simulació_Factura_Som Energia.pdf",
    }
    checkout_path = Path(__file__).resolve().parents[3] / "assets" / filenames[locale]
    if checkout_path.is_file():
        return checkout_path

    raise TemplateResolutionError(f"No s'ha trobat el PDF mestre en idioma '{locale}' de la plantilla de comparativa v3.")


def _reference_copy(locale: str) -> dict:
    try:
        return REFERENCE_COPY[locale]
    except KeyError as exc:
        raise TemplateValidationError(f"L'idioma '{locale}' no està disponible per al PDF de comparativa.") from exc


def _format_effective_date(value: str, copy: dict) -> str:
    year, month, day = value.split("-")
    month_number = int(month)
    if month_number in copy["months"]:
        return copy["date_format"].format(day=int(day), month=copy["months"][month_number], year=year)
    return f"{int(day)}/{month_number}/{year}"


def _resolve_template_content(content: dict, report: dict) -> dict:
    token_values = {
        "customer.titular": report["customer"]["titular"],
        "customer.cups": report["customer"]["cups"],
        "input.billing_days": report["input"]["billing_days"],
        "pricing.tariff_name": report["pricing"]["tariff_name"],
        "pricing.effective_date": report["pricing"]["effective_date"],
        "comparison.savings_label": report["comparison"]["savings_label"],
    }
    return _render_content_value(content, token_values)


def _render_content_value(value, token_values: dict[str, object]):
    if isinstance(value, str):
        rendered = value
        for token, token_value in token_values.items():
            rendered = rendered.replace(f"{{{token}}}", str(token_value))
        return rendered

    if isinstance(value, list):
        return [_render_content_value(item, token_values) for item in value]

    if isinstance(value, dict):
        return {key: _render_content_value(item, token_values) for key, item in value.items()}

    return value


def _resolve_render_assets(assets: dict, *, mode: str) -> dict:
    if mode == "pdf":
        return assets

    if mode != "html":
        raise ValueError(f"Unsupported asset render mode: {mode}")

    rendered_assets = {}
    for slot_name, asset in assets.items():
        if asset is None:
            rendered_assets[slot_name] = None
            continue

        rendered_assets[slot_name] = {
            **asset,
            "src": _asset_file_to_data_uri(asset["src"]),
        }
    return rendered_assets


def _asset_file_to_data_uri(src: str) -> str:
    parsed = urlparse(src)
    if parsed.scheme != "file":
        return src

    file_path = Path(parsed.path)
    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(file_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
