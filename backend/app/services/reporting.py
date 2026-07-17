from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

from flask import render_template
from weasyprint import HTML

from app.config import resolve_comparison_template_bundle


def render_report_pdf(report: dict, template_version: str | None = None) -> bytes:
    template_bundle = resolve_comparison_template_bundle(version=template_version)
    html = _render_report_html(report, template_bundle, asset_mode="pdf")
    return HTML(string=html, base_url=template_bundle.assets_dir.as_uri()).write_pdf()


def render_report_html(report: dict, template_version: str | None = None) -> str:
    template_bundle = resolve_comparison_template_bundle(version=template_version)
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
