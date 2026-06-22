from __future__ import annotations

from flask import render_template
from weasyprint import HTML


def render_report_pdf(report: dict) -> bytes:
    html = render_template("reports/comparison_report.html", report=report, euro=euro)
    return HTML(string=html).write_pdf()


def euro(amount: float) -> str:
    return f"{amount:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
