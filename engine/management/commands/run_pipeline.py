import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from engine.pipeline import run
from engine.registry import UnknownRuleset, registry
from engine.rules import InvalidInputs


class Command(BaseCommand):
    help = (
        "Run a ruleset over a file of subjects. The whole file runs in one transaction, and "
        "subjects already decided are returned rather than decided again, so it is safe to "
        "re-run."
    )

    def add_arguments(self, parser):
        parser.add_argument("ruleset")
        parser.add_argument("path", type=Path)
        parser.add_argument(
            "--ruleset-version", help="Force a ruleset version instead of using flags"
        )
        parser.add_argument(
            "--enrich",
            action="store_true",
            help="Fetch bureau data for each subject before deciding",
        )

    def handle(self, ruleset, path, ruleset_version, enrich, **options):
        try:
            subjects = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"could not read {path}: {exc}") from None
        if not isinstance(subjects, list):
            raise CommandError("file must hold a JSON list of subjects")

        try:
            registry.get(ruleset, ruleset_version or registry.default_version(ruleset))
        except UnknownRuleset as exc:
            raise CommandError(f"unknown ruleset {exc}") from None

        if enrich:
            from integrations.bureau import client_from_settings, enrich_inputs

            client = client_from_settings()

        created = existing = 0
        try:
            with transaction.atomic():
                for subject in subjects:
                    reference = str(subject["subject_reference"])
                    inputs = dict(subject["inputs"])
                    if enrich:
                        inputs = enrich_inputs(inputs, reference, client)
                    result = run(ruleset, reference, inputs, version=ruleset_version)
                    created += result.created
                    existing += not result.created
                    self.stdout.write(
                        f"{reference:<16} {'new' if result.created else 'existing':<8} "
                        f"{result.record.outcome:<9} {json.dumps(result.record.decision)}"
                    )
        except InvalidInputs as exc:
            raise CommandError(f"invalid inputs for {reference}: {exc}") from None
        except KeyError as exc:
            raise CommandError(
                f"each subject needs subject_reference and inputs (missing {exc})"
            ) from None

        self.stdout.write(self.style.SUCCESS(f"{created} decided, {existing} already decided"))
