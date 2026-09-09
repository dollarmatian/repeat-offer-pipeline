"""Stage sequencing, with no database: the engine as a pure function."""

from decimal import Decimal

import pytest

from engine.evaluate import STAGE_CONTRACT, Evaluation, evaluate
from engine.rules import Outcome, Result, Rule, Ruleset, RulesetError, Stage
from rulesets.lending.ruleset import LendingV1
from rulesets.metering.ruleset import MeteringV1


def stages_run(evaluation):
    return [s.stage for s in evaluation.stages]


class TestLendingSequence:
    def test_a_clean_run_goes_through_all_three_stages(self, lending_inputs):
        evaluation = evaluate(LendingV1, lending_inputs)
        assert evaluation.outcome == Evaluation.DECIDED
        assert evaluation.stopped_at is None
        assert evaluation.decision == {"rate": Decimal("0.019"), "amount": Decimal("20000")}
        assert set(stages_run(evaluation)) == {Stage.ELIGIBILITY, Stage.PRICE, Stage.AMOUNT}

    def test_failing_eligibility_is_never_priced(self, lending_inputs):
        evaluation = evaluate(LendingV1, {**lending_inputs, "loans_repaid": 0})
        assert evaluation.outcome == Evaluation.DECLINED
        assert evaluation.stopped_at is Stage.ELIGIBILITY
        assert Stage.PRICE not in stages_run(evaluation)
        assert evaluation.decision == {}

    def test_a_referral_stops_the_run_and_names_the_rule(self, lending_inputs):
        evaluation = evaluate(LendingV1, {**lending_inputs, "missed_payments_last_12m": 1})
        assert evaluation.outcome == Evaluation.REFERRED
        assert evaluation.referral.rule_name == "lending.missed_payments"
        assert Stage.PRICE not in stages_run(evaluation)

    def test_rules_in_a_stage_run_in_declared_order(self, lending_inputs):
        evaluation = evaluate(LendingV1, {**lending_inputs, "sector": "construction"})
        names = [s.rule_name for s in evaluation.stages if s.stage is Stage.PRICE]
        assert names == ["lending.base_rate", "lending.sector_loading"]
        assert evaluation.decision["rate"] == Decimal("0.024")

    def test_a_decline_at_the_amount_stage_keeps_the_rate_decided(self, lending_inputs):
        evaluation = evaluate(LendingV1, {**lending_inputs, "requested_amount": Decimal("500")})
        assert evaluation.outcome == Evaluation.DECLINED
        assert evaluation.stopped_at is Stage.AMOUNT
        assert evaluation.stages[-1].rule_name == "lending.minimum_offer"
        assert evaluation.decision["rate"] == Decimal("0.019")

    def test_every_stage_result_carries_a_reason(self, lending_inputs):
        evaluation = evaluate(LendingV1, lending_inputs)
        assert all(s.reason for s in evaluation.stages)


class TestMeteringSequence:
    def test_a_clean_read_is_charged(self, metering_inputs):
        evaluation = evaluate(MeteringV1, metering_inputs)
        assert evaluation.outcome == Evaluation.DECIDED
        assert evaluation.decision == {
            "consumption_kwh": 300,
            "rate": Decimal("24.50"),
            "amount": Decimal("73.50"),
        }

    def test_an_estimate_is_never_priced(self, metering_inputs):
        evaluation = evaluate(MeteringV1, {**metering_inputs, "read_source": "estimated"})
        assert evaluation.outcome == Evaluation.DECLINED
        assert Stage.PRICE not in stages_run(evaluation)

    def test_zero_consumption_is_decided_not_declined(self, metering_inputs):
        evaluation = evaluate(MeteringV1, {**metering_inputs, "current_read": 1000})
        assert evaluation.outcome == Evaluation.DECIDED
        assert evaluation.decision["amount"] == Decimal("0.00")


class TestOverrides:
    def test_an_override_replaces_the_rule_result_and_is_marked(self, lending_inputs):
        inputs = {**lending_inputs, "missed_payments_last_12m": 1}
        override = {"lending.missed_payments": Result(Outcome.PASS, "overridden by ops")}
        evaluation = evaluate(LendingV1, inputs, override)
        assert evaluation.outcome == Evaluation.DECIDED
        overridden = [s for s in evaluation.stages if s.overridden]
        assert [s.rule_name for s in overridden] == ["lending.missed_payments"]


class TestStageContract:
    def test_a_price_stage_that_decides_nothing_refers(self, metering_inputs):
        class SilentRate(Rule):
            name = "test.silent_rate"
            stage = Stage.PRICE
            decides = ("rate",)

            def evaluate(self, ctx):
                return self.passes("said nothing")

        class Silent(MeteringV1):
            rules = tuple(r for r in MeteringV1.rules if r.stage is not Stage.PRICE) + (SilentRate,)

        evaluation = evaluate(Silent, metering_inputs)
        assert evaluation.outcome == Evaluation.REFERRED
        assert evaluation.referral.rule_name == STAGE_CONTRACT
        assert evaluation.referral.stage is Stage.PRICE

    def test_a_ruleset_with_no_rule_for_a_required_value_is_rejected_up_front(self):
        class NoAmount(Ruleset):
            name = "test"
            version = "1"
            inputs = MeteringV1.inputs
            rules = tuple(r for r in MeteringV1.rules if r.stage is not Stage.AMOUNT)

        with pytest.raises(RulesetError, match="no amount rule decides 'amount'"):
            NoAmount.check()

    def test_a_rule_requiring_an_undeclared_input_is_rejected_up_front(self):
        class Bad(Ruleset):
            name = "test"
            version = "1"
            inputs = ()
            rules = MeteringV1.rules

        with pytest.raises(RulesetError, match="requires undeclared inputs"):
            Bad.check()


class TestValidation:
    def test_inputs_are_coerced_to_declared_types(self):
        validated = LendingV1.validate(
            {
                "loans_repaid": "3",
                "missed_payments_last_12m": 0,
                "outstanding_balance": "5000.50",
                "average_monthly_revenue": 10000,
                "requested_amount": 20000.0,
                "sector": "retail",
            }
        )
        assert validated["loans_repaid"] == 3
        assert validated["outstanding_balance"] == Decimal("5000.50")
        assert isinstance(validated["requested_amount"], Decimal)

    def test_missing_wrong_and_undeclared_inputs_are_all_reported(self, lending_inputs):
        from engine.rules import InvalidInputs

        raw = {**lending_inputs, "loans_repaid": "three", "colour": "blue"}
        del raw["sector"]
        with pytest.raises(InvalidInputs) as info:
            LendingV1.validate(raw)
        assert info.value.errors == {
            "loans_repaid": "must be an integer",
            "sector": "is required",
            "colour": "is not a declared input",
        }
