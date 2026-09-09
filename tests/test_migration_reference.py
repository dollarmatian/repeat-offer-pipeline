"""Migration 0002 changed the public reference. References issued before it still resolve."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from engine.models import DecisionRecord

BEFORE = [("engine", "0001_initial")]
AFTER = [("engine", "0002_decisionrecord_reference")]


@pytest.mark.django_db(transaction=True)
def test_existing_records_are_backfilled_and_still_resolve_by_id():
    executor = MigrationExecutor(connection)
    executor.migrate(BEFORE)
    OldRecord = executor.loader.project_state(BEFORE).apps.get_model("engine", "DecisionRecord")
    old = OldRecord.objects.create(
        ruleset_name="lending",
        ruleset_version="1",
        subject_reference="CUST-1",
        inputs={},
        idempotency_key="k" * 64,
        outcome="decided",
    )
    issued_reference = str(old.id)

    try:
        executor = MigrationExecutor(connection)
        executor.migrate(AFTER)
        executor.loader.build_graph()

        migrated = DecisionRecord.objects.by_reference(issued_reference)
        assert migrated.reference == f"dec_legacy_{old.id}"
        assert DecisionRecord.objects.by_reference(migrated.reference).pk == old.id
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
