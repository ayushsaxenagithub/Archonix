from decimal import Decimal

import pytest

from app.pricing import apply_discount


def test_discount_rounds_half_up():
    assert apply_discount(Decimal("10.005"), 0) == Decimal("10.01")


def test_discount_applies_percent():
    assert apply_discount(Decimal("200.00"), 25) == Decimal("150.00")


def test_rejects_out_of_range_percent():
    with pytest.raises(ValueError):
        apply_discount(Decimal("1"), 101)
