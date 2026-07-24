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
    contracted_power_kw_by_periods: dict[str, Decimal]
    self_consumption_surplus_kwh: Decimal
    meter_rental_eur: Decimal
    vat_rate: Decimal
    electric_tax_rate: Decimal


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

    power_breakdown = []
    power_total = Decimal("0")
    for period, kw in data.contracted_power_kw_by_periods.items():
        unit_price = Decimal(str(pricing["contracted_power_prices_eur_per_kw_day"].get(period, 0)))
        period_total = _money(kw * unit_price * data.billing_days)
        power_total += period_total
        power_breakdown.append(
            {
                "period": period,
                "kw": float(kw),
                "unit_price": float(unit_price),
                "amount": float(period_total),
            }
        )

    regulated_charge = _money(Decimal(str(pricing["regulated_charge_eur_per_day"])) * data.billing_days)
    social_bonus = _money(Decimal(str(pricing["social_bonus_eur_per_day"])) * data.billing_days)
    meter_rental = _money(data.meter_rental_eur)
    subtotal_before_compensation = energy_total + power_total + regulated_charge + social_bonus + meter_rental
    surplus_price = Decimal(str(pricing["self_consumption_surplus_price_eur_per_kwh"]))
    compensation_requested = _money(data.self_consumption_surplus_kwh * surplus_price)
    compensation_applied = min(compensation_requested, subtotal_before_compensation)
    subtotal = subtotal_before_compensation - compensation_applied
    surplus_used_kwh = min(data.self_consumption_surplus_kwh, compensation_applied / surplus_price)
    flux_solar_kwh = _quantity(data.self_consumption_surplus_kwh - surplus_used_kwh)
    electric_tax = _money(subtotal * data.electric_tax_rate)
    vat_tax = _money((subtotal + electric_tax) * data.vat_rate)
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
            "contracted_power_kw_by_periods": {
                period: float(kw) for period, kw in data.contracted_power_kw_by_periods.items()
            },
            "self_consumption_surplus_kwh": float(data.self_consumption_surplus_kwh),
            "meter_rental_eur": float(data.meter_rental_eur),
            "vat_rate_percent": float(data.vat_rate * 100),
            "electric_tax_rate_percent": float(data.electric_tax_rate * 100),
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
            "power": power_breakdown,
            "flux_solar_kwh": float(flux_solar_kwh),
            "totals": [
                {"label": "Cost per l'energia utilitzada", "amount": float(energy_total)},
                *[
                    {"label": f"Cost de potència {item['period']}", "amount": item["amount"]}
                    for item in power_breakdown
                ],
                {"label": "Cost Serveis d'Ajust", "amount": float(regulated_charge)},
                {"label": "Bo Social", "amount": float(social_bonus)},
                {"label": "Cost del lloguer del comptador", "amount": float(meter_rental)},
                {"label": "Compensació d'excedents", "amount": float(-compensation_applied)},
                {"label": f"Impost elèctric {data.electric_tax_rate * 100}%", "amount": float(electric_tax)},
                {"label": f"IVA {data.vat_rate * 100}%", "amount": float(vat_tax)},
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

    power_payload = payload.get("contracted_power_kw_by_periods") or {}
    contracted_power_kw_by_periods: dict[str, Decimal] = {}
    if not isinstance(power_payload, dict):
        errors["contracted_power_kw_by_periods"] = "La potència contractada per períodes ha de ser un objecte."
    else:
        for period in ("P1", "P2"):
            try:
                power_value = Decimal(str(power_payload.get(period, "")))
                if power_value < 0:
                    raise ValueError
                contracted_power_kw_by_periods[period] = power_value
            except (TypeError, ValueError, ArithmeticError):
                errors[f"contracted_power_kw_by_periods.{period}"] = (
                    f"La potència contractada del període {period} ha de ser positiva o zero."
                )

    self_consumption_surplus_kwh = _parse_non_negative_decimal(
        payload.get("self_consumption_surplus_kwh"),
        "self_consumption_surplus_kwh",
        "Els excedents d'autoconsum han de ser positius o zero.",
        errors,
    )
    meter_rental_eur = _parse_non_negative_decimal(
        payload.get("meter_rental_eur"),
        "meter_rental_eur",
        "El lloguer del comptador ha de ser positiu o zero.",
        errors,
    )
    vat_rate = _parse_percentage(payload.get("vat_rate_percent"), "vat_rate_percent", "El tipus d'IVA", errors)
    electric_tax_rate = _parse_percentage(
        payload.get("electric_tax_rate_percent"),
        "electric_tax_rate_percent",
        "El tipus d'impost elèctric",
        errors,
    )

    if errors:
        raise ComparisonInputError(errors)

    return ComparisonInput(
        cups=cups,
        titular=titular,
        billing_days=billing_days,
        competitor_invoice_amount=competitor_invoice_amount,
        energy_by_periods=energy_by_periods,
        contracted_power_kw_by_periods=contracted_power_kw_by_periods,
        self_consumption_surplus_kwh=self_consumption_surplus_kwh,
        meter_rental_eur=meter_rental_eur,
        vat_rate=vat_rate,
        electric_tax_rate=electric_tax_rate,
    )


def _money(value: Decimal) -> Decimal:
    return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _quantity(value: Decimal) -> Decimal:
    return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _parse_non_negative_decimal(raw_value, key: str, message: str, errors: dict[str, str]) -> Decimal:
    try:
        value = Decimal(str(raw_value))
        if value < 0:
            raise ValueError
        return value
    except (TypeError, ValueError, ArithmeticError):
        errors[key] = message
        return Decimal("0")


def _parse_percentage(raw_value, key: str, label: str, errors: dict[str, str]) -> Decimal:
    value = _parse_non_negative_decimal(raw_value, key, f"{label} ha de ser entre 0 i 100.", errors)
    if value > 100:
        errors[key] = f"{label} ha de ser entre 0 i 100."
        return Decimal("0")
    return value / 100
