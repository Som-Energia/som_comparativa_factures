#!/usr/bin/env python3
"""Extract a minimal, auditable electricity-invoice contract from a digital PDF."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import fitz
except ImportError:  # pragma: no cover - exercised by the CLI environment
    fitz = None


CUPS_PATTERN = re.compile(r"\bES(?:\s*\d){16}(?:\s*[A-Z0-9]){2,4}\b", re.IGNORECASE)
NUMBER_PATTERN = r"\d{1,3}(?:\.\d{3})*,\d{2,3}|\d+(?:[.,]\d{2,3})?"
POWER_PATTERN = r"\d{1,3}(?:\.\d{3})*,\d+|\d+(?:[.,]\d+)?"
AMOUNT_PATTERN = rf"({NUMBER_PATTERN})"
DATE_PATTERN = r"(\d{2}/\d{2}/\d{4})"
CATALAN_MONTHS = {
    "gener": 1,
    "febrer": 2,
    "març": 3,
    "abril": 4,
    "maig": 5,
    "juny": 6,
    "juliol": 7,
    "agost": 8,
    "setembre": 9,
    "octubre": 10,
    "novembre": 11,
    "desembre": 12,
}
SPANISH_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}
CATALAN_BILLING_PERIOD_PATTERN = re.compile(
    r"dels\s+dies\s+"
    r"(\d{1,2})\s+de\s+([a-zà-ÿ]+)\s+(\d{4})\s*[-–]\s*"
    r"(\d{1,2})\s+de\s+([a-zà-ÿ]+)\s+(\d{4})",
    re.IGNORECASE,
)
SPANISH_BILLING_PERIOD_PATTERN = re.compile(
    r"de\s+los\s+d[ií]as\s+"
    r"(\d{1,2})\s+de\s+([a-zá-ÿ]+)\s+(\d{4})\s*[-–]\s*"
    r"(\d{1,2})\s+de\s+([a-zá-ÿ]+)\s+(\d{4})",
    re.IGNORECASE,
)
RETAILERS = {
    "energía xxi": "Energía XXI",
    "energia xxi": "Energía XXI",
    "iberdrola": "Iberdrola",
    "naturgy": "Naturgy",
    "hola luz": "Holaluz",
    "holaluz": "Holaluz",
    "endesa": "Endesa",
    "repsol": "Repsol",
    "factor energia": "Factor Energia",
    "factor energía": "Factor Energia",
}
TITULAR_VALUE_EXCLUSIONS = {"POTENCIA"}


def empty_result() -> dict[str, Any]:
    return {
        "retailer": None,
        "cups": None,
        "titular": None,
        "billing_days": None,
        "competitor_invoice_amount": None,
        "energy_by_periods": {"P1": None, "P2": None, "P3": None},
        "contracted_power_kw_by_periods": {"P1": None, "P2": None, "P3": None},
        "meter_rental_eur": None,
        "vat_amount": None,
        "vat_rate_percent": None,
        "igic_lines": [],
        "igic_total_eur": None,
        "electricity_tax": None,
        "electric_tax_rate_percent": None,
        "self_consumption_surplus_kwh": None,
        "data_quality": {"status": "needs_review", "issues": []},
    }


def add_issue(result: dict[str, Any], field: str, code: str, message: str) -> None:
    result["data_quality"]["issues"].append(
        {"field": field, "code": code, "message": message}
    )


def normalize_number(value: str) -> float:
    """Convert Spanish and standard decimal notation to a JSON number."""
    value = value.strip().replace(" ", "")
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    return float(value)


def is_titular_value(value: str) -> bool:
    return bool(value) and not any(character.isdigit() for character in value) and any(
        character.isalpha() for character in value
    )


def detect_retailer(text: str) -> str | None:
    lowered = text.lower()
    matches = [
        (lowered.index(anchor), retailer)
        for anchor, retailer in RETAILERS.items()
        if anchor in lowered
    ]
    return min(matches, default=(None, None), key=lambda match: match[0])[1]


def extract_retailer(text: str, words: list[tuple[Any, ...]] | None = None) -> str | None:
    if words:
        header = " ".join(
            word[5]
            for word in sorted(words, key=lambda word: (word[0], word[2], word[1]))
            if word[0] == 0 and word[1] < 300 and word[2] < 180
        )
        retailer = detect_retailer(header)
        if retailer:
            return retailer
    return detect_retailer(text)


def extract_cups(text: str, words: list[tuple[Any, ...]] | None = None) -> str | None:
    if words:
        for label in words:
            if "CUPS" not in label[5].upper():
                continue
            for candidate in words:
                if (
                    candidate[0] == label[0]
                    and abs(candidate[2] - label[2]) < 4
                    and candidate[1] > label[3]
                    and CUPS_PATTERN.fullmatch(candidate[5])
                ):
                    return re.sub(r"\s+", "", candidate[5]).upper()

    labeled = re.search(r"\bCUPS\b.{0,100}?" + CUPS_PATTERN.pattern, text, re.IGNORECASE | re.DOTALL)
    match = CUPS_PATTERN.search(labeled.group(0) if labeled else text)
    return re.sub(r"\s+", "", match.group(0)).upper() if match else None


def extract_titular(text: str, words: list[tuple[Any, ...]] | None = None) -> str | None:
    if words:
        for label in words:
            if label[5].casefold() != "nombre:":
                continue
            value_words = sorted(
                (
                    word
                    for word in words
                    if word[0] == label[0]
                    and abs(word[2] - label[2]) < 3
                    and label[3] < word[1] < label[3] + 270
                    and not any(character.isdigit() for character in word[5])
                ),
                key=lambda word: word[1],
            )
            value = " ".join(word[5] for word in value_words).strip()
            if is_titular_value(value):
                return value

    if words:
        for label in words:
            if label[5].casefold() not in {"nom", "nombre"}:
                continue
            page_number, label_x0, label_y0, _, label_y1 = label[:5]
            label_words = sorted(
                (
                    word
                    for word in words
                    if word[0] == page_number
                    and abs(word[2] - label_y0) < 3
                    and label_x0 <= word[1] < label_x0 + 170
                ),
                key=lambda word: word[1],
            )
            label_text = " ".join(word[5].casefold() for word in label_words)
            if not re.fullmatch(
                r"(?:nom i cognoms|nombre y apellidos) del titular", label_text
            ):
                continue

            below = [
                word
                for word in words
                if word[0] == page_number
                and label_y1 < word[2] < label_y1 + 25
                and label_x0 - 2 <= word[1] < label_x0 + 270
            ]
            if below:
                line_y0 = min(word[2] for word in below)
                value = " ".join(
                    word[5] for word in below if abs(word[2] - line_y0) < 3
                ).strip()
                if is_titular_value(value):
                    return value

    named_holder = re.search(
        r"(?:nom\s+i\s+cognoms|nombre\s+y\s+apellidos)\s*:\s*\n\s*([^\n]{2,120})",
        text,
        re.IGNORECASE,
    )
    if named_holder:
        value = re.sub(r"\s+", " ", named_holder.group(1)).strip()
        if is_titular_value(value):
            return value

    naturgy_holder = re.search(
        r"(?:^|\n)\s*nombre\s*:\s*((?:[^\n]+\n?){1,2}?)(?=\s*(?:doc\.?\s*identidad|direcci[oó]n\s+fiscal)\s*:)",
        text,
        re.IGNORECASE,
    )
    if naturgy_holder:
        value = re.sub(r"\s+", " ", naturgy_holder.group(1)).strip()
        if is_titular_value(value):
            return value

    factor_holder = re.search(
        r"(?:^|\n)\s*titular\s*[:\-]\s*([A-ZÁÉÍÓÚÀÈÌÒÙÜÏÑ][A-ZÁÉÍÓÚÀÈÌÒÙÜÏÑ ,]{2,80})",
        text,
        re.IGNORECASE,
    )
    if factor_holder:
        raw = re.sub(r"\s+", " ", factor_holder.group(1)).strip().rstrip(",")
        parts = [p.strip().title() for p in raw.split(",", 1)]
        value = " ".join(reversed(parts)) if len(parts) == 2 else parts[0]
        if is_titular_value(value):
            return value
            return value

    repsol_holder = re.search(
        r"(?:nom\s+i\s+cognoms|nombre\s+y\s+apellidos)\s+del\s+titular\s*\n\s*([^\n]{2,120})",
        text,
        re.IGNORECASE,
    )
    if repsol_holder:
        value = re.sub(r"\s+", " ", repsol_holder.group(1)).strip()
        if is_titular_value(value):
            return value

    if words:
        for label in words:
            page_number, label_x0, label_y0, label_x1, label_y1 = label[:5]
            if label[5].upper() != "TITULAR":
                continue
            if not any(
                word[0] == page_number
                and abs(word[2] - label_y0) < 3
                and word[1] > label_x1
                and word[5].upper().startswith("POTENCIA")
                for word in words
            ):
                continue

            # Iberdrola places the holder directly below the left-column label.
            below = [
                word
                for word in words
                if word[0] == page_number
                and label_y1 < word[2] < label_y1 + 25
                and label_x0 - 2 <= word[1] < label_x0 + 110
            ]
            if below:
                first_line_y0 = min(word[2] for word in below)
                has_supply_address = any(
                    word[5].casefold() in {"dirección", "direccion"}
                    and word[2] > first_line_y0 + 3
                    for word in below
                )
                holder_words = (
                    [word for word in below if abs(word[2] - first_line_y0) < 3]
                    if has_supply_address
                    else below
                )
                value = " ".join(
                    word[5] for word in sorted(holder_words, key=lambda word: (word[2], word[1]))
                ).strip()
                normalized_value = re.sub(r"[^A-Z]", "", value.upper())
                if (
                    value
                    and normalized_value not in TITULAR_VALUE_EXCLUSIONS
                    and is_titular_value(value)
                ):
                    return value

            values = [
                word[5]
                for word in words
                if word[0] == page_number
                and abs(word[2] - label_y0) < 3
                and label_x1 + 10 < word[1] < label_x1 + 220
            ]
            value = " ".join(values).strip()
            normalized_value = re.sub(r"[^A-Z]", "", value.upper())
            if (
                value
                and normalized_value not in TITULAR_VALUE_EXCLUSIONS
                and is_titular_value(value)
            ):
                return value

    contract_holder = re.search(
        r"(?:^|\n)\s*titular\s+del\s+contrato\s*:\s*(.+?)(?=\s+(?:nif|direcci[oó]n)\s*:|\s{2,}|\n|$)",
        text,
        re.IGNORECASE,
    )
    if contract_holder:
        value = re.sub(r"\s+", " ", contract_holder.group(1)).strip()
        if is_titular_value(value):
            return value

    match = re.search(
        r"(?:^|\n)\s*(?:titular(?:\s+del\s+(?:contrato|suministro|subministrament))?|datos\s+del\s+titular)\s*[:\-]?\s*([^\n]{2,120})",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    value = re.sub(r"\s+", " ", match.group(1)).strip(" :-")
    return value if is_titular_value(value) else None


def extract_billing_days(
    text: str, words: list[tuple[Any, ...]] | None = None
) -> tuple[int | None, bool]:
    for billing_period, months in (
        (CATALAN_BILLING_PERIOD_PATTERN.search(text), CATALAN_MONTHS),
        (SPANISH_BILLING_PERIOD_PATTERN.search(text), SPANISH_MONTHS),
    ):
        if not billing_period:
            continue
        try:
            start = datetime(
                int(billing_period.group(3)),
                months[billing_period.group(2).casefold()],
                int(billing_period.group(1)),
            ).date()
            end = datetime(
                int(billing_period.group(6)),
                months[billing_period.group(5).casefold()],
                int(billing_period.group(4)),
            ).date()
        except (KeyError, ValueError):
            continue
        else:
            return (end - start).days + 1, False

    if words:
        for label in words:
            if label[5].upper().rstrip(":") not in {"DIAS", "DÍAS"}:
                continue
            has_facturados = any(
                word[0] == label[0]
                and abs(word[2] - label[2]) < 3
                and word[1] > label[3]
                and word[5].upper().rstrip(":") == "FACTURADOS"
                for word in words
            )
            if not has_facturados:
                continue
            values = [
                word
                for word in words
                if word[0] == label[0]
                and label[4] < word[2] < label[4] + 25
                and label[1] - 2 <= word[1] < label[1] + 110
                and word[5].isdigit()
            ]
            if values:
                return int(values[0][5]), False

        for label in words:
            if label[5].casefold() != "período":
                continue
            has_electricity = any(
                word[0] == label[0]
                and abs(word[2] - label[2]) < 3
                and word[1] > label[3]
                and word[5].casefold().rstrip(":") == "electricidad"
                for word in words
            )
            if not has_electricity:
                continue
            dates = sorted(
                (
                    word
                    for word in words
                    if word[0] == label[0]
                    and label[4] < word[2] < label[4] + 35
                    and label[1] - 2 <= word[1] < label[1] + 300
                    and re.fullmatch(DATE_PATTERN, word[5])
                ),
                key=lambda word: (word[2], word[1]),
            )
            if len(dates) >= 2:
                start = datetime.strptime(dates[0][5], "%d/%m/%Y").date()
                end = datetime.strptime(dates[1][5], "%d/%m/%Y").date()
                return (end - start).days + 1, False

    naturgy_days = re.search(
        r"(\d{1,3})\s+d[ií]as\s*\n\s*per[ií]odo\s+electricidad\s+"
        r"(?:del\s+)?\d{2}/\d{2}/\d{4}\s+al\s+\d{2}/\d{2}/\d{4}",
        text,
        re.IGNORECASE,
    )
    if naturgy_days:
        return int(naturgy_days.group(1)), False

    naturgy_period = re.search(
        r"per[ií]odo\s+electricidad\s*:\s*(?:del\s+)?"
        + DATE_PATTERN
        + r"\s+al\s+"
        + DATE_PATTERN,
        text,
        re.IGNORECASE,
    )
    if naturgy_period:
        start = datetime.strptime(naturgy_period.group(1), "%d/%m/%Y").date()
        end = datetime.strptime(naturgy_period.group(2), "%d/%m/%Y").date()
        return (end - start).days + 1, False

    factor_period = re.search(
        r"(?:per[ií]ode\s+de\s+facturaci[oó]\s*:|del\s+)"
        + DATE_PATTERN
        + r"\s+al\s+"
        + DATE_PATTERN,
        text,
        re.IGNORECASE,
    )
    if factor_period:
        start = datetime.strptime(factor_period.group(1), "%d/%m/%Y").date()
        end = datetime.strptime(factor_period.group(2), "%d/%m/%Y").date()
        return (end - start).days, False

    explicit_period = re.search(
        r"\bperiodo(?:\s+de\s+facturaci[oó]n)?\s*:\s*[^\n()]{0,100}?\(\s*(\d{1,3})\s+d[ií]as\s*\)",
        text,
        re.IGNORECASE,
    )
    if explicit_period:
        return int(explicit_period.group(1)), False

    direct = re.search(r"(?:dies\s+facturats|d[ií]as?\s+(?:facturados|de\s+facturaci[oó]n)|billing\s+days)\s*[:\-]?\s*(\d{1,3})", text, re.IGNORECASE)
    if direct:
        return int(direct.group(1)), False

    period = re.search(
        r"(?:(?:per[ií]ode|periodo)\s+de\s+facturaci(?:[oó]n|ó)|periodo\s+facturado).{0,60}?"
        + DATE_PATTERN
        + r"\s*(?:a|al|\-|hasta)\s*"
        + DATE_PATTERN,
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if not period:
        return None, False
    start = datetime.strptime(period.group(1), "%d/%m/%Y").date()
    end = datetime.strptime(period.group(2), "%d/%m/%Y").date()
    return (end - start).days, True


def extract_total_amount(text: str, words: list[tuple[Any, ...]] | None = None) -> float | None:
    total_to_pay = re.search(
        r"\btotal\s+a\s+pagar\s*[:\-]?\s*" + AMOUNT_PATTERN + r"\s*(?:€|eur|euros?)?",
        text,
        re.IGNORECASE,
    )
    if total_to_pay:
        return normalize_number(total_to_pay.group(1))

    if words:
        for label in words:
            if label[5].upper().rstrip(":") != "TOTAL":
                continue
            amounts = [
                word
                for word in words
                if word[0] == label[0]
                and abs(word[2] - label[2]) < 8
                and word[1] > label[3]
                and re.fullmatch(AMOUNT_PATTERN, word[5])
            ]
            for amount in amounts:
                has_currency = any(
                    word[0] == amount[0]
                    and abs(word[2] - amount[2]) < 8
                    and amount[3] < word[1] < amount[1] + 100
                    and word[5].upper() in {"€", "EUR"}
                    for word in words
                )
                if has_currency:
                    return normalize_number(amount[5])

    match = re.search(
        r"(?:total\s+(?:a\s+pagar|factura)|importe\s+total(?:\s+a\s+pagar)?)"
        r"[^\d]{0,80}?"
        + AMOUNT_PATTERN
        + r"\s*(?:€|eur|euros?)?",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    return normalize_number(match.group(1)) if match else None


def extract_energy_by_periods(
    text: str, words: list[tuple[Any, ...]] | None = None
) -> dict[str, float | None]:
    periods: dict[str, float | None] = {"P1": None, "P2": None, "P3": None}
    naturgy_periods = {"punta": "P1", "llano": "P2", "valle": "P3"}
    naturgy_consumptions = re.findall(
        rf"consumo\s+electricidad\s+(punta|llano|valle)\s+({NUMBER_PATTERN})\s*kwh",
        text,
        re.IGNORECASE,
    )
    for label, value in naturgy_consumptions:
        normalized_value = value.replace(".", "") if re.fullmatch(
            r"\d{1,3}(?:\.\d{3})+", value
        ) else value
        periods[naturgy_periods[label.casefold()]] = normalize_number(normalized_value)
    if all(value is not None for value in periods.values()):
        return periods

    naturgy_table_consumptions = re.findall(
        rf"\b(punta|llano|valle)\s+(real|estimad[oa])\s+(?:{NUMBER_PATTERN})\s+((?:{NUMBER_PATTERN}))\s*kwh",
        text,
        re.IGNORECASE,
    )
    for label, _, value in naturgy_table_consumptions:
        normalized_value = value.replace(".", "") if re.fullmatch(
            r"\d{1,3}(?:\.\d{3})+", value
        ) else value
        periods[naturgy_periods[label.casefold()]] = normalize_number(normalized_value)
    if all(value is not None for value in periods.values()):
        return periods

    factor_consumptions = re.findall(
        rf"consum(?:o)?\s+\(kwh\)\s*\n\s*({NUMBER_PATTERN})\s*\n\s*({NUMBER_PATTERN})\s*\n\s*({NUMBER_PATTERN})",
        text,
        re.IGNORECASE,
    )
    if factor_consumptions:
        p1, p2, p3 = factor_consumptions[0]
        return {
            "P1": normalize_number(p1),
            "P2": normalize_number(p2),
            "P3": normalize_number(p3),
        }

    if words:
        for label in words:
            if not re.fullmatch(r"consum(?:o)?", label[5], re.IGNORECASE):
                continue
            has_kwh = any(
                word[0] == label[0]
                and abs(word[2] - label[2]) < 4
                and word[1] > label[3]
                and re.fullmatch(r"\(kwh\)", word[5], re.IGNORECASE)
                for word in words
            )
            if not has_kwh:
                continue
            values = sorted(
                (
                    word
                    for word in words
                    if word[0] == label[0]
                    and word[2] > label[4]
                    and word[2] < label[4] + 80
                    and label[1] - 5 <= word[1] <= label[3] + 50
                    and re.fullmatch(rf"{NUMBER_PATTERN}", word[5])
                ),
                key=lambda word: word[2],
            )
            if len(values) >= 3:
                return {
                    "P1": normalize_number(values[0][5]),
                    "P2": normalize_number(values[1][5]),
                    "P3": normalize_number(values[2][5]),
                }

    iberdrola_consumptions = re.search(
        r"sus\s+consumos\s+desagregados\s+han\s+sido\s+"
        r"punta\s*:\s*" + AMOUNT_PATTERN + r"\s*kwh\s*;\s*"
        r"llano\s*:\s*" + AMOUNT_PATTERN + r"\s*kwh\s*;\s*"
        r"valle\s*:?\s*" + AMOUNT_PATTERN + r"\s*kwh\b",
        text,
        re.IGNORECASE,
    )
    if iberdrola_consumptions:
        return {
            "P1": normalize_number(iberdrola_consumptions.group(1)),
            "P2": normalize_number(iberdrola_consumptions.group(2)),
            "P3": normalize_number(iberdrola_consumptions.group(3)),
        }

    repsol_energy = re.search(
        r"(?:per|por)\s+energ[ií]a(?P<details>.{0,500})",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if repsol_energy:
        consumptions = re.findall(
            rf"({NUMBER_PATTERN})\s*kwh\s*x",
            repsol_energy.group("details"),
            re.IGNORECASE,
        )
        if len(consumptions) >= 3:
            return {
                "P1": normalize_number(consumptions[0]),
                "P2": normalize_number(consumptions[1]),
                "P3": normalize_number(consumptions[2]),
            }

    endesa_periods = {"punta": "P1", "llano": "P2", "valle": "P3"}
    for line in text.splitlines():
        period_match = re.match(r"\s*(punta|llano|valle)\b", line, re.IGNORECASE)
        if not period_match:
            continue
        values = re.findall(rf"-?{NUMBER_PATTERN}", line)
        if len(values) >= 5:
            periods[endesa_periods[period_match.group(1).casefold()]] = normalize_number(
                values[-1]
            )

    if all(value is not None for value in periods.values()):
        return periods

    for line in text.splitlines():
        billed_period = re.match(
            r"\s*(P[123])\s*\((?:punta|llano|valle)\)\s+"
            r"(\d{1,3}(?:\.\d{3})*,\d{3})\s+kwh\s+x\b",
            line,
            re.IGNORECASE,
        )
        if billed_period and periods[billed_period.group(1)] is None:
            periods[billed_period.group(1)] = normalize_number(billed_period.group(2))

    if words:
        spanish_periods = {"punta": "P1", "llano": "P2", "valle": "P3"}
        for label in words:
            period = spanish_periods.get(label[5].lower().rstrip(":"))
            if period is None:
                continue
            readings = sorted(
                (
                    word
                    for word in words
                    if word[0] == label[0]
                    and abs(word[2] - label[2]) < 4
                    and re.fullmatch(rf"-?{NUMBER_PATTERN}", word[5])
                ),
                key=lambda word: word[1],
            )
            if len(readings) >= 4:
                periods[period] = normalize_number(readings[-1][5])

    for period in periods:
        if periods[period] is not None:
            continue
        match = re.search(
            rf"\b{period}\b[^\n]{{0,100}}?{AMOUNT_PATTERN}\s*kwh\b",
            text,
            re.IGNORECASE,
        )
        if match:
            periods[period] = normalize_number(match.group(1))
    return periods


def extract_surplus_kwh(text: str) -> float | None:
    # Patró numèric flexible per a kWh d'excedents: enters, 1 decimal o més
    kwh_pat = r"-?\d{1,3}(?:\.\d{3})*(?:[.,]\d+)?"
    patterns = [
        # Endesa: "Compensación excedente NNN,NNN kWh x -N €/kWh"
        rf"compensaci[oó]n\s+excedentes?\s+({kwh_pat})\s*kwh",
        # Iberdrola: "Compensación de excedentes (N)  -NN,N kWh x N €/kWh"
        rf"compensaci[oó]n\s+de\s+excedentes\b[^\n]{{0,30}}\s+({kwh_pat})\s*kwh",
        # Naturgy: "Valoración excedentes  -NN kWh  x N €/kWh"
        rf"valoraci[oó]n\s+excedentes\b[^\n]{{0,30}}\s+({kwh_pat})\s*kwh",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return abs(normalize_number(m.group(1)))
    return None


def extract_electricity_tax(text: str) -> float | None:
    # Endesa / Energía XXI: "Impuesto electricidad[:]  ( NNN Eur X N% ) ....N,NN €"
    # Primera ocurrència positiva (evita ajustos negatius)
    for m in re.finditer(
        rf"impuesto\s+electricidad\s*:?\s*\([^)]+\)\s*\.{{2,}}\s*(-?{AMOUNT_PATTERN[1:-1]})\s*€",
        text, re.IGNORECASE,
    ):
        val = normalize_number(m.group(1))
        if val > 0:
            return val

    # Iberdrola: "Impuesto sobre electricidad  N,NNNNNNNN % s/NN,NN €  N,NN €"  — final de línia
    m = re.search(
        rf"impuesto\s+sobre\s+electricidad\b[^\n]+?(-?{AMOUNT_PATTERN[1:-1]})\s*€\s*$",
        text, re.IGNORECASE | re.MULTILINE,
    )
    if m:
        return normalize_number(m.group(1))

    # Naturgy: "Impuesto electricidad  NNN,NN €  x N% N,NN €"  — final de línia
    m = re.search(
        rf"impuesto\s+electricidad\b[^\n]+?(-?{AMOUNT_PATTERN[1:-1]})\s*€\s*$",
        text, re.IGNORECASE | re.MULTILINE,
    )
    if m:
        return normalize_number(m.group(1))

    # Factor Energia: "Import IEE N% s/(base)= amount €" reports the final tax amount.
    m = re.search(
        rf"import\s+iee\s+\d{{1,3}}(?:[.,]\d+)?\s*%\s+s/\s*\([^)]{{1,80}}\)\s*=\s*(-?{AMOUNT_PATTERN[1:-1]})\s*€",
        text,
        re.IGNORECASE,
    )
    if m:
        return normalize_number(m.group(1))

    # Repsol (català/castellà): "Impost elèctric / Impuesto Eléctrico  N,NN €  NNN x N%"
    # L'import és el primer valor numèric de la línia
    m = re.search(
        rf"(?:impost\s+el[eè]ctric|impuesto\s+el[eé]ctrico)\s+(-?{AMOUNT_PATTERN[1:-1]})\s*€",
        text, re.IGNORECASE,
    )
    if m:
        return normalize_number(m.group(1))

    return None


def extract_vat_rate(text: str) -> float | None:
    # Busquem la primera línia/fragment que conté "IVA" o "Import IVA" seguit d'un percentatge
    m = re.search(
        r"^\s*(?:import\s+)?iva\b[^%\n]{0,100}?(\d{1,3}(?:[.,]\d+)?)\s*%",
        text, re.IGNORECASE | re.MULTILINE,
    )
    if m:
        return normalize_number(m.group(1))
    return None


def extract_igic(text: str) -> tuple[list[dict[str, float | str]], float | None]:
    lines = []
    for match in re.finditer(
        rf"^\s*igic\s+(?P<name>[^\d%\n]+?)\s+(?P<percent>\d{{1,3}}(?:[.,]\d+)?)\s*%\s*"
        rf"s/\s*(?P<taxable_base>{AMOUNT_PATTERN[1:-1]})\s*\.{{2,}}\s*"
        rf"(?P<amount>-?{AMOUNT_PATTERN[1:-1]})\s*€",
        text,
        re.IGNORECASE | re.MULTILINE,
    ):
        lines.append(
            {
                "name": match.group("name").strip().casefold(),
                "percent": normalize_number(match.group("percent")),
                "taxable_base_eur": normalize_number(match.group("taxable_base")),
                "amount_eur": normalize_number(match.group("amount")),
            }
        )

    return lines, sum(line["amount_eur"] for line in lines) if lines else None


def extract_electricity_tax_rate(text: str) -> float | None:
    # Endesa / E21: "Impuesto electricidad ( NNN Eur X N,N% )"
    m = re.search(
        r"impuesto\s+electricidad\s*:?\s*\([^)]*?(\d{1,3}(?:[.,]\d+)?)\s*%",
        text, re.IGNORECASE,
    )
    if m:
        return normalize_number(m.group(1))

    # Iberdrola: "Impuesto sobre electricidad  N,NNNNNNNN % s/..."
    m = re.search(
        r"impuesto\s+sobre\s+electricidad\b[^\n]{0,60}?(\d{1,3}(?:[.,]\d+)?)\s*%",
        text, re.IGNORECASE,
    )
    if m:
        return normalize_number(m.group(1))

    # Naturgy: "Impuesto electricidad  NNN €  x N,NNNNNN %"
    m = re.search(
        r"impuesto\s+electricidad\b[^\n]{0,40}?x\s+(\d{1,3}(?:[.,]\d+)?)\s*%",
        text, re.IGNORECASE,
    )
    if m:
        return normalize_number(m.group(1))

    # Factor Energia: "Import IEE N% s/(base)= amount €" states the applied rate directly.
    m = re.search(
        r"import\s+iee\s+(\d{1,3}(?:[.,]\d+)?)\s*%\s+s/\s*\([^)]{1,80}\)\s*=\s*-?\d",
        text,
        re.IGNORECASE,
    )
    if m:
        return normalize_number(m.group(1))

    # Factor Energia: reduced tax notice states the previous rate followed by the applied rate.
    m = re.search(
        r"impost\s+especial\s+sobre\s+l['’]electricitat\b.{0,200}?"
        r"redu[iï]t\s+del\s+\d{1,3}(?:[.,]\d+)?\s*%\s+al\s+(\d{1,3}(?:[.,]\d+)?)\s*%",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        return normalize_number(m.group(1))

    # Repsol (català/castellà): "Impost elèctric  N,NN €  NNN x N,NNNNNNNN%"
    m = re.search(
        r"(?:impost\s+el[eè]ctric|impuesto\s+el[eé]ctrico)\b[^\n]{0,50}?(\d{1,3}(?:[.,]\d+)?)\s*%",
        text, re.IGNORECASE,
    )
    if m:
        return normalize_number(m.group(1))

    return None


def extract_vat_amount(text: str) -> float | None:
    # Endesa / Energía XXI: "IVA normal[:]  NN %  s/ NNN,NN ....NN,NN €"
    # Prioritat màxima: primera ocurrència amb punts suspensius (total del període principal)
    m = re.search(
        rf"iva\s+normal\s*:?\s*\d{{1,3}}\s*%\s+s/\s*[^\n]{{1,80}}?\.{{2,}}\s*(-?{AMOUNT_PATTERN[1:-1]})\s*€",
        text, re.IGNORECASE,
    )
    if m:
        return normalize_number(m.group(1))

    # Repsol: "IVA (NN %) de NNN,NN  NN,NN €"
    m = re.search(
        rf"iva\s*\(\d{{1,3}}\s*%\)\s+de\s+[^\n]{{1,30}}?\s+(-?{AMOUNT_PATTERN[1:-1]})\s*€",
        text, re.IGNORECASE,
    )
    if m:
        return normalize_number(m.group(1))

    # Iberdrola / Naturgy / Factor Energia: línia que comença per "IVA" o "Import IVA"
    # — l'últim import de la línia és el valor de l'IVA
    m = re.search(
        rf"^\s*(?:import\s+)?iva\b[^\n]+?(-?{AMOUNT_PATTERN[1:-1]})\s*€\s*$",
        text, re.IGNORECASE | re.MULTILINE,
    )
    if m:
        return normalize_number(m.group(1))

    return None


def extract_meter_rental(text: str) -> float | None:
    # Endesa: "Alquiler del contador ( N días x N €/día ) ....N,NN €"
    m = re.search(
        rf"alquiler\s+del\s+contador\s*\([^)]+\)\s*\.+\s*({AMOUNT_PATTERN[1:-1]})\s*€",
        text, re.IGNORECASE,
    )
    if m:
        return normalize_number(m.group(1))

    # Energía XXI: "Alquiler del contador: ( N días x N €/día ) ....N,NN €"
    m = re.search(
        rf"alquiler\s+del\s+contador\s*:\s*\([^)]+\)\s*\.+\s*({AMOUNT_PATTERN[1:-1]})\s*€",
        text, re.IGNORECASE,
    )
    if m:
        return normalize_number(m.group(1))

    # Iberdrola: "Alquiler equipos medida  N días x N €/día  N,NN €"
    # L'import final és l'últim número de la línia
    m = re.search(
        rf"alquiler\s+equipos?\s+medida\b[^\n]+?({AMOUNT_PATTERN[1:-1]})\s*€\s*$",
        text, re.IGNORECASE | re.MULTILINE,
    )
    if m:
        return normalize_number(m.group(1))

    # Naturgy: "Alquiler de contador  N días  x N €/día  N,NN €"
    m = re.search(
        rf"alquiler\s+de\s+contador\b[^\n]+?({AMOUNT_PATTERN[1:-1]})\s*€\s*$",
        text, re.IGNORECASE | re.MULTILINE,
    )
    if m:
        return normalize_number(m.group(1))

    # Repsol castellà: "Alquiler de contador  N,NN €"  (sense dies ni preu/dia)
    m = re.search(
        rf"alquiler\s+de\s+contador\b\s+({AMOUNT_PATTERN[1:-1]})\s*€",
        text, re.IGNORECASE,
    )
    if m:
        return normalize_number(m.group(1))

    # Repsol català: "Lloguer de comptadors  N,NN €"
    m = re.search(
        rf"lloguer\s+de\s+comptadors?\s+({AMOUNT_PATTERN[1:-1]})\s*€",
        text, re.IGNORECASE,
    )
    if m:
        return normalize_number(m.group(1))

    # Factor Energia: "Lloguer d' Equip  N,NN €"
    m = re.search(
        rf"lloguer\s+d[''\s]*equip\s+({AMOUNT_PATTERN[1:-1]})\s*€",
        text, re.IGNORECASE,
    )
    if m:
        return normalize_number(m.group(1))

    return None


def extract_contracted_powers(
    text: str, words: list[tuple[Any, ...]] | None = None
) -> dict[str, float | None]:
    powers: dict[str, float | None] = {"P1": None, "P2": None, "P3": None}

    # Endesa: "Potencias contratadas: punta-llano N kW; valle N kW"
    endesa_match = re.search(
        rf"potencias?\s+contratadas?\s*:\s*"
        rf"punta[- ]llano\s+({POWER_PATTERN})\s*kw\s*;\s*"
        rf"valle\s+({POWER_PATTERN})\s*kw\b",
        text,
        re.IGNORECASE,
    )
    if endesa_match:
        p1p2 = normalize_number(endesa_match.group(1))
        p3 = normalize_number(endesa_match.group(2))
        return {"P1": p1p2, "P2": p1p2, "P3": p3}

    # Energía XXI: "Potencia contratada en punta-llano: N kW  Potencia contratada en valle: N kW"
    e21_match = re.search(
        rf"potencias?\s+contratadas?\s+en\s+punta[- ]llano\s*:\s*({POWER_PATTERN})\s*kw"
        rf".{{0,60}}potencias?\s+contratadas?\s+en\s+valle\s*:\s*({POWER_PATTERN})\s*kw\b",
        text,
        re.IGNORECASE,
    )
    if e21_match:
        p1p2 = normalize_number(e21_match.group(1))
        p3 = normalize_number(e21_match.group(2))
        return {"P1": p1p2, "P2": p1p2, "P3": p3}

    # Iberdrola: "Potencia punta: N kW" ... "Potencia valle: N,NN kW"
    ib_punta = re.search(rf"potencia\s+punta\s*:\s*({POWER_PATTERN})\s*kw\b", text, re.IGNORECASE)
    ib_valle = re.search(rf"potencia\s+valle\s*:\s*({POWER_PATTERN})\s*kw\b", text, re.IGNORECASE)
    if ib_punta and ib_valle:
        p1p2 = normalize_number(ib_punta.group(1))
        p3 = normalize_number(ib_valle.group(1))
        return {"P1": p1p2, "P2": p1p2, "P3": p3}

    # Naturgy: "Potencia contratada P1: N kW" + "Potencia contratada P2: N kW"
    naturgy_powers = re.findall(
        rf"potencia\s+contratada\s+(p[123])\s*:\s*({POWER_PATTERN})\s*kw\b",
        text,
        re.IGNORECASE,
    )
    if naturgy_powers:
        for label, value in naturgy_powers:
            powers[label.upper()] = normalize_number(value)
        if powers["P1"] is not None and powers["P3"] is None:
            powers["P3"] = powers["P1"]
        if powers["P2"] is None and powers["P1"] is not None:
            powers["P2"] = powers["P1"]
        if any(v is not None for v in powers.values()):
            return powers

    # Repsol (català/castellà): "Potència contractada  N,NkW  N,NkW"
    repsol_match = re.search(
        rf"pot[eè]ncia\s+contract(?:ada)\s+({POWER_PATTERN})\s*kw\s+({POWER_PATTERN})\s*kw\b",
        text,
        re.IGNORECASE,
    )
    if repsol_match:
        p1p2 = normalize_number(repsol_match.group(1))
        p3 = normalize_number(repsol_match.group(2))
        return {"P1": p1p2, "P2": p1p2, "P3": p3}

    # Repsol (layout): "Punta: N,NkW" i "Vall/Valle: N,NkW" en línies separades
    repsol_punta = re.search(rf"punta\s*:\s*({POWER_PATTERN})\s*kw\b", text, re.IGNORECASE)
    repsol_vall = re.search(rf"val(?:l|le)\s*:\s*({POWER_PATTERN})\s*kw\b", text, re.IGNORECASE)
    if repsol_punta and repsol_vall:
        p1p2 = normalize_number(repsol_punta.group(1))
        p3 = normalize_number(repsol_vall.group(1))
        return {"P1": p1p2, "P2": p1p2, "P3": p3}

    # Factor Energia: capçalera "P." + "Contractada" en tokens consecutius (prioritat sobre Holaluz)
    if words:
        for label in words:
            if label[5].casefold() not in {"p.", "p"}:
                continue
            pg, x0, y0, x1, y1 = label[:5]
            has_contractada = any(
                word[0] == pg and abs(word[2] - y0) < 4
                and word[1] > x1 and word[1] < x1 + 40
                and word[5].casefold().rstrip(":") == "contractada"
                for word in words
            )
            if not has_contractada:
                continue
            values = sorted(
                (
                    word for word in words
                    if word[0] == pg
                    and word[2] > y1
                    and word[2] < y1 + 80
                    and x0 - 5 <= word[1] <= x1 + 50
                    and re.fullmatch(rf"{POWER_PATTERN}", word[5])
                ),
                key=lambda word: word[2],
            )
            if len(values) >= 2:
                return {
                    "P1": normalize_number(values[0][5]),
                    "P2": normalize_number(values[1][5]),
                    "P3": normalize_number(values[1][5]),
                }

    # Holaluz: "P1: N,NN kW  P2: N,NN kW" o "P1 N,NN kW  P2 N,NN kW"
    holaluz_powers = re.findall(
        rf"\b(p[123])\s*:?\s*({POWER_PATTERN})\s*kw\b",
        text,
        re.IGNORECASE,
    )
    if holaluz_powers:
        for label, value in holaluz_powers:
            powers[label.upper()] = normalize_number(value)
        if any(v is not None for v in powers.values()):
            return powers

    return powers


def extract_from_text(text: str, words: list[tuple[Any, ...]] | None = None) -> dict[str, Any]:
    """Apply deterministic extraction rules to native PDF text."""
    result = empty_result()
    result["retailer"] = extract_retailer(text, words)

    result["cups"] = extract_cups(text, words)
    result["titular"] = extract_titular(text, words)
    billing_days, derived = extract_billing_days(text, words)
    result["billing_days"] = billing_days
    result["competitor_invoice_amount"] = extract_total_amount(text, words)
    result["energy_by_periods"] = extract_energy_by_periods(text, words)
    result["contracted_power_kw_by_periods"] = extract_contracted_powers(text, words)
    result["meter_rental_eur"] = extract_meter_rental(text)
    result["vat_amount"] = extract_vat_amount(text)
    result["vat_rate_percent"] = extract_vat_rate(text)
    result["igic_lines"], result["igic_total_eur"] = extract_igic(text)
    result["electricity_tax"] = extract_electricity_tax(text)
    result["electric_tax_rate_percent"] = extract_electricity_tax_rate(text)
    result["self_consumption_surplus_kwh"] = extract_surplus_kwh(text)

    for field in ("retailer", "cups", "titular", "billing_days", "competitor_invoice_amount"):
        if result[field] is None:
            add_issue(result, field, "missing_or_unverified", "No s'ha pogut extreure i validar el camp.")

    for period, value in result["energy_by_periods"].items():
        if value is None:
            add_issue(result, f"energy_by_periods.{period}", "missing_or_unverified", "No s'ha pogut extreure el consum en kWh.")

    # Contracted power is implemented progressively for each retailer.
    for period, value in result["contracted_power_kw_by_periods"].items():
        if value is None:
            add_issue(result, f"contracted_power_kw_by_periods.{period}", "missing_or_unverified", "No s'ha pogut extreure la potència contractada.")

    if result["meter_rental_eur"] is None:
        add_issue(result, "meter_rental_eur", "missing_or_unverified", "No s'ha pogut extreure el lloguer del comptador.")

    if result["vat_amount"] is None:
        add_issue(result, "vat_amount", "missing_or_unverified", "No s'ha pogut extreure l'import de l'IVA.")

    if result["vat_rate_percent"] is None:
        add_issue(result, "vat_rate_percent", "missing_or_unverified", "No s'ha pogut extreure el percentatge d'IVA.")

    if result["electricity_tax"] is None:
        add_issue(result, "electricity_tax", "missing_or_unverified", "No s'ha pogut extreure l'impost elèctric.")

    if result["electric_tax_rate_percent"] is None:
        add_issue(result, "electric_tax_rate_percent", "missing_or_unverified", "No s'ha pogut extreure el percentatge de l'impost elèctric.")

    if derived:
        add_issue(result, "billing_days", "derived_value", "Calculat a partir del període de facturació; cal confirmar la convenció de dies.")

    if not result["data_quality"]["issues"]:
        result["data_quality"]["status"] = "verified"
    return result


def extract_pdf_content(pdf_path: Path) -> tuple[str, list[tuple[Any, ...]]]:
    if fitz is None:
        raise RuntimeError("PyMuPDF no està instal·lat. Instal·la les dependències del projecte.")
    with fitz.open(pdf_path) as document:
        text_pages = []
        words = []
        for page_number, page in enumerate(document):
            text_pages.append(page.get_text("text", sort=True))
            words.extend((page_number, *word) for word in page.get_text("words", sort=True))
        text = "\n".join(text_pages)
    if not text.strip():
        raise ValueError("El PDF no conté text digital usable.")
    return text, words


def extract_pdf_text(pdf_path: Path) -> str:
    """Return native text for callers that do not need layout coordinates."""
    return extract_pdf_content(pdf_path)[0]


def extract_pdf(pdf_path: Path) -> dict[str, Any]:
    text, words = extract_pdf_content(pdf_path)
    return extract_from_text(text, words)


def extract_directory(directory: Path) -> list[dict[str, Any]]:
    """Extract every PDF contained in a directory and its subdirectories, in relative path order."""
    results = []
    pdf_paths = sorted(
        (path for path in directory.rglob("*") if path.suffix.casefold() == ".pdf"),
        key=lambda path: str(path.relative_to(directory)).casefold(),
    )
    for pdf_path in pdf_paths:
        try:
            result = extract_pdf(pdf_path)
        except (RuntimeError, ValueError, OSError):
            result = empty_result()
            result["data_quality"]["status"] = "rejected"
            add_issue(
                result,
                "document",
                "processing_error",
                "No s'ha pogut processar el PDF localment.",
            )
        result["source_file"] = str(pdf_path.relative_to(directory))
        results.append(result)
    return results


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_path", type=Path, help="Ruta a una factura PDF digital o a un directori de PDFs")
    parser.add_argument("--pretty", action="store_true", help="Formata el JSON amb indentació")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.input_path.exists():
        print("Cal indicar una ruta existent a un PDF o directori.", file=sys.stderr)
        return 2

    if args.input_path.is_dir():
        result: dict[str, Any] | list[dict[str, Any]] = extract_directory(args.input_path)
    elif args.input_path.suffix.lower() == ".pdf":
        try:
            result = extract_pdf(args.input_path)
        except (RuntimeError, ValueError, OSError) as error:
            print(f"No s'ha pogut processar el PDF: {error}", file=sys.stderr)
            return 1
    else:
        print("Cal indicar una ruta a un fitxer PDF o a un directori.", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
