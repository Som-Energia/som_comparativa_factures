"""Read billed component amounts, never regulatory tolls or unit prices alone."""

from decimal import Decimal
import re
import unicodedata


MONEY = r"(-?\s*\d+(?:\.\d{3})*,\d{2}|-?\s*\d+\.\d{2})\s*(?:€|EUR)\s*$"
BILLED_MONEY = r"(?<![\d,])(-?\s*\d+(?:\.\d{3})*,\d{2}|-?\s*\d+\.\d{2})\s*(?:€|eur\b)(?!\s*/)"
LABELS = {
    "energy": r"(?:por energia (?:utilizada|consumida)|subtotal energia demandada|consumo electricidad|energia consumida(?: de la red)?|energia activa|(?:terme|termino|importe|cost|coste) (?:de (?:la )?)?energia|energia|consum|consumo)",
    "power": r"(?:por potencia (?:contractada|contratada)|(?:terme|termino|importe|cost|coste) (?:de (?:la )?)?potencia(?: (?:contractada|contratada))?|potencia(?: (?:contratada|contractada))?|terme fix|termino fijo)",
}


def _normalized(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFD", value.casefold())
        if unicodedata.category(char) != "Mn"
    )


def _amount(value: str) -> Decimal:
    value = value.replace(" ", "")
    return Decimal(value.replace(".", "").replace(",", ".") if "," in value else value)


def _label_rows(lines, label):
    """Keep labels at column starts and stop before unrelated adjacent columns."""
    for line in lines:
        for match in re.finditer(rf"\b{label}\b\s*:?[ .]*", line):
            if match.start() and not re.search(r"\s{2}$", line[:match.start()]):
                continue
            tail = line[match.end():].strip()
            amount = re.search(BILLED_MONEY, tail)
            if not amount:
                continue
            financial = line[match.start():match.end()] + tail[:amount.end()]
            # A regulatory paragraph can continue after the first amount.
            continuation = re.split(r"\s{2,}", tail[amount.end():])[0]
            if re.search(r"peatge|peaje|carrec|cargo|acceso|acces|impuesto|impost", financial + continuation):
                continue
            prefix = tail[:amount.start()].strip(" .:")
            yield financial, prefix, _amount(amount[1])


def _iberdrola_costs(lines):
    """Iberdrola's ENERGÍA summary also includes power and the social bonus."""
    power = set()
    energy = {}
    energy_totals = {}
    reading_energy = False
    blocks = closed_blocks = 0
    for line in lines:
        if match := re.match(r"total importe potencia hasta \d{2}/\d{2}/\d{4}\s+" + MONEY, line, re.IGNORECASE):
            power.add((line, _amount(match[1])))
        if re.match(r"energia consumida\s{2,}", line):
            reading_energy = True
            blocks += 1
        elif reading_energy and re.match(r"financiacion|total energia|servicios|compensacion|impuestos|iva", line):
            reading_energy = False
        if reading_energy:
            match = re.search(BILLED_MONEY, line)
            if match:
                if re.match(r"total .*kwh hasta \d{2}/\d{2}/\d{4}", line):
                    energy_totals[line] = _amount(match[1])
                    reading_energy = False
                    closed_blocks += 1
                else:
                    energy[line] = _amount(match[1])
            elif line and not re.match(r"horas |energia consumida", line):
                # An unrecognised amount or subheading in the block needs review.
                reading_energy = False
    energy_cost = sum(energy.values()) if energy else None
    if energy_totals and blocks == closed_blocks:
        total = sum(energy_totals.values())
        energy_cost = total if energy_cost is not None and abs(total - energy_cost) <= Decimal("0.02") else None
    else:
        energy_cost = None
    power_cost = sum(value for _, value in power) if power else None
    return {
        "competitor_energy_eur": float(energy_cost) if energy_cost is not None and energy_cost >= 0 else None,
        "competitor_power_eur": float(power_cost) if power_cost is not None and power_cost >= 0 else None,
    }


def extract_component_costs(text: str) -> dict[str, float | None]:
    """Prefer explicit totals; otherwise require all periods and apply explicit discounts.

    Ambiguous discounts, conflicting totals and flat-rate invoices stay unset.
    Prices/quantities in a formula are not accepted as the final billed amount.
    """
    lines = [_normalized(line).strip() for line in text.splitlines()]
    result = {"competitor_energy_eur": None, "competitor_power_eur": None}
    if any(re.search(r"cuota fija|quota fixa", line) for line in lines):
        return result
    if any(line.startswith("total importe potencia hasta ") for line in lines):
        return _iberdrola_costs(lines)

    discounts = {"energy": Decimal("0"), "power": Decimal("0")}
    uncertain = set()
    summary_amounts = {
        kind: {amount for _, prefix, amount in _label_rows(lines, label) if not prefix}
        for kind, label in LABELS.items()
    }
    for line in set(lines):
        if not re.match(r"(?:descuento|descompte|bonificacion|bonificacio)\b", line):
            continue
        # Ignore explanatory prose. A discount billing row has an amount or a %.
        amounts = list(re.finditer(BILLED_MONEY, line))
        match = amounts[-1] if amounts else None
        if not match and "%" not in line:
            continue
        components = [kind for kind, term in [("energy", r"energ|consum"), ("power", r"potencia")] if re.search(term, line)]
        # Some Endesa discounts name no component, but print the exact base.
        # Only allocate it when that base identifies one component uniquely.
        if not components and (base := re.search(r"(\d+(?:[.,]\d{2}))\s*eur\s*x", line)):
            components = [kind for kind, amounts in summary_amounts.items() if _amount(base[1]) in amounts]
        if len(components) != 1:
            uncertain.update(discounts)
        elif match:
            discounts[components[0]] -= abs(_amount(match[1]))
        else:
            uncertain.add(components[0])

    for kind, label in LABELS.items():
        totals = set()
        detail = {}
        formulas = {}
        for financial, prefix, amount in _label_rows(lines, label):
            # Factor Energia explicitly states that the agreed discount is included.
            prefix = re.sub(r"^\(el preu inclou el(?: descompte acordat\))?\s*", "", prefix)
            # Never mistake a unit price (€/kWh, €/kW/day) for an amount.
            if prefix.endswith(("/", "x", "×", "*")):
                continue
            period = re.match(r"\[?(P[123]|punta|llano|valle)\]?\b", prefix, re.IGNORECASE)
            if period:
                name = {"punta": "p1", "llano": "p2", "valle": "p3" if kind == "energy" else "p2"}.get(period[1], period[1].lower())
                detail[financial] = (name, amount)
            elif not prefix:
                totals.add(amount)
            elif re.match(r"^\d", prefix) and "kwh" in prefix and kind == "energy":
                formulas[financial] = amount

        required = {"p1", "p2", "p3"} if kind == "energy" else {"p1", "p2"}
        detailed = sum((value for _, value in detail.values()), Decimal("0")) if {period for period, _ in detail.values()} == required and len(detail) == len(required) else None
        if formulas:
            formula_total = sum(formulas.values())
            detailed = formula_total if detailed is None or abs(detailed - formula_total) <= Decimal("0.02") else None
        discount = discounts[kind]
        value = None
        if kind not in uncertain and len(totals) <= 1:
            if totals:
                total = next(iter(totals))
                if not discount and (detailed is None or abs(total - detailed) <= Decimal("0.02")):
                    value = total
                elif detailed is not None:
                    # Summary can be gross or already net: avoid a double discount.
                    net = detailed + discount
                    if abs(total - detailed) <= Decimal("0.02") or abs(total - net) <= Decimal("0.02"):
                        value = net
            elif detailed is not None:
                value = detailed + discount
        if value is not None and value >= 0:
            result[f"competitor_{kind}_eur"] = float(value)
    return result
