import json
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from engine.models import DecisionRecord, RolloutFlag

pytestmark = pytest.mark.django_db


def subjects_file(tmp_path, subjects):
    path = tmp_path / "subjects.json"
    path.write_text(json.dumps(subjects))
    return path


def lending_subject(reference, inputs, **overrides):
    return {
        "subject_reference": reference,
        "inputs": {**{k: str(v) for k, v in inputs.items()}, **overrides},
    }


class TestRunPipeline:
    def test_runs_every_subject_and_is_safe_to_re_run(self, tmp_path, lending_inputs):
        path = subjects_file(
            tmp_path,
            [
                lending_subject("CUST-1", lending_inputs),
                lending_subject("CUST-2", lending_inputs, loans_repaid="0"),
            ],
        )
        out = StringIO()
        call_command("run_pipeline", "lending", str(path), stdout=out)
        assert "2 decided, 0 already decided" in out.getvalue()
        assert DecisionRecord.objects.count() == 2

        out = StringIO()
        call_command("run_pipeline", "lending", str(path), stdout=out)
        assert "0 decided, 2 already decided" in out.getvalue()
        assert DecisionRecord.objects.count() == 2

    def test_one_bad_subject_rolls_back_the_whole_file(self, tmp_path, lending_inputs):
        path = subjects_file(
            tmp_path,
            [
                lending_subject("CUST-1", lending_inputs),
                lending_subject("CUST-2", lending_inputs, loans_repaid="many"),
            ],
        )
        with pytest.raises(CommandError, match="invalid inputs for CUST-2"):
            call_command("run_pipeline", "lending", str(path))
        assert DecisionRecord.objects.count() == 0

    def test_a_forced_version(self, tmp_path, lending_inputs):
        path = subjects_file(tmp_path, [lending_subject("CUST-1", lending_inputs)])
        call_command("run_pipeline", "lending", str(path), ruleset_version="2", stdout=StringIO())
        assert DecisionRecord.objects.get().ruleset_version == "2"

    def test_unknown_ruleset(self, tmp_path):
        path = subjects_file(tmp_path, [])
        with pytest.raises(CommandError, match="unknown ruleset"):
            call_command("run_pipeline", "nothing", str(path), ruleset_version="1")

    def test_the_shipped_examples_run(self):
        out = StringIO()
        call_command("run_pipeline", "lending", "examples/lending.json", stdout=out)
        call_command("run_pipeline", "metering", "examples/metering.json", stdout=out)
        assert DecisionRecord.objects.filter(ruleset_name="lending").count() == 5
        assert DecisionRecord.objects.filter(ruleset_name="metering").count() == 4


class TestSetFlag:
    def test_creates_then_updates(self):
        call_command(
            "set_flag",
            "lending-v2",
            ruleset="lending",
            ruleset_version="2",
            percent=10,
            stdout=StringIO(),
        )
        call_command(
            "set_flag",
            "lending-v2",
            ruleset="lending",
            ruleset_version="2",
            percent=25,
            allow=["CUST-9"],
            stdout=StringIO(),
        )
        flag = RolloutFlag.objects.get(key="lending-v2")
        assert (flag.percent, flag.allowlist, flag.enabled) == (25, ["CUST-9"], True)

    def test_refuses_unknown_version(self):
        with pytest.raises(CommandError):
            call_command("set_flag", "x", ruleset="lending", ruleset_version="9")


def test_list_rules_names_every_stage():
    out = StringIO()
    call_command("list_rules", stdout=out)
    text = out.getvalue()
    assert "lending 1 (default)" in text
    assert "metering.charge_from_consumption" in text
