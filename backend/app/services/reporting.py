from __future__ import annotations

from flask import render_template
from weasyprint import HTML

from app.config import resolve_comparison_template_bundle


def render_report_pdf(report: dict, template_version: str | None = None) -> bytes:
    template_bundle = resolve_comparison_template_bundle(version=template_version)
    content = _resolve_template_content(template_bundle.content, report)
    html = render_template(
        "reports/comparison_report.html",
        report=report,
        content=content,
        theme=template_bundle.theme,
        euro=euro,
        template_bundle=template_bundle,
    )
    return HTML(string=html).write_pdf()


def euro(amount: float) -> str:
    return f"{amount:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


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
