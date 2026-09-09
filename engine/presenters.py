from engine.models import DecisionRecord, ExceptionCase, StageOutcome


def stage_outcome(outcome: StageOutcome) -> dict:
    return {
        "attempt": outcome.attempt,
        "position": outcome.position,
        "stage": outcome.stage,
        "rule": outcome.rule_name,
        "outcome": outcome.outcome,
        "reason": outcome.reason,
        "values": outcome.values,
        "overridden": outcome.overridden,
    }


def record(rec: DecisionRecord) -> dict:
    return {
        "reference": rec.reference,
        "id": rec.id,
        "ruleset": rec.ruleset_name,
        "version": rec.ruleset_version,
        "subject_reference": rec.subject_reference,
        "inputs": rec.inputs,
        "flag_state": rec.flag_state,
        "outcome": rec.outcome,
        "stopped_at_stage": rec.stopped_at_stage or None,
        "decision": rec.decision,
        "stages": [stage_outcome(s) for s in rec.stage_outcomes.all()],
        "created_at": rec.created_at.isoformat(),
    }


def case(exc: ExceptionCase, *, with_record: bool = False) -> dict:
    data = {
        "id": exc.id,
        "status": exc.status,
        "stage": exc.stage,
        "rule": exc.rule_name,
        "reason": exc.reason,
        "decision_reference": exc.record.reference,
        "subject_reference": exc.record.subject_reference,
        "ruleset": exc.record.ruleset_name,
        "version": exc.record.ruleset_version,
        "history": exc.history,
        "opened_at": exc.opened_at.isoformat(),
        "resolved_at": exc.resolved_at.isoformat() if exc.resolved_at else None,
        "resolved_by": exc.resolved_by or None,
    }
    if with_record:
        data["record"] = record(exc.record)
    return data
