"""One run, one record, and the same inputs twice make one record."""

from decimal import Decimal

import pytest

from engine.models import DecisionRecord, ExceptionCase, RolloutFlag, StageOutcome
from engine.pipeline import idempotency_key, run

pytestmark = pytest.mark.django_db


class TestDecisionRecord:
    def test_a_run_writes_everything_needed_to_explain_it(self, lending_inputs):
        result = run("lending", "CUST-1", {**lending_inputs, "sector": "construction"})
        record = result.record
        assert result.created
        assert record.reference.startswith("dec_")
        assert record.ruleset_name == "lending"
        assert record.ruleset_version == "1"
        assert record.subject_reference == "CUST-1"
        assert record.inputs["sector"] == "construction"
        assert record.inputs["requested_amount"] == "20000"
        assert record.outcome == DecisionRecord.Outcome.DECIDED
        assert record.decision == {"rate": "0.024", "amount": "20000"}
        assert record.flag_state == {
            "flag": None,
            "matched": False,
            "bucket": record.flag_state["bucket"],
            "version": "1",
        }

        fired = list(record.stage_outcomes.values_list("stage", "rule_name", "outcome"))
        assert fired == [
            ("eligibility", "lending.repayment_history", "pass"),
            ("eligibility", "lending.missed_payments", "pass"),
            ("eligibility", "lending.balance_to_revenue", "pass"),
            ("price", "lending.base_rate", "pass"),
            ("price", "lending.sector_loading", "pass"),
            ("amount", "lending.amount_from_revenue", "pass"),
            ("amount", "lending.offer_cap", "pass"),
            ("amount", "lending.minimum_offer", "pass"),
        ]
        loading = record.stage_outcomes.get(rule_name="lending.sector_loading")
        assert loading.values == {"rate": "0.024"}
        assert "construction" in loading.reason

    def test_a_decline_records_where_it_stopped(self, lending_inputs):
        record = run("lending", "CUST-2", {**lending_inputs, "loans_repaid": 0}).record
        assert record.outcome == DecisionRecord.Outcome.DECLINED
        assert record.stopped_at_stage == "eligibility"
        assert record.stage_outcomes.count() == 1
        assert not hasattr(record, "exception_case")

    def test_a_referral_opens_an_exception(self, lending_inputs):
        record = run("lending", "CUST-3", {**lending_inputs, "missed_payments_last_12m": 1}).record
        assert record.outcome == DecisionRecord.Outcome.REFERRED
        case = record.exception_case
        assert case.status == ExceptionCase.Status.OPEN
        assert case.stage == "eligibility"
        assert case.rule_name == "lending.missed_payments"


class TestIdempotency:
    def test_the_same_inputs_return_the_record_already_written(self, lending_inputs):
        first = run("lending", "CUST-1", lending_inputs)
        second = run("lending", "CUST-1", lending_inputs)
        assert first.created and not second.created
        assert first.record.pk == second.record.pk
        assert DecisionRecord.objects.count() == 1
        assert StageOutcome.objects.count() == 8

    def test_equivalent_representations_share_a_key(self):
        a = idempotency_key("lending", "1", {"requested_amount": Decimal("20000")})
        b = idempotency_key("lending", "1", {"requested_amount": Decimal("20000.00")})
        assert a == b

    def test_changed_inputs_make_a_new_record(self, lending_inputs):
        run("lending", "CUST-1", lending_inputs)
        run("lending", "CUST-1", {**lending_inputs, "requested_amount": Decimal("21000")})
        assert DecisionRecord.objects.filter(subject_reference="CUST-1").count() == 2

    def test_a_new_ruleset_version_is_a_new_decision(self, lending_inputs):
        run("lending", "CUST-1", lending_inputs, version="1")
        run("lending", "CUST-1", lending_inputs, version="2")
        assert DecisionRecord.objects.count() == 2

    def test_a_referred_run_re_run_does_not_open_a_second_exception(self, lending_inputs):
        inputs = {**lending_inputs, "missed_payments_last_12m": 1}
        run("lending", "CUST-3", inputs)
        run("lending", "CUST-3", inputs)
        assert ExceptionCase.objects.count() == 1


class TestRolloutFlags:
    def test_without_a_flag_the_default_version_runs(self, lending_inputs):
        record = run("lending", "CUST-1", lending_inputs).record
        assert record.ruleset_version == "1"
        assert record.flag_state["matched"] is False

    def test_an_allowlisted_subject_gets_the_flagged_version(self, lending_inputs):
        RolloutFlag.objects.create(
            key="lending-v2", ruleset_name="lending", version="2", allowlist=["CUST-1"]
        )
        record = run("lending", "CUST-1", lending_inputs).record
        assert record.ruleset_version == "2"
        assert record.flag_state["flag"] == "lending-v2"
        assert record.flag_state["listed"] is True
        # version 2 needs a bureau score, so with none supplied it refers
        assert record.outcome == DecisionRecord.Outcome.REFERRED
        assert record.exception_case.rule_name == "lending.bureau_score"

    def test_a_percentage_rollout_is_deterministic_per_subject(self, lending_inputs):
        RolloutFlag.objects.create(key="half", ruleset_name="lending", version="2", percent=50)
        subjects = [f"CUST-{n}" for n in range(40)]
        versions = {s: run("lending", s, lending_inputs).record.ruleset_version for s in subjects}
        assert set(versions.values()) == {"1", "2"}
        again = {s: run("lending", s, lending_inputs).record.ruleset_version for s in subjects}
        assert again == versions

    def test_a_disabled_flag_does_nothing(self, lending_inputs):
        RolloutFlag.objects.create(
            key="off", ruleset_name="lending", version="2", percent=100, enabled=False
        )
        assert run("lending", "CUST-1", lending_inputs).record.ruleset_version == "1"

    def test_a_forced_version_is_recorded_as_forced(self, lending_inputs):
        record = run("lending", "CUST-1", lending_inputs, version="2").record
        assert record.flag_state["forced"] is True


class TestBothRulesetsOneEngine:
    def test_metering_runs_through_the_same_pipeline(self, metering_inputs):
        record = run("metering", "MPAN-1", metering_inputs).record
        assert record.outcome == DecisionRecord.Outcome.DECIDED
        assert record.decision == {"consumption_kwh": 300, "rate": "24.50", "amount": "73.50"}
        assert list(dict.fromkeys(record.stage_outcomes.values_list("stage", flat=True))) == [
            "eligibility",
            "price",
            "amount",
        ]

    def test_metering_refers_into_the_same_queue(self, metering_inputs):
        record = run("metering", "MPAN-2", {**metering_inputs, "current_read": 900}).record
        assert record.exception_case.rule_name == "metering.read_not_below_previous"

    def test_a_zero_charge_is_still_a_decision(self, metering_inputs):
        record = run("metering", "MPAN-3", {**metering_inputs, "current_read": 1000}).record
        assert record.outcome == DecisionRecord.Outcome.DECIDED
        assert record.decision["amount"] == "0.00"
