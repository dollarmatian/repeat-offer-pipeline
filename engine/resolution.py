"""Human resolution of exceptions, written to the same record."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from engine.evaluate import STAGE_CONTRACT, Evaluation, evaluate
from engine.models import DecisionRecord, ExceptionCase, StageOutcome
from engine.pipeline import overrides_from_history, write_stage_outcomes
from engine.registry import registry
from engine.rules import STAGES, Outcome

ACTIONS = ("override", "decline")


class AlreadyResolved(Exception):
    pass


class InvalidResolution(ValueError):
    pass


def coerce_values(values: Mapping[str, Any] | None) -> dict[str, Any]:
    coerced: dict[str, Any] = {}
    for key, value in (values or {}).items():
        if isinstance(value, bool):
            coerced[key] = value
        elif isinstance(value, int | float):
            coerced[key] = Decimal(str(value))
        elif isinstance(value, str):
            try:
                coerced[key] = Decimal(value)
            except InvalidOperation:
                coerced[key] = value
        else:
            coerced[key] = value
    return coerced


def allowed_keys(case: ExceptionCase) -> set[str]:
    ruleset = registry.get(case.record.ruleset_name, case.record.ruleset_version)
    if case.rule_name == STAGE_CONTRACT:
        stage = next(s for s in STAGES if s == case.stage)
        return {stage.produces} if stage.produces else set()
    rule = next(r for r in ruleset.rules if r.name == case.rule_name)
    return set(rule.decides)


def resolve(
    case_id: int,
    *,
    action: str,
    by: str,
    note: str = "",
    values: Mapping[str, Any] | None = None,
) -> ExceptionCase:
    if action not in ACTIONS:
        raise InvalidResolution(f"action must be one of {ACTIONS}")
    if not by:
        raise InvalidResolution("resolved_by is required")

    with transaction.atomic():
        case = ExceptionCase.objects.select_for_update().select_related("record").get(pk=case_id)
        if case.status != ExceptionCase.Status.OPEN:
            raise AlreadyResolved(case_id)
        record = case.record
        values = coerce_values(values)
        stray = set(values) - allowed_keys(case)
        if stray:
            raise InvalidResolution(f"{case.rule_name} cannot decide {sorted(stray)}")

        attempt = (record.stage_outcomes.aggregate(m=Max("attempt"))["m"] or 0) + 1
        case.history = [
            *case.history,
            {
                "at": timezone.now().isoformat(),
                "by": by,
                "action": action,
                "note": note,
                "stage": case.stage,
                "rule_name": case.rule_name,
                "values": values,
            },
        ]

        if action == "decline":
            StageOutcome.objects.create(
                record=record,
                attempt=attempt,
                position=1,
                stage=case.stage,
                rule_name="human.decline",
                outcome=Outcome.FAIL,
                reason=note or f"declined by {by}",
                overridden=True,
            )
            record.outcome = DecisionRecord.Outcome.DECLINED
            record.stopped_at_stage = case.stage
            close(case, by)
        else:
            ruleset = registry.get(record.ruleset_name, record.ruleset_version)
            evaluation = evaluate(
                ruleset, ruleset.validate(record.inputs), overrides_from_history(case.history)
            )
            write_stage_outcomes(record, evaluation, attempt=attempt)
            record.outcome = evaluation.outcome
            record.stopped_at_stage = evaluation.stopped_at or ""
            record.decision = dict(evaluation.decision)
            if evaluation.outcome == Evaluation.REFERRED:
                referral = evaluation.referral
                case.stage = referral.stage
                case.rule_name = referral.rule_name
                case.reason = referral.reason
            else:
                close(case, by)

        record.save(update_fields=["outcome", "stopped_at_stage", "decision"])
        case.save()
    return case


def close(case: ExceptionCase, by: str) -> None:
    case.status = ExceptionCase.Status.RESOLVED
    case.resolved_at = timezone.now()
    case.resolved_by = by
