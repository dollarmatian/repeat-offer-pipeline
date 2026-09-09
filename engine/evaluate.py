"""Run a ruleset over validated inputs. No database, no clock."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from engine.rules import STAGES, Outcome, Result, Ruleset, Stage

STAGE_CONTRACT = "engine.stage_contract"


@dataclass(frozen=True)
class StageResult:
    position: int
    stage: Stage
    rule_name: str
    outcome: Outcome
    reason: str
    values: Mapping[str, Any] = field(default_factory=dict)
    overridden: bool = False


@dataclass(frozen=True)
class Evaluation:
    outcome: str
    stopped_at: Stage | None
    decision: Mapping[str, Any]
    stages: tuple[StageResult, ...]

    DECIDED = "decided"
    DECLINED = "declined"
    REFERRED = "referred"

    @property
    def referral(self) -> StageResult | None:
        if self.outcome != self.REFERRED:
            return None
        return self.stages[-1]


def evaluate(
    ruleset: type[Ruleset],
    inputs: Mapping[str, Any],
    overrides: Mapping[str, Result] | None = None,
) -> Evaluation:
    overrides = overrides or {}
    decided: dict[str, Any] = {}
    results: list[StageResult] = []
    position = 0

    for stage in STAGES:
        for rule_cls in ruleset.rules_for(stage):
            rule = rule_cls()
            overridden = rule.name in overrides
            result = (
                overrides[rule.name] if overridden else rule.run(inputs, decided, ruleset.config)
            )
            position += 1
            results.append(
                StageResult(
                    position,
                    stage,
                    rule.name,
                    result.outcome,
                    result.reason,
                    result.values,
                    overridden,
                )
            )
            if result.outcome is Outcome.FAIL:
                return Evaluation(Evaluation.DECLINED, stage, decided, tuple(results))
            if result.outcome is Outcome.REFER:
                return Evaluation(Evaluation.REFERRED, stage, decided, tuple(results))
            decided.update(result.values)

        produces = stage.produces
        if produces is not None and produces not in decided:
            position += 1
            supplied = overrides.get(STAGE_CONTRACT)
            if supplied is not None and produces in supplied.values:
                decided[produces] = supplied.values[produces]
                results.append(
                    StageResult(
                        position,
                        stage,
                        STAGE_CONTRACT,
                        Outcome.PASS,
                        supplied.reason,
                        {produces: supplied.values[produces]},
                        overridden=True,
                    )
                )
                continue
            results.append(
                StageResult(
                    position,
                    stage,
                    STAGE_CONTRACT,
                    Outcome.REFER,
                    f"no {stage} rule decided {produces!r}",
                )
            )
            return Evaluation(Evaluation.REFERRED, stage, decided, tuple(results))

    return Evaluation(Evaluation.DECIDED, None, decided, tuple(results))
