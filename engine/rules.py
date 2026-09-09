"""Rules and rulesets: classes with a declared shape, held to it at run time."""

from __future__ import annotations

import enum
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any, ClassVar


class Stage(enum.StrEnum):
    ELIGIBILITY = "eligibility"
    PRICE = "price"
    AMOUNT = "amount"

    @property
    def produces(self) -> str | None:
        """The decision key a stage must have settled before the next one runs."""
        return {Stage.PRICE: "rate", Stage.AMOUNT: "amount"}.get(self)


STAGES: tuple[Stage, ...] = (Stage.ELIGIBILITY, Stage.PRICE, Stage.AMOUNT)


class Outcome(enum.StrEnum):
    PASS = "pass"
    FAIL = "fail"
    REFER = "refer"


@dataclass(frozen=True)
class Result:
    outcome: Outcome
    reason: str
    values: Mapping[str, Any] = field(default_factory=dict)


class RuleError(Exception):
    """A rule broke its declared shape."""


class UndeclaredInput(RuleError, LookupError):
    pass


class UndeclaredDecision(RuleError):
    pass


class DeclaredInputs(Mapping[str, Any]):
    """A view of the inputs restricted to what one rule declared it needs."""

    def __init__(self, inputs: Mapping[str, Any], allowed: tuple[str, ...], rule_name: str):
        self._inputs = inputs
        self._allowed = allowed
        self._rule_name = rule_name

    def __getitem__(self, key: str) -> Any:
        if key not in self._allowed:
            raise UndeclaredInput(f"{self._rule_name} reads {key!r} but does not declare it")
        return self._inputs[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._allowed)

    def __len__(self) -> int:
        return len(self._allowed)


@dataclass(frozen=True)
class Context:
    inputs: Mapping[str, Any]
    decided: Mapping[str, Any]
    config: Mapping[str, Any]


class Rule:
    name: ClassVar[str]
    stage: ClassVar[Stage]
    description: ClassVar[str] = ""
    requires: ClassVar[tuple[str, ...]] = ()
    decides: ClassVar[tuple[str, ...]] = ()

    def evaluate(self, ctx: Context) -> Result:
        raise NotImplementedError

    def passes(self, reason: str, **values: Any) -> Result:
        return Result(Outcome.PASS, reason, values)

    def fails(self, reason: str) -> Result:
        return Result(Outcome.FAIL, reason)

    def refers(self, reason: str) -> Result:
        return Result(Outcome.REFER, reason)

    def run(
        self, inputs: Mapping[str, Any], decided: Mapping[str, Any], config: Mapping[str, Any]
    ) -> Result:
        ctx = Context(
            inputs=DeclaredInputs(inputs, self.requires, self.name),
            decided=MappingProxyType(dict(decided)),
            config=MappingProxyType(dict(config)),
        )
        result = self.evaluate(ctx)
        undeclared = set(result.values) - set(self.decides)
        if undeclared:
            raise UndeclaredDecision(
                f"{self.name} decided {sorted(undeclared)} but only declares {list(self.decides)}"
            )
        return result

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {
            "name": cls.name,
            "stage": str(cls.stage),
            "description": cls.description,
            "requires": list(cls.requires),
            "decides": list(cls.decides),
        }


@dataclass(frozen=True)
class Input:
    name: str
    type: type
    required: bool = True
    description: str = ""

    def coerce(self, value: Any) -> Any:
        if value is None:
            if self.required:
                raise ValueError("is required")
            return None
        if self.type is bool:
            if isinstance(value, bool):
                return value
            raise ValueError("must be a boolean")
        if self.type is int:
            if isinstance(value, bool):
                raise ValueError("must be an integer")
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.strip().lstrip("-").isdigit():
                return int(value)
            raise ValueError("must be an integer")
        if self.type is Decimal:
            if isinstance(value, bool):
                raise ValueError("must be a number")
            if isinstance(value, Decimal):
                return value
            if isinstance(value, int | float | str):
                try:
                    return Decimal(str(value))
                except InvalidOperation:
                    raise ValueError("must be a number") from None
            raise ValueError("must be a number")
        if self.type is str:
            if isinstance(value, str):
                return value
            raise ValueError("must be a string")
        raise TypeError(f"unsupported input type {self.type!r}")

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type.__name__,
            "required": self.required,
            "description": self.description,
        }


class InvalidInputs(ValueError):
    def __init__(self, errors: Mapping[str, str]):
        self.errors = dict(errors)
        super().__init__("; ".join(f"{k}: {v}" for k, v in self.errors.items()))


class RulesetError(Exception):
    """Raised at registration when a ruleset is declared inconsistently."""


class Ruleset:
    name: ClassVar[str]
    version: ClassVar[str]
    description: ClassVar[str] = ""
    inputs: ClassVar[tuple[Input, ...]] = ()
    rules: ClassVar[tuple[type[Rule], ...]] = ()
    config: ClassVar[Mapping[str, Any]] = MappingProxyType({})

    @classmethod
    def rules_for(cls, stage: Stage) -> tuple[type[Rule], ...]:
        return tuple(rule for rule in cls.rules if rule.stage is stage)

    @classmethod
    def validate(cls, raw: Mapping[str, Any]) -> dict[str, Any]:
        errors: dict[str, str] = {}
        declared = {spec.name for spec in cls.inputs}
        for key in raw:
            if key not in declared:
                errors[key] = "is not a declared input"
        validated: dict[str, Any] = {}
        for spec in cls.inputs:
            try:
                validated[spec.name] = spec.coerce(raw.get(spec.name))
            except ValueError as exc:
                errors[spec.name] = str(exc)
        if errors:
            raise InvalidInputs(errors)
        return validated

    @classmethod
    def check(cls) -> None:
        declared = {spec.name for spec in cls.inputs}
        names = [rule.name for rule in cls.rules]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise RulesetError(
                f"{cls.name} {cls.version}: duplicate rule names {sorted(duplicates)}"
            )
        for rule in cls.rules:
            missing = set(rule.requires) - declared
            if missing:
                raise RulesetError(
                    f"{cls.name} {cls.version}: {rule.name} requires undeclared inputs "
                    f"{sorted(missing)}"
                )
        for stage in STAGES:
            if stage.produces is None:
                continue
            deciders = [r for r in cls.rules_for(stage) if stage.produces in r.decides]
            if not deciders:
                raise RulesetError(
                    f"{cls.name} {cls.version}: no {stage} rule decides {stage.produces!r}"
                )

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.description,
            "inputs": [spec.describe() for spec in cls.inputs],
            "stages": {
                str(stage): [rule.describe() for rule in cls.rules_for(stage)] for stage in STAGES
            },
            "config": {k: str(v) for k, v in cls.config.items()},
        }
