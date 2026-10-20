"""Pure business logic, testable without the web framework."""

from decimal import ROUND_HALF_UP, Decimal


def apply_discount(amount: Decimal, percent: int) -> Decimal:
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    discounted = amount * (Decimal(100 - percent) / Decimal(100))
    return discounted.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def legacy_rounding(amount):  # deliberately unused: a dead-code candidate for Vulture
    return round(amount, 2)
