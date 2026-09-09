import hashlib

from engine.models import RolloutFlag
from engine.registry import registry


def bucket(ruleset_name: str, subject_reference: str) -> int:
    digest = hashlib.sha256(f"{ruleset_name}:{subject_reference}".encode()).hexdigest()
    return int(digest, 16) % 100


def resolve(ruleset_name: str, subject_reference: str) -> tuple[str, dict]:
    """Pick the ruleset version for a subject, and the flag state that chose it."""
    default = registry.default_version(ruleset_name)
    b = bucket(ruleset_name, subject_reference)
    for flag in RolloutFlag.objects.filter(ruleset_name=ruleset_name, enabled=True):
        listed = subject_reference in flag.allowlist
        if listed or b < flag.percent:
            return flag.version, {
                "flag": flag.key,
                "matched": True,
                "listed": listed,
                "bucket": b,
                "version": flag.version,
            }
    return default, {"flag": None, "matched": False, "bucket": b, "version": default}
