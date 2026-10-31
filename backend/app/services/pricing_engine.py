"""Monetary calculation engine.

Pure functions with no database access, so the arithmetic can be unit-tested in
isolation. Calculation order per line:

    line_subtotal  = unit_price x quantity
    discount       = line_subtotal x discount_percent / 100
    taxable_amount = line_subtotal - discount
    tax            = taxable_amount x tax_rate / 100
    line_total     = taxable_amount + tax

Document totals are the sum of the already-rounded line amounts, so the printed
lines always add up to the printed total (summing first and rounding last would
let the two disagree by a cent).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.utils.money import HUNDRED, ZERO, money, percent_of, rate, to_decimal


@dataclass(slots=True)
class LineAmounts:
    """The six figures that describe one priced line."""

    line_subtotal: Decimal = ZERO
    line_discount_amount: Decimal = ZERO
    line_taxable_amount: Decimal = ZERO
    tax_rate: Decimal = ZERO
    line_tax_amount: Decimal = ZERO
    line_total: Decimal = ZERO

    def as_dict(self) -> dict[str, Decimal]:
        return {
            "line_subtotal": self.line_subtotal,
            "line_discount_amount": self.line_discount_amount,
            "line_taxable_amount": self.line_taxable_amount,
            "tax_rate": self.tax_rate,
            "line_tax_amount": self.line_tax_amount,
            "line_total": self.line_total,
        }


@dataclass(slots=True)
class DocumentTotals:
    """Document-level roll-up of a set of priced lines."""

    subtotal: Decimal = ZERO
    total_discount: Decimal = ZERO
    taxable_amount: Decimal = ZERO
    total_tax: Decimal = ZERO
    final_amount: Decimal = ZERO
    effective_discount_percent: Decimal = ZERO
    total_quantity: int = 0
    line_count: int = 0
    currency: str = "INR"
    tax_label: str = "GST"

    def as_dict(self) -> dict:
        return {
            "subtotal": self.subtotal,
            "total_discount": self.total_discount,
            "taxable_amount": self.taxable_amount,
            "total_tax": self.total_tax,
            "final_amount": self.final_amount,
            "effective_discount_percent": self.effective_discount_percent,
            "total_quantity": self.total_quantity,
            "line_count": self.line_count,
            "currency": self.currency,
            "tax_label": self.tax_label,
        }


def price_line(
    *,
    unit_price: Decimal | str | int,
    quantity: int,
    discount_percent: Decimal | str | int = ZERO,
    tax_rate: Decimal | str | int = ZERO,
) -> LineAmounts:
    """Compute the amounts for a single quotation line."""
    if quantity < 1:
        raise ValueError("quantity must be at least 1")

    unit = money(unit_price)
    discount_pct = rate(discount_percent)
    tax_pct = rate(tax_rate)

    if unit < ZERO:
        raise ValueError("unit_price cannot be negative")
    if discount_pct < ZERO or discount_pct > HUNDRED:
        raise ValueError("discount_percent must be between 0 and 100")
    if tax_pct < ZERO:
        raise ValueError("tax_rate cannot be negative")

    subtotal = money(unit * Decimal(quantity))
    discount_amount = percent_of(subtotal, discount_pct)
    taxable = money(subtotal - discount_amount)
    tax_amount = percent_of(taxable, tax_pct)

    return LineAmounts(
        line_subtotal=subtotal,
        line_discount_amount=discount_amount,
        line_taxable_amount=taxable,
        tax_rate=tax_pct,
        line_tax_amount=tax_amount,
        line_total=money(taxable + tax_amount),
    )


def summarise_lines(
    lines: list[dict],
    *,
    currency: str = "INR",
    tax_label: str = "GST",
) -> DocumentTotals:
    """Roll a list of priced line dicts up into document totals."""
    totals = DocumentTotals(currency=currency, tax_label=tax_label)

    for line in lines:
        totals.subtotal += to_decimal(line.get("line_subtotal"))
        totals.total_discount += to_decimal(line.get("line_discount_amount"))
        totals.taxable_amount += to_decimal(line.get("line_taxable_amount"))
        totals.total_tax += to_decimal(line.get("line_tax_amount"))
        totals.final_amount += to_decimal(line.get("line_total"))
        totals.total_quantity += int(line.get("quantity") or 0)
        totals.line_count += 1

    totals.subtotal = money(totals.subtotal)
    totals.total_discount = money(totals.total_discount)
    totals.taxable_amount = money(totals.taxable_amount)
    totals.total_tax = money(totals.total_tax)
    totals.final_amount = money(totals.final_amount)

    if totals.subtotal > ZERO:
        totals.effective_discount_percent = rate(
            totals.total_discount / totals.subtotal * HUNDRED
        )

    return totals


def resolve_tax_rate(
    product_tax_rate: Decimal | None, default_tax_rate: Decimal | str | int
) -> Decimal:
    """A product may override the company default rate; otherwise use the default."""
    if product_tax_rate is not None:
        return rate(product_tax_rate)
    return rate(default_tax_rate)
