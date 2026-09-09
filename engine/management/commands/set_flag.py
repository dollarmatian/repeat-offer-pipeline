from datetime import date

from django.core.management.base import BaseCommand, CommandError

from engine.models import RolloutFlag
from engine.registry import UnknownRuleset, registry


class Command(BaseCommand):
    help = "Create or update a rollout flag that routes a subset of subjects to a ruleset version."

    def add_arguments(self, parser):
        parser.add_argument("key")
        parser.add_argument("--ruleset", required=True)
        parser.add_argument("--ruleset-version", required=True)
        parser.add_argument("--percent", type=int, default=0)
        parser.add_argument("--allow", action="append", default=[], metavar="SUBJECT")
        parser.add_argument("--retire-by", type=date.fromisoformat)
        parser.add_argument("--disable", action="store_true")

    def handle(self, key, ruleset, ruleset_version, percent, allow, retire_by, disable, **options):
        try:
            registry.get(ruleset, ruleset_version)
        except UnknownRuleset:
            raise CommandError(f"no ruleset {ruleset} version {ruleset_version}") from None
        if not 0 <= percent <= 100:
            raise CommandError("percent must be between 0 and 100")
        flag, created = RolloutFlag.objects.update_or_create(
            key=key,
            defaults={
                "ruleset_name": ruleset,
                "version": ruleset_version,
                "percent": percent,
                "allowlist": allow,
                "enabled": not disable,
                "retire_by": retire_by,
            },
        )
        self.stdout.write(self.style.SUCCESS(f"{'created' if created else 'updated'} {flag}"))
