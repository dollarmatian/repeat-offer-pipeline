from __future__ import annotations

import importlib

from engine.rules import Ruleset


class UnknownRuleset(LookupError):
    pass


class Registry:
    def __init__(self) -> None:
        self._versions: dict[str, dict[str, type[Ruleset]]] = {}
        self._defaults: dict[str, str] = {}

    def load(self, module_path: str) -> None:
        module = importlib.import_module(module_path)
        self.register(module.VERSIONS, default=module.DEFAULT)

    def register(self, versions: tuple[type[Ruleset], ...], *, default: type[Ruleset]) -> None:
        for ruleset in versions:
            ruleset.check()
            self._versions.setdefault(ruleset.name, {})[ruleset.version] = ruleset
        self._defaults[default.name] = default.version

    def clear(self) -> None:
        self._versions.clear()
        self._defaults.clear()

    def names(self) -> list[str]:
        return sorted(self._versions)

    def versions(self, name: str) -> list[str]:
        if name not in self._versions:
            raise UnknownRuleset(name)
        return list(self._versions[name])

    def default_version(self, name: str) -> str:
        if name not in self._defaults:
            raise UnknownRuleset(name)
        return self._defaults[name]

    def get(self, name: str, version: str) -> type[Ruleset]:
        try:
            return self._versions[name][version]
        except KeyError:
            raise UnknownRuleset(f"{name} {version}") from None


registry = Registry()
