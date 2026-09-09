"""Each rule on its own: declared inputs in, a result with a reason out."""

from decimal import Decimal

import pytest

from engine.rules import Outcome, UndeclaredDecision, UndeclaredInput
from rulesets.lending.amount import AmountFromRevenue, MinimumOffer, OfferCap
from rulesets.lending.eligibility import (
    BalanceToRevenue,
    BureauScore,
    MissedPayments,
    RepaymentHistory,
)
from rulesets.lending.pricing import BaseRate, SectorLoading
from rulesets.lending.ruleset import LendingV2


def evaluate(rule_cls, inputs, config, decided=None):
    return rule_cls().run(inputs, decided or {}, config)


class TestRepaymentHistory:
    def test_no_loans_repaid_fails(self, lending_config):
        result = evaluate(RepaymentHistory, {"loans_repaid": 0}, lending_config)
        assert result.outcome is Outcome.FAIL
        assert "no loan repaid" in result.reason

    def test_one_loan_repaid_passes(self, lending_config):
        assert (
            evaluate(RepaymentHistory, {"loans_repaid": 1}, lending_config).outcome is Outcome.PASS
        )


class TestMissedPayments:
    @pytest.mark.parametrize(
        "missed, outcome",
        [(0, Outcome.PASS), (1, Outcome.REFER), (2, Outcome.FAIL), (5, Outcome.FAIL)],
    )
    def test_bands(self, lending_config, missed, outcome):
        result = evaluate(MissedPayments, {"missed_payments_last_12m": missed}, lending_config)
        assert result.outcome is outcome


class TestBalanceToRevenue:
    def test_within_limit_passes(self, lending_config):
        inputs = {
            "outstanding_balance": Decimal("20000"),
            "average_monthly_revenue": Decimal("10000"),
        }
        assert evaluate(BalanceToRevenue, inputs, lending_config).outcome is Outcome.PASS

    def test_over_limit_fails(self, lending_config):
        inputs = {
            "outstanding_balance": Decimal("20001"),
            "average_monthly_revenue": Decimal("10000"),
        }
        result = evaluate(BalanceToRevenue, inputs, lending_config)
        assert result.outcome is Outcome.FAIL
        assert "2x revenue" in result.reason

    def test_no_revenue_fails(self, lending_config):
        inputs = {"outstanding_balance": Decimal("0"), "average_monthly_revenue": Decimal("0")}
        assert evaluate(BalanceToRevenue, inputs, lending_config).outcome is Outcome.FAIL


class TestBureauScore:
    def test_missing_score_refers_with_the_status(self):
        inputs = {"bureau_score": None, "bureau_status": "unavailable after 3 attempts: timeout"}
        result = evaluate(BureauScore, inputs, LendingV2.config)
        assert result.outcome is Outcome.REFER
        assert "timeout" in result.reason

    def test_below_floor_fails(self):
        inputs = {"bureau_score": 399, "bureau_status": "ok"}
        assert evaluate(BureauScore, inputs, LendingV2.config).outcome is Outcome.FAIL

    def test_at_floor_passes(self):
        inputs = {"bureau_score": 400, "bureau_status": "ok"}
        assert evaluate(BureauScore, inputs, LendingV2.config).outcome is Outcome.PASS


class TestBaseRate:
    def test_established_band(self, lending_config):
        result = evaluate(BaseRate, {"loans_repaid": 3}, lending_config)
        assert result.values == {"rate": Decimal("0.019")}

    def test_standard_band(self, lending_config):
        result = evaluate(BaseRate, {"loans_repaid": 2}, lending_config)
        assert result.values == {"rate": Decimal("0.029")}


class TestSectorLoading:
    def test_loaded_sector_adds_to_the_rate_already_decided(self, lending_config):
        result = evaluate(
            SectorLoading,
            {"sector": "construction"},
            lending_config,
            decided={"rate": Decimal("0.019")},
        )
        assert result.values == {"rate": Decimal("0.024")}

    def test_other_sector_leaves_the_rate_alone(self, lending_config):
        result = evaluate(
            SectorLoading, {"sector": "retail"}, lending_config, decided={"rate": Decimal("0.019")}
        )
        assert result.outcome is Outcome.PASS
        assert result.values == {}


class TestAmountFromRevenue:
    def test_requested_amount_when_affordable(self, lending_config):
        inputs = {"requested_amount": Decimal("20000"), "average_monthly_revenue": Decimal("10000")}
        assert evaluate(AmountFromRevenue, inputs, lending_config).values == {
            "amount": Decimal("20000")
        }

    def test_capped_by_revenue_and_rounded_down(self, lending_config):
        inputs = {"requested_amount": Decimal("50000"), "average_monthly_revenue": Decimal("3350")}
        assert evaluate(AmountFromRevenue, inputs, lending_config).values == {
            "amount": Decimal("10000")
        }


class TestOfferCap:
    def test_above_cap_is_capped(self, lending_config):
        result = evaluate(OfferCap, {}, lending_config, decided={"amount": Decimal("60000")})
        assert result.values == {"amount": Decimal("50000")}

    def test_within_cap_unchanged(self, lending_config):
        result = evaluate(OfferCap, {}, lending_config, decided={"amount": Decimal("60")})
        assert result.values == {}


class TestMinimumOffer:
    def test_below_minimum_fails(self, lending_config):
        result = evaluate(MinimumOffer, {}, lending_config, decided={"amount": Decimal("900")})
        assert result.outcome is Outcome.FAIL

    def test_at_minimum_passes(self, lending_config):
        result = evaluate(MinimumOffer, {}, lending_config, decided={"amount": Decimal("1000")})
        assert result.outcome is Outcome.PASS


class TestDeclaredShape:
    def test_a_rule_cannot_read_an_input_it_did_not_declare(self, lending_config):
        class Sneaky(RepaymentHistory):
            name = "test.sneaky"

            def evaluate(self, ctx):
                return self.passes(str(ctx.inputs["sector"]))

        with pytest.raises(UndeclaredInput):
            evaluate(Sneaky, {"loans_repaid": 1, "sector": "retail"}, lending_config)

    def test_a_rule_cannot_decide_a_value_it_did_not_declare(self, lending_config):
        class Sneaky(RepaymentHistory):
            name = "test.sneaky"

            def evaluate(self, ctx):
                return self.passes("ok", rate=Decimal("0.5"))

        with pytest.raises(UndeclaredDecision):
            evaluate(Sneaky, {"loans_repaid": 1}, lending_config)
