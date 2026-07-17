from __future__ import annotations

from io import BytesIO

from flask import Blueprint, Response, jsonify, request, send_file

from .config import TemplateResolutionError, TemplateValidationError
from .services.calculator import ComparisonInputError, build_comparison_report
from .services.reporting import render_report_html, render_report_pdf


api = Blueprint("api", __name__)

SAMPLE_PREVIEW_PAYLOAD = {
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
    template_version = _extract_template_version(payload)
    if isinstance(template_version, Response):
        return template_version

    try:
        report = build_comparison_report(payload)
    except ComparisonInputError as exc:
        return jsonify({"errors": exc.errors}), 400

    try:
        pdf_bytes = render_report_pdf(report, template_version=template_version)
    except TemplateValidationError as exc:
        return jsonify({"errors": {"template_version": str(exc)}}), 422
    except TemplateResolutionError as exc:
        return jsonify({"errors": {"template_version": str(exc)}}), 404

    filename = f"comparison-report-{report['customer']['cups']}.pdf"
    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@api.get("/reports/comparison.preview")
def comparison_report_preview():
    template_version = _extract_template_version(request.args)
    if isinstance(template_version, Response):
        return template_version

    report = build_comparison_report(SAMPLE_PREVIEW_PAYLOAD)

    try:
        html = render_report_html(report, template_version=template_version)
    except TemplateValidationError as exc:
        return jsonify({"errors": {"template_version": str(exc)}}), 422
    except TemplateResolutionError as exc:
        return jsonify({"errors": {"template_version": str(exc)}}), 404

    return Response(html, mimetype="text/html")


def _extract_template_version(source) -> str | None | Response:
    template_version_raw = source.get("template_version")
    if template_version_raw is None:
        return None

    template_version = str(template_version_raw).strip()
    if not template_version:
        response = jsonify({"errors": {"template_version": "La versio de plantilla no pot ser buida."}})
        response.status_code = 400
        return response

    return template_version
