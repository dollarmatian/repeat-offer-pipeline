from decimal import Decimal

import pytest

from engine import resolution
from engine.evaluate import STAGE_CONTRACT
from engine.models import DecisionRecord, ExceptionCase
from engine.pipeline import run

pytestmark = pytest.mark.django_db


@pytest.fixture
def referred(lending_inputs):
    return run("lending", "CUST-3", {**lending_inputs, "missed_payments_last_12m": 1}).record


class TestOverride:
    def test_overriding_the_referring_rule_finishes_the_run_on_the_same_record(self, referred):
        case = resolution.resolve(
            referred.exception_case.id, action="override", by="ops@example", note="spoke to them"
        )
        record = DecisionRecord.objects.get(pk=referred.pk)
        assert case.status == ExceptionCase.Status.RESOLVED
        assert case.resolved_by == "ops@example"
        assert record.outcome == DecisionRecord.Outcome.DECIDED
        assert record.decision == {"rate": "0.019", "amount": "20000"}

        attempts = sorted(set(record.stage_outcomes.values_list("attempt", flat=True)))
        assert attempts == [1, 2]
        second = record.stage_outcomes.filter(attempt=2)
        overridden = second.get(rule_name="lending.missed_payments")
        assert overridden.overridden is True
        assert "ops@example" in overridden.reason
        assert second.count() == 8

    def test_the_first_attempt_is_kept(self, referred):
        resolution.resolve(referred.exception_case.id, action="override", by="ops")
        first = referred.stage_outcomes.filter(attempt=1)
        assert list(first.values_list("outcome", flat=True)) == ["pass", "refer"]

    def test_history_records_who_did_what(self, referred):
        case = resolution.resolve(
            referred.exception_case.id, action="override", by="ops", note="ok"
        )
        assert len(case.history) == 1
        assert case.history[0]["by"] == "ops"
        assert case.history[0]["action"] == "override"
        assert case.history[0]["rule_name"] == "lending.missed_payments"

    def test_a_second_referral_keeps_the_case_open_with_the_new_reason(self, metering_inputs):
        record = run(
            "metering", "MPAN-9", {**metering_inputs, "current_read": 900, "tariff_code": "legacy"}
        ).record
        case = record.exception_case
        assert case.rule_name == "metering.read_not_below_previous"
        case = resolution.resolve(
            case.id,
            action="override",
            by="ops",
            note="rollover confirmed",
            values={"consumption_kwh": 200},
        )
        assert case.status == ExceptionCase.Status.OPEN
        assert case.rule_name == "metering.unit_rate"
        assert case.stage == "price"

    def test_a_deciding_rule_can_be_overridden_with_a_value(self, metering_inputs):
        record = run("metering", "MPAN-9", {**metering_inputs, "tariff_code": "legacy"}).record
        case = resolution.resolve(
            record.exception_case.id, action="override", by="ops", values={"rate": "30.00"}
        )
        record.refresh_from_db()
        assert case.status == ExceptionCase.Status.RESOLVED
        assert record.decision["rate"] == "30.00"
        assert record.decision["amount"] == "90.00"

    def test_both_overrides_are_applied_on_the_second_pass(self, metering_inputs):
        record = run(
            "metering", "MPAN-9", {**metering_inputs, "current_read": 900, "tariff_code": "legacy"}
        ).record
        case = resolution.resolve(
            record.exception_case.id, action="override", by="ops", values={"consumption_kwh": 150}
        )
        assert case.rule_name == "metering.unit_rate"
        case = resolution.resolve(case.id, action="override", by="ops", values={"rate": 10})
        record.refresh_from_db()
        assert case.status == ExceptionCase.Status.RESOLVED
        assert record.outcome == DecisionRecord.Outcome.DECIDED
        assert record.decision == {"consumption_kwh": "150", "rate": "10", "amount": "15.00"}

    def test_a_confirmed_rollover_needs_the_consumption_stated(self, metering_inputs):
        record = run("metering", "MPAN-9", {**metering_inputs, "current_read": 900}).record
        case = resolution.resolve(
            record.exception_case.id, action="override", by="ops", note="rollover confirmed"
        )
        assert case.status == ExceptionCase.Status.OPEN
        assert case.rule_name == "metering.consumption_plausible"

    def test_overriding_a_deciding_rule_without_a_value_refers_to_the_stage_contract(
        self, metering_inputs
    ):
        record = run("metering", "MPAN-9", {**metering_inputs, "tariff_code": "legacy"}).record
        case = resolution.resolve(record.exception_case.id, action="override", by="ops")
        assert case.status == ExceptionCase.Status.OPEN
        assert case.rule_name == STAGE_CONTRACT
        assert case.reason == "no price rule decided 'rate'"
        case = resolution.resolve(case.id, action="override", by="ops", values={"rate": "20"})
        record.refresh_from_db()
        assert case.status == ExceptionCase.Status.RESOLVED
        assert record.decision == {"consumption_kwh": 300, "rate": "20", "amount": "60.00"}
        contract = record.stage_outcomes.get(attempt=3, rule_name=STAGE_CONTRACT)
        assert contract.overridden is True
        assert contract.values == {"rate": "20"}

    def test_values_outside_the_rules_declared_shape_are_rejected(self, referred):
        with pytest.raises(resolution.InvalidResolution, match="cannot decide"):
            resolution.resolve(
                referred.exception_case.id, action="override", by="ops", values={"amount": 1}
            )
        assert referred.exception_case.status == ExceptionCase.Status.OPEN


class TestDecline:
    def test_a_human_decline_is_written_like_any_other(self, referred):
        case = resolution.resolve(
            referred.exception_case.id, action="decline", by="ops", note="not this time"
        )
        record = DecisionRecord.objects.get(pk=referred.pk)
        assert case.status == ExceptionCase.Status.RESOLVED
        assert record.outcome == DecisionRecord.Outcome.DECLINED
        last = record.stage_outcomes.last()
        assert (last.attempt, last.rule_name, last.outcome, last.reason) == (
            2,
            "human.decline",
            "fail",
            "not this time",
        )


class TestGuards:
    def test_resolving_twice_is_refused(self, referred):
        resolution.resolve(referred.exception_case.id, action="decline", by="ops")
        with pytest.raises(resolution.AlreadyResolved):
            resolution.resolve(referred.exception_case.id, action="decline", by="ops")

    def test_a_resolver_must_be_named(self, referred):
        with pytest.raises(resolution.InvalidResolution):
            resolution.resolve(referred.exception_case.id, action="decline", by="")

    def test_unknown_actions_are_refused(self, referred):
        with pytest.raises(resolution.InvalidResolution):
            resolution.resolve(referred.exception_case.id, action="approve", by="ops")

    def test_values_are_coerced_to_decimal(self):
        assert resolution.coerce_values({"rate": 0.03, "note": "x"}) == {
            "rate": Decimal("0.03"),
            "note": "x",
        }
