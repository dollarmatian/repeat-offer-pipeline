from django.core.serializers.json import DjangoJSONEncoder
from django.db import models


class DecisionRecordQuerySet(models.QuerySet):
    def by_reference(self, reference):
        """Resolve a reference or, for links issued before migration 0002, a numeric id."""
        if reference.isdigit():
            return self.get(pk=int(reference))
        return self.get(reference=reference)


class DecisionRecord(models.Model):
    class Outcome(models.TextChoices):
        DECIDED = "decided"
        DECLINED = "declined"
        REFERRED = "referred"

    reference = models.CharField(max_length=32, unique=True)
    ruleset_name = models.CharField(max_length=64)
    ruleset_version = models.CharField(max_length=32)
    subject_reference = models.CharField(max_length=128)
    inputs = models.JSONField(encoder=DjangoJSONEncoder)
    idempotency_key = models.CharField(max_length=64, unique=True)
    flag_state = models.JSONField(default=dict)
    outcome = models.CharField(max_length=16, choices=Outcome.choices)
    stopped_at_stage = models.CharField(max_length=16, blank=True, default="")
    decision = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = DecisionRecordQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(
                fields=["ruleset_name", "ruleset_version", "outcome"], name="record_ruleset_outcome"
            ),
            models.Index(fields=["subject_reference"], name="record_subject"),
            models.Index(fields=["created_at"], name="record_created"),
        ]

    def __str__(self):
        return f"{self.reference} {self.ruleset_name}/{self.ruleset_version} {self.outcome}"


class StageOutcome(models.Model):
    """One rule's result in one run. Attempt 1 is automatic; later attempts follow a human
    override."""

    record = models.ForeignKey(
        DecisionRecord, on_delete=models.CASCADE, related_name="stage_outcomes"
    )
    attempt = models.PositiveSmallIntegerField(default=1)
    position = models.PositiveSmallIntegerField()
    stage = models.CharField(max_length=16)
    rule_name = models.CharField(max_length=128)
    outcome = models.CharField(max_length=8)
    reason = models.TextField()
    values = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    overridden = models.BooleanField(default=False)

    class Meta:
        ordering = ["attempt", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["record", "attempt", "position"], name="stage_outcome_position"
            )
        ]
        indexes = [models.Index(fields=["stage", "outcome"], name="stage_outcome_stage")]


class ExceptionCase(models.Model):
    class Status(models.TextChoices):
        OPEN = "open"
        RESOLVED = "resolved"

    record = models.OneToOneField(
        DecisionRecord, on_delete=models.CASCADE, related_name="exception_case"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    stage = models.CharField(max_length=16)
    rule_name = models.CharField(max_length=128)
    reason = models.TextField()
    history = models.JSONField(default=list, encoder=DjangoJSONEncoder)
    opened_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.CharField(max_length=128, blank=True, default="")

    class Meta:
        ordering = ["opened_at", "id"]
        indexes = [models.Index(fields=["status", "opened_at"], name="exception_status")]


class RolloutFlag(models.Model):
    """Routes subjects on the allowlist, or under `percent` by bucket, to a ruleset version.
    `retire_by` is the date the flag is meant to be deleted."""

    key = models.CharField(max_length=64, unique=True)
    ruleset_name = models.CharField(max_length=64)
    version = models.CharField(max_length=32)
    percent = models.PositiveSmallIntegerField(default=0)
    allowlist = models.JSONField(default=list)
    enabled = models.BooleanField(default=True)
    retire_by = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.key} -> {self.ruleset_name}/{self.version} ({self.percent}%)"
