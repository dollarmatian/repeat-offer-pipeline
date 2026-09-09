"""Illustrative and synthetic. A decisioning pipeline, not a credit model."""

from decimal import Decimal
from types import MappingProxyType

from engine.rules import Input, Ruleset
from rulesets.lending.amount import AmountFromRevenue, MinimumOffer, OfferCap
from rulesets.lending.eligibility import (
    BalanceToRevenue,
    BureauScore,
    MissedPayments,
    RepaymentHistory,
)
from rulesets.lending.pricing import BaseRate, SectorLoading

INPUTS = (
    Input("loans_repaid", int, description="Loans repaid in full with this lender"),
    Input("missed_payments_last_12m", int),
    Input("outstanding_balance", Decimal, description="Balance still owed, in pounds"),
    Input("average_monthly_revenue", Decimal, description="In pounds"),
    Input("requested_amount", Decimal, description="In pounds"),
    Input("sector", str),
)

CONFIG_V1 = MappingProxyType(
    {
        "missed_payments_refer_at": 1,
        "missed_payments_fail_at": 2,
        "max_balance_to_revenue": Decimal("2"),
        "established_loans": 3,
        "rate_established": Decimal("0.019"),
        "rate_standard": Decimal("0.029"),
        "sector_loading": Decimal("0.005"),
        "loaded_sectors": ("construction", "hospitality"),
        "revenue_multiple": Decimal("3"),
        "rounding": Decimal("100"),
        "offer_cap": Decimal("50000"),
        "minimum_offer": Decimal("1000"),
    }
)


class LendingV1(Ruleset):
    name = "lending"
    version = "1"
    description = "Repeat offer: eligibility, monthly rate, then amount."
    inputs = INPUTS
    config = CONFIG_V1
    rules = (
        RepaymentHistory,
        MissedPayments,
        BalanceToRevenue,
        BaseRate,
        SectorLoading,
        AmountFromRevenue,
        OfferCap,
        MinimumOffer,
    )


class LendingV2(LendingV1):
    """Adds a bureau check and raises the cap. Rolled out behind a flag, compared on metrics."""

    version = "2"
    description = "As version 1, with a bureau score check and a higher cap."
    inputs = INPUTS + (
        Input("bureau_score", int, required=False, description="From the bureau integration"),
        Input("bureau_status", str, required=False, description="Why a score is missing, if it is"),
    )
    config = MappingProxyType(
        {**CONFIG_V1, "bureau_score_floor": 400, "offer_cap": Decimal("75000")}
    )
    rules = (
        RepaymentHistory,
        MissedPayments,
        BalanceToRevenue,
        BureauScore,
        BaseRate,
        SectorLoading,
        AmountFromRevenue,
        OfferCap,
        MinimumOffer,
    )
