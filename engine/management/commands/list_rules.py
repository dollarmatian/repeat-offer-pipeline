from django.core.management.base import BaseCommand

from engine.registry import registry
from engine.rules import STAGES


class Command(BaseCommand):
    help = "List every registered ruleset version and the rules in each stage, in run order."

    def handle(self, **options):
        for name in registry.names():
            default = registry.default_version(name)
            for version in registry.versions(name):
                ruleset = registry.get(name, version)
                marker = " (default)" if version == default else ""
                self.stdout.write(self.style.MIGRATE_HEADING(f"{name} {version}{marker}"))
                for stage in STAGES:
                    self.stdout.write(f"  {stage}")
                    for rule in ruleset.rules_for(stage):
                        decides = f" -> {', '.join(rule.decides)}" if rule.decides else ""
                        self.stdout.write(
                            f"    {rule.name:<40} reads {', '.join(rule.requires) or '-'}{decides}"
                        )
