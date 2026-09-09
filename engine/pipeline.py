"""validate -> decide -> record, atomically."""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.db import IntegrityError, transaction

from engine import flags
from engine.evaluate import Evaluation, evaluate
from engine.models import DecisionRecord, ExceptionCase, StageOutcome
from engine.registry import registry
from engine.rules import Result


@dataclass(frozen=True)
class RunResult:
    record: DecisionRecord
    created: bool


def canonical(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, Mapping):
        return {k: canonical(v) for k, v in sorted(value.items())}
    if isinstance(value, list | tuple):
        return [canonical(v) for v in value]
    return value


def idempotency_key(ruleset_name: str, version: str, inputs: Mapping[str, Any]) -> str:
    payload = json.dumps(
        {"ruleset": ruleset_name, "version": version, "inputs": canonical(inputs)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def new_reference() -> str:
    return "dec_" + secrets.token_hex(8)


def run(
    ruleset_name: str,
    subject_reference: str,
    inputs: Mapping[str, Any],
    *,
    version: str | None = None,
) -> RunResult:
    """Decide once. The same inputs under the same version return the existing record."""
    if version is None:
        version, flag_state = flags.resolve(ruleset_name, subject_reference)
    else:
        flag_state = {"flag": None, "matched": False, "forced": True, "version": version}
    ruleset = registry.get(ruleset_name, version)
    validated = ruleset.validate(inputs)
    key = idempotency_key(ruleset_name, version, validated)

    existing = DecisionRecord.objects.filter(idempotency_key=key).first()
    if existing is not None:
        return RunResult(existing, created=False)

    evaluation = evaluate(ruleset, validated)
    try:
        with transaction.atomic():
            record = DecisionRecord.objects.create(
                reference=new_reference(),
                ruleset_name=ruleset_name,
                ruleset_version=version,
                subject_reference=subject_reference,
                inputs=validated,
                idempotency_key=key,
                flag_state=flag_state,
                outcome=evaluation.outcome,
                stopped_at_stage=evaluation.stopped_at or "",
                decision=dict(evaluation.decision),
            )
            write_stage_outcomes(record, evaluation, attempt=1)
            if evaluation.outcome == Evaluation.REFERRED:
                referral = evaluation.referral
                ExceptionCase.objects.create(
                    record=record,
                    stage=referral.stage,
                    rule_name=referral.rule_name,
                    reason=referral.reason,
                )
    except IntegrityError:
        return RunResult(DecisionRecord.objects.get(idempotency_key=key), created=False)
    record.refresh_from_db()
    return RunResult(record, created=True)


def write_stage_outcomes(record: DecisionRecord, evaluation: Evaluation, *, attempt: int) -> None:
    StageOutcome.objects.bulk_create(
        StageOutcome(
            record=record,
            attempt=attempt,
            position=stage.position,
            stage=stage.stage,
            rule_name=stage.rule_name,
            outcome=stage.outcome,
            reason=stage.reason,
            values=dict(stage.values),
            overridden=stage.overridden,
        )
        for stage in evaluation.stages
    )


def overrides_from_history(history: list[dict]) -> dict[str, Result]:
    from engine.rules import Outcome

    overrides: dict[str, Result] = {}
    for entry in history:
        if entry["action"] == "override":
            overrides[entry["rule_name"]] = Result(
                Outcome.PASS,
                f"overridden by {entry['by']}: {entry['note']}".rstrip(": "),
                entry.get("values") or {},
            )
    return overrides
