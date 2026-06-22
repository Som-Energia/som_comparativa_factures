from __future__ import annotations

from io import BytesIO

from flask import Blueprint, jsonify, request, send_file

from .services.calculator import ComparisonInputError, build_comparison_report
from .services.reporting import render_report_pdf


api = Blueprint("api", __name__)


@api.get("/health")
def healthcheck():
    return {"status": "ok"}


@api.post("/compare")
def compare():
    payload = request.get_json(silent=True) or {}

    try:
        report = build_comparison_report(payload)
    except ComparisonInputError as exc:
        return jsonify({"errors": exc.errors}), 400

    return jsonify(report)


@api.post("/reports/comparison.pdf")
def comparison_report_pdf():
    payload = request.get_json(silent=True) or {}

    try:
        report = build_comparison_report(payload)
    except ComparisonInputError as exc:
        return jsonify({"errors": exc.errors}), 400

    pdf_bytes = render_report_pdf(report)
    filename = f"comparison-report-{report['customer']['cups']}.pdf"
    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )
