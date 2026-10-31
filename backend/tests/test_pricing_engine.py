"""Pricing engine arithmetic. No database, no HTTP."""

from decimal import Decimal

import pytest

from app.services.pricing_engine import (
    price_line,
    resolve_tax_rate,
    summarise_lines,
)

pytestmark = pytest.mark.engine


def test_line_without_discount_or_tax():
    amounts = price_line(unit_price="1000.00", quantity=3)
    assert amounts.line_subtotal == Decimal("3000.00")
    assert amounts.line_discount_amount == Decimal("0.00")
    assert amounts.line_taxable_amount == Decimal("3000.00")
    assert amounts.line_tax_amount == Decimal("0.00")
    assert amounts.line_total == Decimal("3000.00")


def test_discount_then_tax_order():
    """Tax is charged on the discounted amount, not the gross."""
    amounts = price_line(
        unit_price="1000.00", quantity=10, discount_percent="10", tax_rate="18"
    )
    assert amounts.line_subtotal == Decimal("10000.00")
    assert amounts.line_discount_amount == Decimal("1000.00")
    assert amounts.line_taxable_amount == Decimal("9000.00")
    assert amounts.line_tax_amount == Decimal("1620.00")  # 18% of 9000, not of 10000
    assert amounts.line_total == Decimal("10620.00")


def test_amounts_are_quantised_to_two_places():
    amounts = price_line(
        unit_price="333.33", quantity=7, discount_percent="7.5", tax_rate="18"
    )
    for value in amounts.as_dict().values():
        assert value == value.quantize(Decimal("0.01"))


def test_half_up_rounding_not_bankers_rounding():
    """0.125 -> 0.13, where Python's round() would give 0.12."""
    amounts = price_line(unit_price="0.25", quantity=1, discount_percent="50")
    assert amounts.line_discount_amount == Decimal("0.13")


def test_float_input_does_not_leak_binary_noise():
    amounts = price_line(unit_price=0.1, quantity=3)
    assert amounts.line_subtotal == Decimal("0.30")


def test_full_discount_leaves_nothing_payable():
    amounts = price_line(
        unit_price="500.00", quantity=4, discount_percent="100", tax_rate="18"
    )
    assert amounts.line_taxable_amount == Decimal("0.00")
    assert amounts.line_total == Decimal("0.00")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"unit_price": "100.00", "quantity": 0},
        {"unit_price": "100.00", "quantity": -1},
        {"unit_price": "-100.00", "quantity": 1},
        {"unit_price": "100.00", "quantity": 1, "discount_percent": "101"},
        {"unit_price": "100.00", "quantity": 1, "discount_percent": "-1"},
        {"unit_price": "100.00", "quantity": 1, "tax_rate": "-5"},
    ],
)
def test_invalid_inputs_are_rejected(kwargs):
    with pytest.raises(ValueError):
        price_line(**kwargs)


def test_totals_are_the_sum_of_rounded_lines():
    """The printed lines must add up to the printed total, exactly."""
    lines = [
        price_line(
            unit_price="333.33", quantity=3, discount_percent="5", tax_rate="18"
        ).as_dict()
        | {"quantity": 3},
        price_line(
            unit_price="19.99", quantity=17, discount_percent="2.5", tax_rate="12"
        ).as_dict()
        | {"quantity": 17},
        price_line(unit_price="1250.00", quantity=1, tax_rate="18").as_dict()
        | {"quantity": 1},
    ]
    totals = summarise_lines(lines)

    assert totals.line_count == 3
    assert totals.total_quantity == 21
    assert totals.subtotal == sum(line["line_subtotal"] for line in lines)
    assert totals.final_amount == sum(line["line_total"] for line in lines)
    # Totals are internally consistent.
    assert totals.taxable_amount == totals.subtotal - totals.total_discount
    assert totals.final_amount == totals.taxable_amount + totals.total_tax


def test_effective_discount_percent_is_derived_from_the_totals():
    lines = [
        price_line(unit_price="1000.00", quantity=10, discount_percent="10").as_dict()
        | {"quantity": 10},
        price_line(unit_price="1000.00", quantity=10, discount_percent="0").as_dict()
        | {"quantity": 10},
    ]
    totals = summarise_lines(lines)
    # 1000 off 20000 == 5%
    assert totals.total_discount == Decimal("1000.00")
    assert totals.effective_discount_percent == Decimal("5.00")


def test_empty_line_set_totals_to_zero():
    totals = summarise_lines([])
    assert totals.final_amount == Decimal("0.00")
    assert totals.effective_discount_percent == Decimal("0.00")
    assert totals.line_count == 0


def test_product_tax_rate_overrides_the_company_default():
    assert resolve_tax_rate(Decimal("5"), "18") == Decimal("5.00")
    assert resolve_tax_rate(None, "18") == Decimal("18.00")
