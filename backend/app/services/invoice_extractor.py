#!/usr/bin/env python3
"""Extract a minimal, auditable electricity-invoice contract from a digital PDF."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

if __package__:
    from .cups import is_valid_cups, normalize_cups
    from .invoice_costs import extract_component_costs
else:  # Support the standalone PDF extraction CLI.
    from cups import is_valid_cups, normalize_cups
    from invoice_costs import extract_component_costs

try:
    import fitz
except ImportError:  # pragma: no cover - exercised by the CLI environment
    fitz = None


CUPS_PATTERN = re.compile(
    r"(?<![A-Z0-9])ES(?:[\s-]*[0-9]){16}[\s-]*[A-Z]{2}"
    r"(?:[\s-]*[0-9][\s-]*[A-Z])?(?![A-Z0-9])", re.IGNORECASE,
)
NUMBER_PATTERN = r"\d{1,3}(?:\.\d{3})*,\d{2,3}|\d+(?:[.,]\d{2,3})?"
ENERGY_NUMBER_PATTERN = r"\d{1,3}(?:\.\d{3})*,\d{1,3}|\d+(?:[.,]\d{1,3})?"
POWER_PATTERN = r"\d{1,3}(?:\.\d{3})*,\d+|\d+(?:[.,]\d+)?"
AMOUNT_PATTERN = rf"({NUMBER_PATTERN})"
DATE_PATTERN = r"(\d{2}/\d{2}/\d{4})"
NAMED_ENERGY_PERIODS = {"punta": "P1", "pla": "P2", "llano": "P2", "vall": "P3", "valle": "P3"}
NAMED_ENERGY_PERIOD_PATTERN = r"punta|pla|llano|vall|valle"
ENDESA_ELECTRICITY_TAX_LABEL = r"(?:impuesto\s+electricidad|impost\s+electricitat)"
ENDESA_METER_RENTAL_LABEL = r"(?:alquiler\s+del\s+contador|lloguer\s+del\s+comptador)"
EQUIPMENT_RENTAL_LABEL = r"alquiler\s+(?:de\s+)?equipos?(?:\s+(?:de\s+)?medida(?:\s+y\s+control)?)?"
SURPLUS_LABEL_PATTERN = (
    r"(?:compensaci[oó](?:n)?\s+(?:(?:de|d['’])\s*)?excedent(?:e)?s?"
    r"|valoraci[oó]n\s+excedentes?"
    r"|excedentes?\s+de\s+(?:autoconsumo|energ[ií]a\s+generada))\b"
)
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
    r"(\d{1,2})\s+d(?:e\s+|['’]\s*)([a-zà-ÿ]+)\s+(\d{4})\s*[-–]\s*"
    r"(\d{1,2})\s+d(?:e\s+|['’]\s*)([a-zà-ÿ]+)\s+(\d{4})",
    re.IGNORECASE,
)
SPANISH_BILLING_PERIOD_PATTERN = re.compile(
    r"de\s+los\s+d[ií]as\s+"
    r"(\d{1,2})\s+de\s+([a-zá-ÿ]+)\s+(\d{4})\s*[-–]\s*"
    r"(\d{1,2})\s+de\s+([a-zá-ÿ]+)\s+(\d{4})",
    re.IGNORECASE,
)
RETAILERS = {
    "octopus": "Octopus Energy",
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
    "plenitude": "Plenitude",
    "pepeenergy": "Pepeenergy",
    "pepephone": "Pepeenergy",
    "bon preu": "Bonpreu Esclat Energia",
    "bonpreu esclat": "Bonpreu Esclat Energia",
    "bonpreuesclat": "Bonpreu Esclat Energia",
}
TITULAR_VALUE_EXCLUSIONS = {"POTENCIA"}


def empty_result() -> dict[str, Any]:
    return {
        "retailer": None,
        "cups": None,
        "titular": None,
        "billing_days": None,
        "competitor_invoice_amount": None,
        "competitor_energy_eur": None,
        "competitor_power_eur": None,
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
    def candidates(fragment: str) -> set[str]:
        return {
            normalize_cups(match.group(0)) for match in CUPS_PATTERN.finditer(fragment)
            if is_valid_cups(match.group(0))
        }

    def unique(values: set[str]) -> str | None:
        return next(iter(values)) if len(values) == 1 else None

    # Reconstruct the whole value row before considering the line below it.
    # A fragmented CUPS must not lose precedence to the nearby bank details.
    if words:
        labels = [word for word in words if re.search(r"\bCUPS\b", word[5], re.IGNORECASE)]
        values = set()
        for label in labels:
            row = " ".join(
                word[5] for word in sorted(words, key=lambda word: word[1])
                if word[0] == label[0] and abs(word[2] - label[2]) < 4
                and word[1] >= label[1]
            )
            values.update(candidates(row))
        if values:
            return unique(values)

        for label in labels:
            below = [
                word for word in words
                if word[0] == label[0] and label[4] < word[2] < label[4] + 25
                and label[1] - 2 <= word[1] < label[1] + 180
            ]
            if below:
                first_y = min(word[2] for word in below)
                values.update(candidates(" ".join(
                    word[5] for word in sorted(below, key=lambda word: word[1])
                    if abs(word[2] - first_y) < 3
                )))
        if values:
            return unique(values)

    # Text fallback is confined to the label's row and its immediate value row.
    labeled_values = set()
    labels_found = False
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if label := re.search(r"\bCUPS\b", line, re.IGNORECASE):
            labels_found = True
            labeled_values.update(candidates(line[label.end():]))
            following = next((row for row in lines[index + 1:] if row.strip()), "")
            if following.lstrip().upper().startswith("ES"):
                labeled_values.update(candidates(following))
    if labels_found or (words and labels):
        return unique(labeled_values)
    return unique(candidates(text))


def extract_titular(text: str, words: list[tuple[Any, ...]] | None = None) -> str | None:
    # Holaluz's supply-holder block also supports names wrapped over several lines.
    holder_text = text
    if words:
        for label in words:
            if label[5].casefold() != "titular":
                continue
            line = " ".join(
                word[5] for word in sorted(words, key=lambda word: word[1])
                if word[0] == label[0] and abs(word[2] - label[2]) < 3
                and label[1] <= word[1] < label[1] + 180
            )
            if not re.match(r"titular del (?:subministrament|suministro)\s*:", line, re.IGNORECASE):
                continue
            holder_text = "\n".join(
                word[5] for word in sorted(words, key=lambda word: (word[2], word[1]))
                if word[0] == label[0] and label[1] - 2 <= word[1] < label[1] + 180
                and label[2] <= word[2] < label[2] + 85
            )
            break
    supply_holder = re.search(
        r"titular\s+del\s+(?:subministrament|suministro)\s*:\s*(.{2,160}?)\s*(?=\bNIF\s*:)",
        holder_text, re.IGNORECASE | re.DOTALL,
    )
    if supply_holder:
        value = re.sub(r"\s+", " ", supply_holder.group(1)).strip()
        if is_titular_value(value):
            return value

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
        r"(?:^|\n)\s*titular\s+del\s+(?:contrato|contracte)\s*:\s*(.+?)(?=\s+(?:nif|direcci[oó]n|cups)\s*:|\s{2,}|\n|$)",
        text,
        re.IGNORECASE,
    )
    if contract_holder:
        value = re.sub(r"\s+", " ", contract_holder.group(1)).strip()
        if is_titular_value(value):
            return value

    # Pepeenergy puts the name below "Datos cliente", beside the billing column.
    if words:
        for label in words:
            if label[5].casefold() != "datos":
                continue
            if not any(
                word[0] == label[0] and abs(word[2] - label[2]) < 3
                and label[3] < word[1] < label[3] + 50
                and word[5].casefold().rstrip(":") == "cliente"
                for word in words
            ):
                continue
            below = [
                word for word in words
                if word[0] == label[0] and label[4] < word[2] < label[4] + 30
                and label[1] - 2 <= word[1] < label[1] + 240
            ]
            if below:
                first_y = min(word[2] for word in below)
                value = " ".join(
                    word[5] for word in sorted(below, key=lambda word: word[1])
                    if abs(word[2] - first_y) < 3
                )
                if is_titular_value(value) and not re.match(r"(?:NIF|NIE|CIF)\b", value, re.IGNORECASE):
                    return value

    customer = re.search(r"\bdatos[ \t]+cliente[ \t]*:?[^\n]*\n[ \t]*([^\n]+)", text, re.IGNORECASE)
    if customer:
        value = re.split(r"\s{2,}", customer.group(1).strip())[0]
        if is_titular_value(value) and not re.match(r"(?:NIF|NIE|CIF)\b", value, re.IGNORECASE):
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
    explicit_period = re.search(
        r"\bper[ií]od[oe](?:\s+de\s+facturaci[oó](?:n)?)?\s*:\s*"
        r"[^\n()]{0,100}?\(\s*(\d{1,3})\s+(?:dies|d[ií]as)\s*\)",
        text,
        re.IGNORECASE,
    )
    if explicit_period:
        return int(explicit_period.group(1)), False

    # Plenitude and Pepeenergy state days in the meter-rental formula, in either order.
    rental_days = set()
    for row in re.findall(
        rf"(?:{EQUIPMENT_RENTAL_LABEL}|alquiler\s+(?:(?:del?|de\s+los)\s+)?contador)\b[^\n]*",
        text, re.IGNORECASE,
    ):
        if not re.search(rf"(?:{NUMBER_PATTERN})\s*(?:€|eur)\s*$", row, re.IGNORECASE):
            continue
        days_first = re.search(r"\b(\d{1,3})\s+d[ií]as\s*[x×*]", row, re.IGNORECASE)
        rate_first = re.search(
            r"(?:€|eur)\s*/\s*d[ií]a\s*[x×*]\s*(\d{1,3})(?![\d.,])", row, re.IGNORECASE,
        )
        if match := days_first or rate_first:
            rental_days.add(int(match.group(1)))
    if len(rental_days) == 1 and (days := next(iter(rental_days))) > 0:
        return days, False

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

    holaluz_total = re.search(
        rf"^\s*total(?:\s+tarifa\s+justa)?\s+{AMOUNT_PATTERN}\s*(?:€|eur\b)",
        text, re.IGNORECASE | re.MULTILINE,
    )
    if holaluz_total:
        return normalize_number(holaluz_total.group(1))

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


def _extract_consumption_table(words: list[tuple[Any, ...]]) -> dict[str, float | None] | None:
    """Read labeled period rows within the consumption column, not adjacent readings."""
    if (table := _extract_endesa_consumption_table(words)) is not None:
        return table
    for label in words:
        if not re.fullmatch(r"consum(?:o)?", label[5], re.IGNORECASE):
            continue
        header = sorted(
            (word for word in words if word[0] == label[0] and abs(word[2] - label[2]) < 3),
            key=lambda word: word[1],
        )
        unit = next((word for word in header if word[1] > label[3]
                     and re.fullmatch(r"\(kwh\)", word[5], re.IGNORECASE)), None)
        if unit is None:
            continue
        previous = max((word[3] for word in header if word[3] < label[1]), default=label[1])
        following = min((word[1] for word in header if word[1] > unit[3]), default=unit[3])
        left, right = (previous + label[1]) / 2, (unit[3] + following) / 2
        bottom = min(
            (word[2] for word in words if word[0] == label[0] and word[2] > label[4]
             and word[1] < left and word[5].casefold() == "total"),
            default=float("inf"),
        )
        periods = {}
        rows = sorted(
            (word for word in words if word[0] == label[0] and label[4] < word[2] < bottom
             and word[1] < left and re.fullmatch(r"per[ií]od[oe]", word[5], re.IGNORECASE)),
            key=lambda word: word[2],
        )
        for row in rows:
            row_words = sorted(
                (word for word in words if word[0] == row[0] and abs(word[2] - row[2]) < 3),
                key=lambda word: word[1],
            )
            period = next((word[5] for word in row_words
                           if row[3] < word[1] < left and word[5] in {"1", "2", "3"}), None)
            if period is None:
                continue
            values = [word for word in row_words if left <= (word[1] + word[3]) / 2 <= right
                      and re.fullmatch(NUMBER_PATTERN, word[5])]
            key = f"P{period}"
            if key in periods:
                break  # Do not mix another table into the same set of periods.
            periods[key] = normalize_number(values[0][5]) if len(values) == 1 else None
            if len(periods) == 3:
                break
        if periods:
            return {period: periods.get(period) for period in ("P1", "P2", "P3")}
    return None


def _extract_endesa_consumption_table(words: list[tuple[Any, ...]]) -> dict[str, float | None] | None:
    """Identify the readings table by its headers and read only its consumption cells."""
    for label in words:
        if not re.fullmatch(r"consum(?:o)?", label[5], re.IGNORECASE):
            continue
        page_words = [word for word in words if word[0] == label[0]]
        header = [word for word in page_words if abs(word[2] - label[2]) < 3]
        adjustment = next((word for word in header if word[3] < label[1]
                           and re.fullmatch(r"ajuste?", word[5], re.IGNORECASE)), None)
        multiplier = next((word for word in header if re.fullmatch(
            r"multipl\.", word[5], re.IGNORECASE,
        )), None)
        period_header = next((word for word in header if re.fullmatch(
            r"per[ií]od[oe]", word[5], re.IGNORECASE,
        )), None)
        if adjustment is None or multiplier is None or period_header is None:
            continue
        if not period_header[3] < multiplier[1] < adjustment[1]:
            continue
        left = (adjustment[3] + label[1]) / 2
        right = label[3] + 3
        # The kWh unit sits on a separate row headed Energia/Energía.
        energy_header = next((word for word in sorted(page_words, key=lambda word: word[2])
                              if word[2] > label[4] and abs(word[1] - period_header[1]) < 3
                              and re.fullmatch(r"energ[ií]a", word[5], re.IGNORECASE)
                              and any(abs(unit[2] - word[2]) < 3 and left <= unit[1] < right
                                      and unit[5].casefold() == "kwh" for unit in page_words)), None)
        if energy_header is None:
            continue
        row_labels = sorted(
            (word for word in page_words if word[2] > energy_header[4]
             and abs(word[1] - period_header[1]) < 3), key=lambda word: word[2],
        )
        periods = {}
        for row in row_labels:
            period = NAMED_ENERGY_PERIODS.get(row[5].casefold())
            if period is None or period in periods:
                break  # A new section or another table must not fill missing cells.
            values = [word for word in page_words if abs(word[2] - row[2]) < 3
                      and left <= (word[1] + word[3]) / 2 <= right
                      and re.fullmatch(NUMBER_PATTERN, word[5])]
            periods[period] = normalize_number(values[0][5]) if len(values) == 1 else None
            if len(periods) == 3:
                break
        if periods:
            return {period: periods.get(period) for period in ("P1", "P2", "P3")}
    return None


def extract_energy_by_periods(
    text: str, words: list[tuple[Any, ...]] | None = None
) -> dict[str, float | None]:
    periods: dict[str, float | None] = {"P1": None, "P2": None, "P3": None}
    # Holaluz Tarifa Justa puts consumption in the extra-information summary.
    summary = re.search(
        r"resumen\s+de\s+tu\s+consumo\s+estimado\b(?P<details>.{0,500})",
        text, re.IGNORECASE | re.DOTALL,
    )
    if summary:
        for label, value in re.findall(
            rf"consumo\s+en\s+(punta|llano|valle)\s*:\s*({NUMBER_PATTERN})\s*kwh",
            summary.group("details"), re.IGNORECASE,
        ):
            periods[{"punta": "P1", "llano": "P2", "valle": "P3"}[label.casefold()]] = normalize_number(value)
        return periods

    # Holaluz Classic: each row has previous reading, current reading, consumption.
    if extract_retailer(text, words) == "Holaluz" and re.search(
        r"les\s+teves\s+lectures|tus\s+lecturas", text, re.IGNORECASE,
    ):
        if words:
            for label in words:
                if not re.fullmatch(r"P[123]", label[5], re.IGNORECASE):
                    continue
                row = " ".join(
                    word[5] for word in sorted(words, key=lambda word: word[1])
                    if word[0] == label[0] and abs(word[2] - label[2]) < 3
                    and word[1] > label[3]
                )
                values = re.findall(rf"({NUMBER_PATTERN})\s*kwh", row, re.IGNORECASE)
                if len(values) == 3:
                    periods[label[5].upper()] = normalize_number(values[-1])
            if any(value is not None for value in periods.values()):
                return periods
        for period, _, _, consumption in re.findall(
            rf"\b(P[123])\s+({NUMBER_PATTERN})\s*kwh\s+({NUMBER_PATTERN})\s*kwh\s+({NUMBER_PATTERN})\s*kwh",
            text, re.IGNORECASE,
        ):
            periods[period.upper()] = normalize_number(consumption)
        return periods

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

    if words and (table := _extract_consumption_table(words)) is not None:
        return table

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

    iberdrola_consumptions = re.search(
        r"sus\s+consumos\s+desagregados\s+han\s+sido\s+"
        rf"punta\s*:\s*({ENERGY_NUMBER_PATTERN})\s*kwh\s*;\s*"
        rf"llano\s*:\s*({ENERGY_NUMBER_PATTERN})\s*kwh\s*;\s*"
        rf"valle\s*:?\s*({ENERGY_NUMBER_PATTERN})\s*kwh\b",
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

    endesa_consumptions = re.findall(
        rf"\bconsum(?:o)?\s+({NAMED_ENERGY_PERIOD_PATTERN})\s+({NUMBER_PATTERN})\s*kwh\b",
        text,
        re.IGNORECASE,
    )
    for label, value in endesa_consumptions:
        periods[NAMED_ENERGY_PERIODS[label.casefold()]] = normalize_number(value)
    if all(value is not None for value in periods.values()):
        return periods

    for line in text.splitlines():
        period_match = re.match(rf"\s*({NAMED_ENERGY_PERIOD_PATTERN})\b", line, re.IGNORECASE)
        if not period_match:
            continue
        # A period name also labels billed power; its prices are not kWh.
        if re.search(r"\bkw\b|€|\beur(?:os?)?\b", line, re.IGNORECASE):
            continue
        values = re.findall(rf"-?{NUMBER_PATTERN}", line)
        if len(values) >= 5:
            periods[NAMED_ENERGY_PERIODS[period_match.group(1).casefold()]] = normalize_number(
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
        for label in words:
            period = NAMED_ENERGY_PERIODS.get(label[5].lower().rstrip(":"))
            if period is None:
                continue
            row = [
                word for word in words
                if word[0] == label[0] and abs(word[2] - label[2]) < 4
            ]
            if re.search(
                r"\bkw\b|€|\beur(?:os?)?\b",
                " ".join(word[5] for word in row), re.IGNORECASE,
            ):
                continue
            readings = sorted(
                (
                    word
                    for word in row
                    if re.fullmatch(rf"-?{NUMBER_PATTERN}", word[5])
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
    kwh_pat = r"-?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:[.,]\d+)?"
    # Pepeenergy bills each period inside a dedicated block; readings elsewhere
    # are cumulative and must not be substituted for incomplete billed quantities.
    block = re.search(
        r"excedentes\s+de\s+energ[ií]a\s+generada\b(?P<details>.*?)"
        r"(?=\b(?:cuota\s+pepeenergy|otros\s+costes|impuesto|iva|total|generaci[oó]n|historial)\b|\Z)",
        text, re.IGNORECASE | re.DOTALL,
    )
    if block:
        rows = re.findall(
            rf"\bper[ií]odo\s+(P[123])\s*\([^\n)]+\)[^\n]*?"
            rf"(?:€|eur)\s*/\s*kwh\s*[×x*]\s*({kwh_pat})\s*kwh\b",
            block.group("details"), re.IGNORECASE,
        )
        if len(rows) == 3 and {period.upper() for period, _ in rows} == {"P1", "P2", "P3"}:
            return float(sum(abs(Decimal(str(normalize_number(value)))) for _, value in rows))
        return None

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
    # Holaluz prints taxable base, rate and tax amount, in that order.
    tax_row = re.search(
        rf"(?:impost\s+el[eè]ctric|impuesto\s+el[eé]ctrico)\s+{AMOUNT_PATTERN}\s*€\s+\d+(?:[.,]\d+)?\s*%\s+{AMOUNT_PATTERN}\s*€",
        text, re.IGNORECASE,
    )
    if tax_row:
        return normalize_number(tax_row.group(2))

    # Endesa / Energía XXI: "Impuesto electricidad[:]  ( NNN Eur X N% ) ....N,NN €"
    # Primera ocurrència positiva (evita ajustos negatius)
    for m in re.finditer(
        rf"{ENDESA_ELECTRICITY_TAX_LABEL}\s*:?\s*\([^)]+\)\s*\.{{2,}}\s*(-?{AMOUNT_PATTERN[1:-1]})\s*€",
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
    # A table row can share a text line with the PDF's left-hand column.
    m = re.search(
        rf"\biva[ \t]+{AMOUNT_PATTERN}[ \t]*€[ \t]+"
        rf"(?P<rate>\d{{1,3}}(?:[.,]\d+)?)[ \t]*%[ \t]+{AMOUNT_PATTERN}[ \t]*€",
        text, re.IGNORECASE,
    )
    if m:
        return normalize_number(m.group("rate"))

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
        rf"{ENDESA_ELECTRICITY_TAX_LABEL}\s*:?\s*\([^)]*?(\d{{1,3}}(?:[.,]\d+)?)\s*%",
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
    equipment = re.search(
        rf"{EQUIPMENT_RENTAL_LABEL}\s*:?\s*(?:\([^\n)]+\)\s*)?"
        rf"({NUMBER_PATTERN})\s*(?:€|eur\b)(?!\s*/)",
        text, re.IGNORECASE,
    )
    if equipment:
        return normalize_number(equipment.group(1))

    # Endesa / Energía XXI can split rental into several billed segments.
    # Only formula rows qualify: a summary must not be added to its own detail.
    rental_segments = re.findall(
        rf"{ENDESA_METER_RENTAL_LABEL}\s*:?\s*\([^)]+\)\s*\.+\s*({NUMBER_PATTERN})\s*€",
        text, re.IGNORECASE,
    )
    if rental_segments:
        return float(sum(
            (Decimal(value.replace(".", "").replace(",", ".")) if "," in value else Decimal(value)
             for value in rental_segments), Decimal("0"),
        ))

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
    is_20td = extract_access_tariff(text, words) == "2.0TD"

    def named_powers(punta: str, valle: str) -> dict[str, float | None]:
        peak, valley = normalize_number(punta), normalize_number(valle)
        if is_20td:
            return {"P1": peak, "P2": valley, "P3": None}
        # Keep the existing mapping outside an identified 2.0TD tariff.
        return {"P1": peak, "P2": peak, "P3": valley}

    contracted = re.search(
        rf"pot[eè]ncia\s+contractada\s*:\s*P1\s*:?\s*({POWER_PATTERN})\s*kw\s+P2\s*:?\s*({POWER_PATTERN})\s*kw",
        text, re.IGNORECASE,
    )
    if contracted:
        return {"P1": normalize_number(contracted.group(1)), "P2": normalize_number(contracted.group(2)), "P3": None}

    # Pepeenergy explicitly names the two 2.0TD contracted-power periods.
    labeled_powers = re.findall(
        rf"potencia\s+contratada\s+en\s+(P[12])\s*(?:\([^\n)]+\)\s*)?:\s*({POWER_PATTERN})\s*kw\b",
        text, re.IGNORECASE,
    )
    if labeled_powers:
        powers.update({period.upper(): normalize_number(value) for period, value in labeled_powers})
        return powers

    # Endesa: "Potencias contratadas: punta-llano N kW; valle N kW"
    endesa_match = re.search(
        rf"pot[eè]nci[ae]s?\s+(?:contratadas?|contractad[ae]s?)\s*:\s*"
        rf"punta[- ](?:llano|pla)\s+({POWER_PATTERN})\s*kw\s*;\s*"
        rf"(?:valle|vall)\s+({POWER_PATTERN})\s*kw\b",
        text,
        re.IGNORECASE,
    )
    if endesa_match:
        return named_powers(endesa_match.group(1), endesa_match.group(2))

    # Energía XXI: "Potencia contratada en punta-llano: N kW  Potencia contratada en valle: N kW"
    e21_match = re.search(
        rf"potencias?\s+contratadas?\s+en\s+punta[- ]llano\s*:\s*({POWER_PATTERN})\s*kw"
        rf".{{0,60}}potencias?\s+contratadas?\s+en\s+valle\s*:\s*({POWER_PATTERN})\s*kw\b",
        text,
        re.IGNORECASE,
    )
    if e21_match:
        return named_powers(e21_match.group(1), e21_match.group(2))

    # Iberdrola: "Potencia punta: N kW" ... "Potencia valle: N,NN kW"
    ib_punta = re.search(rf"potencia\s+punta\s*:\s*({POWER_PATTERN})\s*kw\b", text, re.IGNORECASE)
    ib_valle = re.search(rf"potencia\s+valle\s*:\s*({POWER_PATTERN})\s*kw\b", text, re.IGNORECASE)
    if ib_punta and ib_valle:
        return {
            "P1": normalize_number(ib_punta.group(1)),
            "P2": normalize_number(ib_valle.group(1)),
            "P3": None,
        }

    # Naturgy: "Potencia contratada P1: N kW" + "Potencia contratada P2: N kW"
    naturgy_powers = re.findall(
        rf"potencia\s+contratada\s+(p[123])\s*:\s*({POWER_PATTERN})\s*kw\b",
        text,
        re.IGNORECASE,
    )
    if naturgy_powers:
        for label, value in naturgy_powers:
            powers[label.upper()] = normalize_number(value)
        if is_20td:
            return {"P1": powers["P1"], "P2": powers["P2"], "P3": None}
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
        return named_powers(repsol_match.group(1), repsol_match.group(2))

    # Repsol (layout): "Punta: N,NkW" i "Vall/Valle: N,NkW" en línies separades
    repsol_punta = re.search(rf"punta\s*:\s*({POWER_PATTERN})\s*kw\b", text, re.IGNORECASE)
    repsol_vall = re.search(rf"val(?:l|le)\s*:\s*({POWER_PATTERN})\s*kw\b", text, re.IGNORECASE)
    if repsol_punta and repsol_vall:
        return named_powers(repsol_punta.group(1), repsol_vall.group(1))

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
                    "P3": None if is_20td else normalize_number(values[1][5]),
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
        if is_20td:
            powers["P3"] = None
        if any(v is not None for v in powers.values()):
            return powers

    return powers


def extract_access_tariff(text: str, words: list[tuple[Any, ...]] | None = None) -> str | None:
    tariff_pattern = re.compile(r"\b(?:2\.?0|3\.0|6\.[1-4])TD\b", re.IGNORECASE)
    if words:
        for label in words:
            if label[5].casefold() != "tarifa":
                continue
            label_line = " ".join(
                word[5] for word in sorted(words, key=lambda word: word[1])
                if word[0] == label[0] and abs(word[2] - label[2]) < 3
                and label[1] <= word[1] < label[1] + 180
            )
            if not re.search(r"\b(?:acc[eéè]s|acceso)\b", label_line, re.IGNORECASE):
                continue
            # Use the label's column: sorted PDF text can join the tariff to a meter number.
            candidates = sorted(
                (word for word in words
                 if word[0] == label[0] and label[2] - 3 <= word[2] < label[4] + 30
                 and label[1] - 2 <= word[1] < label[1] + 180),
                key=lambda word: (word[2], word[1]),
            )
            for word in candidates:
                if tariff_pattern.fullmatch(word[5]):
                    return word[5].upper().replace("20TD", "2.0TD")
    match = tariff_pattern.search(text)
    return match.group(0).upper().replace("20TD", "2.0TD") if match else None


def _extract_octopus_fields(text: str, result: dict[str, Any]) -> None:
    """Read Octopus's billed rows without confusing their regulatory breakdowns."""
    def unique_amount(label: str) -> float | None:
        amounts = {
            normalize_number(match.group(1))
            for match in re.finditer(
                rf"^\s*{label}\s*:?\s*({NUMBER_PATTERN})\s*(?:€|EUR)\s*$",
                text, re.IGNORECASE | re.MULTILINE,
            )
        }
        return next(iter(amounts)) if len(amounts) == 1 else None

    holder = re.search(r"^\s*Cliente:[ \t]*([^\n]+)", text, re.IGNORECASE | re.MULTILINE)
    if holder:
        value = re.split(r"\s{2,}|\s+CUPS\s*:", holder.group(1), maxsplit=1)[0].strip()
        if is_titular_value(value):
            result["titular"] = value

    # Each main row is followed by tolls, charges and margin: read only named rows.
    energy = {"P1": None, "P2": None, "P3": None}
    for name, period in (("Punta", "P1"), ("Llano", "P2"), ("Valle", "P3")):
        values = {
            normalize_number(match.group(1)) for match in re.finditer(
                rf"^\s*{name}\s+({NUMBER_PATTERN})\s+kWh\s+"
                rf"(?:{POWER_PATTERN})\s*(?:€|EUR)/\s*kWh\s+(?:{NUMBER_PATTERN})\s*(?:€|EUR)\s*$",
                text, re.IGNORECASE | re.MULTILINE,
            )
        }
        if len(values) == 1:
            energy[period] = next(iter(values))
    result["energy_by_periods"] = energy

    # 2.0TD has two power periods, even though the meter table prints six columns.
    powers = {"P1": None, "P2": None, "P3": None}
    contracted = re.search(
        rf"\bPotencia\s+Contratada\s*\(kW\)\s+({POWER_PATTERN})\s+({POWER_PATTERN})\b",
        text, re.IGNORECASE,
    )
    if contracted and extract_access_tariff(text) == "2.0TD":
        powers.update(P1=normalize_number(contracted.group(1)), P2=normalize_number(contracted.group(2)))
    result["contracted_power_kw_by_periods"] = powers

    billed_days = {int(value) for value in re.findall(
        rf"^\s*(?:Punta|Valle)\s+(?:{POWER_PATTERN})\s+kW\s*\*\s*(\d{{1,3}})\s+días\b",
        text, re.IGNORECASE | re.MULTILINE,
    )}
    rental_rows = list(re.finditer(
        rf"^\s*Alquiler\s+de\s+Equipos\s+(\d{{1,3}})\s+días\s+"
        rf"(?:{POWER_PATTERN})\s*(?:€|EUR)/días?\s+({NUMBER_PATTERN})\s*(?:€|EUR)\s*$",
        text, re.IGNORECASE | re.MULTILINE,
    ))
    billed_days.update(int(row.group(1)) for row in rental_rows)
    if billed_days:
        days = next(iter(billed_days)) if len(billed_days) == 1 and min(billed_days) > 0 else None
        if days != result["billing_days"]:
            add_issue(result, "billing_days", "billing_days_mismatch",
                      "Els dies del detall facturat no coincideixen amb la capçalera. Es prioritza el detall si és coherent; cal revisar-los.")
        result["billing_days"] = days
    rental_amounts = {normalize_number(row.group(2)) for row in rental_rows}
    if rental_rows:
        result["meter_rental_eur"] = next(iter(rental_amounts)) if len(rental_amounts) == 1 else None

    result["competitor_energy_eur"] = unique_amount(r"Energía\s+Activa")
    result["competitor_power_eur"] = unique_amount(r"Potencia")
    # Credit is a payment balance, not a reduction of this invoice's supply cost.
    result["competitor_invoice_amount"] = unique_amount(r"Total\s+factura")
    if re.search(r"Crédito\s+usado\s*:?\s*-\s*[\d.,]+\s*(?:€|EUR)", text, re.IGNORECASE):
        add_issue(result, "competitor_invoice_amount", "credit_excluded",
                  "S'utilitza el total de la factura abans d'aplicar el crèdit acumulat, no el total a pagar.")

    tax = re.search(
        rf"^\s*Impuesto\s+Eléctrico\s*\(REDUCIDO\)\s+(?:{NUMBER_PATTERN})\s+kWh\s+"
        rf"(?:{POWER_PATTERN})\s*(?:€|EUR)/kWh\s+({NUMBER_PATTERN})\s*(?:€|EUR)\s*$",
        text, re.IGNORECASE | re.MULTILINE,
    )
    if tax:
        result["electricity_tax"] = normalize_number(tax.group(1))
        add_issue(result, "electric_tax_rate_percent", "minimum_electricity_tax",
                  "La factura aplica un mínim d'impost elèctric per kWh. El percentatge anunciat, per si sol, no reprodueix l'import facturat; cal revisar la simulació.")
    rate = re.search(
        r"tipo\s+impositivo\s+del\s+IEE\s+queda\s+reducido\s+al\s+(\d+(?:[.,]\d+)?)\s*%",
        text, re.IGNORECASE,
    )
    if rate:
        result["electric_tax_rate_percent"] = normalize_number(rate.group(1))


def _extract_bonpreu_fields(
    text: str, words: list[tuple[Any, ...]] | None, result: dict[str, Any],
) -> None:
    """Use billed sections, excluding rounded readings and the allocation chart."""
    def unique(field: str, values: set) -> Any:
        if len(values) > 1:
            add_issue(result, field, "conflicting_values", "La factura conté valors contradictoris per a aquest camp. Cal revisar-lo.")
        return next(iter(values)) if len(values) == 1 else None

    def amount(field: str, label: str) -> float | None:
        label = label.replace(" ", r"\s+")
        return unique(field, {
            normalize_number(match[1]) for match in re.finditer(
                rf"{label}\s*:?[ \t]*({NUMBER_PATTERN})\s*(?:€|EUR\b)(?!\s*/)",
                text, re.IGNORECASE,
            )
        })

    # The CUPS label ends a long sentence. Its value aligns with the sentence's
    # start, not with the word '(CUPS)'. This also identifies the column boundary.
    holder_rows, cups_rows = [], []
    if words:
        column_boundaries = {}
        for label in words:
            if not re.fullmatch(r"\(CUPS\):?", label[5], re.IGNORECASE):
                continue
            row = sorted((word for word in words if word[0] == label[0]
                          and abs(word[2] - label[2]) < 3), key=lambda word: word[1])
            starts = [index for index, word in enumerate(row) if word[5].casefold() == "número"
                      and re.match(r"número que identifica", " ".join(item[5] for item in row[index:]), re.IGNORECASE)]
            if len(starts) != 1:
                continue
            left = row[starts[0]][1]
            column_boundaries[label[0]] = left
            below = [word for word in words if word[0] == label[0]
                     and label[4] < word[2] < label[4] + 25 and word[1] >= left - 2]
            if below:
                top = min(word[2] for word in below)
                cups_rows.append(" ".join(word[5] for word in sorted(below, key=lambda word: word[1])
                                          if abs(word[2] - top) < 3))
        for holder in words:
            if holder[5].casefold() != "titular:":
                continue
            row = sorted((word for word in words if word[0] == holder[0]
                          and abs(word[2] - holder[2]) < 3), key=lambda word: word[1])
            left = min((word[1] for word in row if word[5].casefold() == "tarifa"
                        and word[1] > holder[3]), default=column_boundaries.get(holder[0]))
            if left is not None:
                holder_rows.append(" ".join(word[5] for word in row if holder[3] < word[1] < left - 2))
    else:
        holder_rows = [re.split(r"\s{2,}|\s+Tarifa\b", match[1], maxsplit=1, flags=re.IGNORECASE)[0].strip()
                       for match in re.finditer(r"^\s*Titular:[ \t]*([^\n]+)", text, re.IGNORECASE | re.MULTILINE)]
        cups_rows = [match[1] for match in re.finditer(
            r"Número que identifica[^\n]*\(CUPS\):([^\n]*(?:\n[^\n]*)?)", text, re.IGNORECASE,
        )]
    result["titular"] = unique("titular", {value for value in holder_rows if is_titular_value(value)})
    result["cups"] = unique("cups", {normalize_cups(match[0]) for row in cups_rows
                                      for match in CUPS_PATTERN.finditer(row) if is_valid_cups(match[0])})

    days = {int(value) for value in re.findall(r"\(\s*(?:Dies|Días):\s*(\d{1,3})\s*\)", text, re.IGNORECASE)}
    days.update(int(value) for value in re.findall(
        r"(?:Els dies que comprèn aquesta factura|Los días que comprende esta factura)\s+(\d{1,3})\s+(?:dies|días)\b", text, re.IGNORECASE,
    ))
    result["billing_days"] = unique("billing_days", {day for day in days if day > 0})
    energy_heading = r"(?:Per l'electricitat que has fet servir|Por la electricidad que has consumido)"
    power_heading = r"(?:Per la potència contractada|Por la potencia contratada)"
    energy_total = r"(?:El que et costa aquest mes l'energia consumida|Lo que te cuesta este mes la energía consumida)"
    power_total = r"(?:El que et costa aquest mes la potència contractada|Lo que te cuesta este mes la potencia contratada)"
    adjustment_label = r"(?:Cost d'ajustament per Red Elèctrica Espanyola|Coste de ajuste por Red Eléctrica Española)"
    result["competitor_invoice_amount"] = amount("competitor_invoice_amount", r"(?:Importe? total de la factura|Total que et toca pagar|(?:El )?total que te toca pagar)")
    for field, label in (
        ("competitor_energy_eur", rf"{energy_total} \(Total (?:€|EUR)\)"),
        ("competitor_power_eur", rf"(?:{power_total} \(Total (?:€|EUR)\)|{power_heading})"),
        ("meter_rental_eur", r"(?:(?:El )?lloguer del comptador|(?:El )?alquiler del contador)"),
        ("electricity_tax", r"(?:L'impost per l'electricitat que pagues a l'Estat|El impuesto por la electricidad que pagas al Estado)"),
        ("vat_amount", r"\bIVA\s+\d+(?:[.,]\d+)?\s*%"),
    ):
        result[field] = amount(field, label)
    for field, pattern in (
        ("electric_tax_rate_percent", r"(?:Impost|Impuesto) especial del (\d+(?:[.,]\d+)?)\s*%"),
        ("vat_rate_percent", r"\bIVA\s+(\d+(?:[.,]\d+)?)\s*%"),
    ):
        result[field] = unique(field, {normalize_number(value) for value in re.findall(pattern.replace(" ", r"\s+"), text, re.IGNORECASE)})

    sections = {}
    for kind, heading, end in (
        ("energy", energy_heading, rf"Cost d'ajustament|Coste de ajuste|{energy_total}"),
        ("power", power_heading, rf"{power_total}|{energy_heading}"),
    ):
        sections[kind] = re.findall(rf"^\s*{heading}\s*\n(.*?)(?=^\s*(?:{end})|\Z)",
                                    text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
    for kind, field, label, unit, periods in (
        ("energy", "energy_by_periods", r"(?:El que has consumit aquest mes|Lo que has consumido este mes)", "kWh", ("P1", "P2", "P3")),
        ("power", "contracted_power_kw_by_periods", r"(?:La potència que tens contractada|La potencia que tienes contratada)", "kW", ("P1", "P2")),
    ):
        candidates = {period: set() for period in periods}
        has_period_detail = False
        for section in sections[kind]:
            blocks = re.split(r"\bPer[ií]od[eo]\s+([123])\b", section, flags=re.IGNORECASE)
            has_period_detail |= len(blocks) > 1
            for index in range(1, len(blocks), 2):
                period = f"P{blocks[index]}"
                if period in candidates:
                    candidates[period].update(normalize_number(value) for value in re.findall(
                        rf"{label}\s+({POWER_PATTERN})\s*{unit}\b", blocks[index + 1], re.IGNORECASE,
                    ))
        # Older flat-price bills have no period breakdown in billed energy.
        # Read explicit consumption rows, never cumulative meter readings.
        if kind == "energy" and not has_period_detail:
            for readings in re.findall(
                r"Informaci[oó]n? del consum(?:o)? el[eèé]ctric(?:o)?(.*?)Total consum(?:o)? (?:dels|de los) per[ií]od[eo]s",
                text, re.IGNORECASE | re.DOTALL,
            ):
                blocks = re.split(r"\bPer[ií]od[eo]\s+([123])\b", readings, flags=re.IGNORECASE)
                for index in range(1, len(blocks), 2):
                    candidates[f"P{blocks[index]}"].update(normalize_number(value) for value in re.findall(
                        rf"Consum(?:o)? total del per[ií]od[eo]:\s*({POWER_PATTERN})\s*kWh\b",
                        blocks[index + 1], re.IGNORECASE,
                    ))
        if kind == "power":
            for p1, p2 in re.findall(
                rf"(?:Potència contractada|Potencia contratada)\s*\(kW\):\s*({POWER_PATTERN})\s*kW\s*-\s*({POWER_PATTERN})\s*kW\b",
                text, re.IGNORECASE,
            ):
                candidates["P1"].add(normalize_number(p1))
                candidates["P2"].add(normalize_number(p2))
        result[field] = {"P1": None, "P2": None, "P3": None}
        for period, values in candidates.items():
            result[field][period] = unique(f"{field}.{period}", values)

    energy_summary = amount("competitor_energy_eur", energy_heading)
    adjustment = amount("competitor_energy_eur", rf"(?:{adjustment_label})")
    energy, power = result["competitor_energy_eur"], result["competitor_power_eur"]
    if energy_summary is not None and energy is not None:
        if abs(Decimal(str(energy_summary)) - Decimal(str(energy)) - Decimal(str(adjustment or 0))) > Decimal("0.02"):
            result["competitor_energy_eur"] = None
            add_issue(result, "competitor_energy_eur", "energy_total_mismatch",
                      "No es pot conciliar l'energia del detall amb el resum i els serveis d'ajust. Cal revisar-la.")
    components = [energy_summary, power, result["electricity_tax"], result["meter_rental_eur"],
                  amount("competitor_invoice_amount", r"(?:Repercussió bo social|Repercusión bono social)"), result["vat_amount"]]
    total = result["competitor_invoice_amount"]
    if total is not None and all(value is not None for value in components):
        if abs(sum(Decimal(str(value)) for value in components) - Decimal(str(total))) > Decimal("0.02"):
            add_issue(result, "competitor_invoice_amount", "invoice_total_mismatch",
                      "La suma dels conceptes facturats no coincideix amb el total. Cal revisar-la.")


def extract_from_text(text: str, words: list[tuple[Any, ...]] | None = None) -> dict[str, Any]:
    """Apply deterministic extraction rules to native PDF text."""
    result = empty_result()
    result["retailer"] = extract_retailer(text, words)

    result["cups"] = extract_cups(text, words)
    result["titular"] = extract_titular(text, words)
    billing_days, derived = extract_billing_days(text, words)
    result["billing_days"] = billing_days
    result["competitor_invoice_amount"] = extract_total_amount(text, words)
    result.update(extract_component_costs(text))
    result["energy_by_periods"] = extract_energy_by_periods(text, words)
    result["contracted_power_kw_by_periods"] = extract_contracted_powers(text, words)
    result["meter_rental_eur"] = extract_meter_rental(text)
    result["vat_amount"] = extract_vat_amount(text)
    result["vat_rate_percent"] = extract_vat_rate(text)
    result["igic_lines"], result["igic_total_eur"] = extract_igic(text)
    result["electricity_tax"] = extract_electricity_tax(text)
    result["electric_tax_rate_percent"] = extract_electricity_tax_rate(text)
    result["self_consumption_surplus_kwh"] = extract_surplus_kwh(text)
    if result["retailer"] == "Octopus Energy":
        _extract_octopus_fields(text, result)
    if result["retailer"] == "Bonpreu Esclat Energia":
        _extract_bonpreu_fields(text, words, result)
        derived = False
    access_tariff = extract_access_tariff(text, words)
    if access_tariff == "2.0TD":
        result["contracted_power_kw_by_periods"]["P3"] = None
    if result["self_consumption_surplus_kwh"] is None and re.search(SURPLUS_LABEL_PATTERN, text, re.IGNORECASE):
        add_issue(
            result, "self_consumption_surplus_kwh", "missing_or_unverified",
            "La factura indica excedents, però no se n'ha pogut extreure la quantitat. Cal revisar-la.",
        )

    estimated_summary = re.search(r"resumen\s+de\s+tu\s+consumo\s+estimado", text, re.IGNORECASE)
    calculated_readings = result["retailer"] == "Holaluz" and re.search(
        r"(?:[úu]ltima\s+lectura|lectura\s+actual).{0,100}?\bcalculad[ao]\b",
        text, re.IGNORECASE | re.DOTALL,
    )
    if estimated_summary or calculated_readings:
        add_issue(result, "energy_by_periods", "estimated_consumption", "El consum indicat a la factura és estimat")

    if result["retailer"] == "Holaluz":
        total_consumption = re.search(
            rf"(?:\btotal\s*:\s*|(?:has\s+utilitzat|has\s+consumido)\s+)({NUMBER_PATTERN})\s*kwh",
            text, re.IGNORECASE,
        )
        energy = result["energy_by_periods"]
        if total_consumption and all(value is not None for value in energy.values()):
            if abs(sum(energy.values()) - normalize_number(total_consumption.group(1))) > 0.01:
                add_issue(result, "energy_by_periods", "consumption_total_mismatch", "La suma dels consums per període no coincideix amb el total de la factura.")

    for field in ("retailer", "cups", "titular", "billing_days", "competitor_invoice_amount"):
        if result[field] is None:
            message = (
                "No s'ha pogut identificar un CUPS únic amb format i lletres de control vàlids. Cal revisar-lo."
                if field == "cups" else "No s'ha pogut extreure i validar el camp."
            )
            add_issue(result, field, "missing_or_unverified", message)

    for period, value in result["energy_by_periods"].items():
        if value is None:
            add_issue(result, f"energy_by_periods.{period}", "missing_or_unverified", "No s'ha pogut extreure el consum en kWh.")

    for kind, label in [("energy", "consum"), ("power", "potència")]:
        field = f"competitor_{kind}_eur"
        if result[field] is None:
            add_issue(result, field, "missing_or_unverified", f"No s'ha pogut verificar l'import de {label} abans d'impostos i amb descomptes. És opcional; cal revisar-lo per proposar el motiu automàtic.")

    # Contracted power is implemented progressively for each retailer.
    for period, value in result["contracted_power_kw_by_periods"].items():
        # 2.0TD has only two power periods, regardless of retailer or missing values.
        if period == "P3" and access_tariff == "2.0TD":
            continue
        if value is None:
            add_issue(result, f"contracted_power_kw_by_periods.{period}", "missing_or_unverified", "No s'ha pogut extreure la potència contractada.")

    if result["meter_rental_eur"] is None:
        add_issue(result, "meter_rental_eur", "missing_or_unverified", "No s'ha pogut extreure el lloguer del comptador.")

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
