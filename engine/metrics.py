from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from django.db.models import Count

from engine.models import DecisionRecord, ExceptionCase, StageOutcome


def counts(*, ruleset_name: str | None = None, since: datetime | None = None) -> dict:
    """Counts by outcome, by stage and by ruleset version."""
    records = DecisionRecord.objects.all()
    if ruleset_name:
        records = records.filter(ruleset_name=ruleset_name)
    if since:
        records = records.filter(created_at__gte=since)

    by_outcome = {
        row["outcome"]: row["n"]
        for row in records.values("outcome").annotate(n=Count("id")).order_by("outcome")
    }

    by_ruleset: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(dict))
    for row in (
        records.values("ruleset_name", "ruleset_version", "outcome")
        .annotate(n=Count("id"))
        .order_by("ruleset_name", "ruleset_version", "outcome")
    ):
        by_ruleset[row["ruleset_name"]][row["ruleset_version"]][row["outcome"]] = row["n"]

    by_stage: dict[str, dict[str, int]] = defaultdict(dict)
    for row in (
        StageOutcome.objects.filter(record__in=records, attempt=1)
        .values("stage", "outcome")
        .annotate(n=Count("id"))
        .order_by("stage", "outcome")
    ):
        by_stage[row["stage"]][row["outcome"]] = row["n"]

    exceptions = {
        row["status"]: row["n"]
        for row in ExceptionCase.objects.filter(record__in=records)
        .values("status")
        .annotate(n=Count("id"))
        .order_by("status")
    }

    return {
        "total": sum(by_outcome.values()),
        "by_outcome": by_outcome,
        "by_stage": {k: dict(v) for k, v in by_stage.items()},
        "by_ruleset": {k: {vk: dict(vv) for vk, vv in v.items()} for k, v in by_ruleset.items()},
        "exceptions": exceptions,
    }
