from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

from flask import render_template
import fitz
from weasyprint import HTML

from app.config import ASSETS_DIR, TemplateResolutionError, resolve_comparison_template_bundle


def render_report_pdf(report: dict, template_version: str | None = None) -> bytes:
    template_bundle = resolve_comparison_template_bundle(version=template_version)
    if template_bundle.version == "v3":
        return _render_reference_report_pdf(report, template_bundle)

    html = _render_report_html(report, template_bundle, asset_mode="pdf")
    return HTML(string=html, base_url=template_bundle.assets_dir.as_uri()).write_pdf()


def render_report_html(report: dict, template_version: str | None = None) -> str:
    template_bundle = resolve_comparison_template_bundle(version=template_version)
    return render_report_html_for_bundle(report, template_bundle)


def render_report_html_for_bundle(report: dict, template_bundle) -> str:
    if template_bundle.version == "v3":
        return _render_reference_simulation_html(report, template_bundle)

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


def _render_reference_report_pdf(report: dict, template_bundle) -> bytes:
    reference_pdf = _reference_pdf_path()
    simulation_html = _render_reference_simulation_html(report, template_bundle)
    simulation_pdf = HTML(string=simulation_html, base_url=template_bundle.assets_dir.as_uri()).write_pdf()

    document = fitz.open(reference_pdf)
    replacement_page = fitz.open(stream=simulation_pdf, filetype="pdf")
    document.delete_page(2)
    document.insert_pdf(replacement_page, from_page=0, to_page=0, start_at=2)
    return document.tobytes(garbage=4, deflate=True)


def _render_reference_simulation_html(report: dict, template_bundle) -> str:
    return render_template(
        "reports/comparison_reference_page.html",
        report=report,
        euro=euro,
        effective_date=_format_effective_date(report["pricing"]["effective_date"]),
    )


def _reference_pdf_path() -> Path:
    deployed_path = ASSETS_DIR / "reference" / "comparison-v3.pdf"
    if deployed_path.is_file():
        return deployed_path

    # Running the backend directly from the checkout uses the tracked design source.
    checkout_path = Path(__file__).resolve().parents[3] / "assets" / "CA_PLANTILLA_Domèstic_Simulació_Factura_Som Energia.pdf"
    if checkout_path.is_file():
        return checkout_path

    raise TemplateResolutionError("No s'ha trobat el PDF mestre de la plantilla de comparativa v3.")


def _format_effective_date(value: str) -> str:
    year, month, day = value.split("-")
    return f"{int(day)} de maig de {year}" if month == "05" else f"{int(day)}/{int(month)}/{year}"


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
