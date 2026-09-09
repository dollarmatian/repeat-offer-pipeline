"""Meter reads to a charge. Synthetic tariffs; the shape is the point."""

from decimal import Decimal
from types import MappingProxyType

from engine.rules import Input, Ruleset
from rulesets.metering.amount import ChargeFromConsumption
from rulesets.metering.eligibility import (
    ConsumptionPlausible,
    PeriodKnown,
    ReadNotBelowPrevious,
    ReadSourceAccepted,
)
from rulesets.metering.pricing import UnitRate


class MeteringV1(Ruleset):
    name = "metering"
    version = "1"
    description = "Which reads are valid, which tariff applies, what is billed."
    inputs = (
        Input("previous_read", int, description="Meter register at the start of the period"),
        Input("current_read", int, description="Meter register at the end of the period"),
        Input("days_in_period", int),
        Input("read_source", str, description="smart, customer, agent or estimated"),
        Input("tariff_code", str),
    )
    config = MappingProxyType(
        {
            "accepted_sources": ("smart", "customer", "agent"),
            "max_daily_kwh": Decimal("100"),
            "unit_rates_pence": MappingProxyType(
                {"standard": Decimal("24.50"), "economy": Decimal("21.00")}
            ),
        }
    )
    rules = (
        PeriodKnown,
        ReadSourceAccepted,
        ReadNotBelowPrevious,
        ConsumptionPlausible,
        UnitRate,
        ChargeFromConsumption,
    )
