from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.config import load_pricing_config


TWOPLACES = Decimal("0.01")


class ComparisonInputError(Exception):
    def __init__(self, errors: dict[str, str]):
        super().__init__("Invalid comparison input")
        self.errors = errors


@dataclass(frozen=True)
class ComparisonInput:
    cups: str
    titular: str
    billing_days: int
    competitor_invoice_amount: Decimal
    energy_by_periods: dict[str, Decimal]


def build_comparison_report(payload: dict) -> dict:
    data = _validate_payload(payload)
    pricing = load_pricing_config()

    energy_breakdown = []
    energy_total = Decimal("0")
    for period, kwh in data.energy_by_periods.items():
        unit_price = Decimal(str(pricing["energy_prices_eur_per_kwh"].get(period, 0)))
        period_total = _money(kwh * unit_price)
        energy_total += period_total
        energy_breakdown.append(
            {
                "period": period,
                "kwh": float(kwh),
                "unit_price": float(unit_price),
                "amount": float(period_total),
            }
        )

    regulated_charge = _money(Decimal(str(pricing["regulated_charge_eur_per_day"])) * data.billing_days)
    social_bonus = _money(Decimal(str(pricing["social_bonus_eur_per_day"])) * data.billing_days)
    meter_rental = _money(Decimal(str(pricing["meter_rental_eur"])) )
    subtotal = energy_total + regulated_charge + social_bonus + meter_rental
    electric_tax_rate = Decimal(str(pricing["electric_tax_rate"]))
    vat_rate = Decimal(str(pricing["vat_rate"]))
    electric_tax = _money(subtotal * electric_tax_rate)
    vat_tax = _money((subtotal + electric_tax) * vat_rate)
    som_total = _money(subtotal + electric_tax + vat_tax)
    savings = _money(data.competitor_invoice_amount - som_total)

    return {
        "customer": {
            "cups": data.cups,
            "titular": data.titular,
        },
        "input": {
            "billing_days": data.billing_days,
            "competitor_invoice_amount": float(data.competitor_invoice_amount),
            "energy_by_periods": {period: float(kwh) for period, kwh in data.energy_by_periods.items()},
        },
        "pricing": {
            "tariff_name": pricing["tariff_name"],
            "effective_date": pricing["effective_date"],
            "currency": pricing["currency"],
        },
        "comparison": {
            "competitor_total": float(data.competitor_invoice_amount),
            "som_total": float(som_total),
            "savings": float(savings),
            "savings_label": "Estalvi" if savings >= 0 else "Diferencia",
        },
        "breakdown": {
            "energy": energy_breakdown,
            "totals": [
                {"label": "Cost per l'energia utilitzada", "amount": float(energy_total)},
                {"label": "Cost Serveis d'Ajust", "amount": float(regulated_charge)},
                {"label": "Bo Social", "amount": float(social_bonus)},
                {"label": "Cost del lloguer del comptador", "amount": float(meter_rental)},
                {"label": f"Impost elèctric {electric_tax_rate * 100}%", "amount": float(electric_tax)},
                {"label": f"IVA {vat_rate * 100}%", "amount": float(vat_tax)},
                {"label": "Total", "amount": float(som_total), "is_total": True},
            ],
        },
    }


def _validate_payload(payload: dict) -> ComparisonInput:
    errors: dict[str, str] = {}

    cups = str(payload.get("cups", "")).strip()
    if not cups:
        errors["cups"] = "El CUPS és obligatori."

    titular = str(payload.get("titular", "")).strip()
    if not titular:
        errors["titular"] = "El titular és obligatori."

    billing_days_raw = payload.get("billing_days")
    try:
        billing_days = int(billing_days_raw)
        if billing_days <= 0:
            raise ValueError
    except (TypeError, ValueError):
        errors["billing_days"] = "Els dies facturats han de ser un enter positiu."
        billing_days = 0

    competitor_total_raw = payload.get("competitor_invoice_amount")
    try:
        competitor_invoice_amount = Decimal(str(competitor_total_raw))
        if competitor_invoice_amount < 0:
            raise ValueError
    except (TypeError, ValueError, ArithmeticError):
        errors["competitor_invoice_amount"] = "L'import de la factura actual ha de ser positiu o zero."
        competitor_invoice_amount = Decimal("0")

    energy_payload = payload.get("energy_by_periods") or {}
    energy_by_periods: dict[str, Decimal] = {}
    if not isinstance(energy_payload, dict):
        errors["energy_by_periods"] = "L'energia per períodes ha de ser un objecte."
    else:
        for period in ("P1", "P2", "P3"):
            try:
                energy_value = Decimal(str(energy_payload.get(period, "")))
                if energy_value < 0:
                    raise ValueError
                energy_by_periods[period] = energy_value
            except (TypeError, ValueError, ArithmeticError):
                errors[f"energy_by_periods.{period}"] = f"El consum del període {period} ha de ser positiu o zero."

    if errors:
        raise ComparisonInputError(errors)

    return ComparisonInput(
        cups=cups,
        titular=titular,
        billing_days=billing_days,
        competitor_invoice_amount=competitor_invoice_amount,
        energy_by_periods=energy_by_periods,
    )


def _money(value: Decimal) -> Decimal:
    return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
