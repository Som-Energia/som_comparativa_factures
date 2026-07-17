from __future__ import annotations

from flask import render_template
from weasyprint import HTML

from app.config import resolve_comparison_template_bundle


def render_report_pdf(report: dict, template_version: str | None = None) -> bytes:
    template_bundle = resolve_comparison_template_bundle(version=template_version)
    html = render_template(
        "reports/comparison_report.html",
        report=report,
        euro=euro,
        template_bundle=template_bundle,
    )
    return HTML(string=html).write_pdf()


def euro(amount: float) -> str:
    return f"{amount:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
