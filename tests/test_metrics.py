from decimal import Decimal

import pytest

from engine import metrics
from engine.models import RolloutFlag
from engine.pipeline import run

pytestmark = pytest.mark.django_db


@pytest.fixture
def some_runs(lending_inputs, metering_inputs):
    run("lending", "CUST-1", lending_inputs)
    run("lending", "CUST-2", {**lending_inputs, "loans_repaid": 0})
    run("lending", "CUST-3", {**lending_inputs, "missed_payments_last_12m": 1})
    run("lending", "CUST-4", lending_inputs, version="2")
    run("metering", "MPAN-1", metering_inputs)


class TestCounts:
    def test_by_outcome_stage_and_ruleset(self, some_runs):
        data = metrics.counts()
        assert data["total"] == 5
        assert data["by_outcome"] == {"decided": 2, "declined": 1, "referred": 2}
        assert data["by_ruleset"] == {
            "lending": {"1": {"decided": 1, "declined": 1, "referred": 1}, "2": {"referred": 1}},
            "metering": {"1": {"decided": 1}},
        }
        assert data["by_stage"]["eligibility"] == {"pass": 11, "fail": 1, "refer": 2}
        assert data["exceptions"] == {"open": 2}

    def test_filtered_to_one_ruleset(self, some_runs):
        data = metrics.counts(ruleset_name="metering")
        assert data["total"] == 1
        assert list(data["by_ruleset"]) == ["metering"]

    def test_endpoint(self, api, some_runs):
        response = api.get("/api/metrics/?ruleset=lending")
        assert response.status_code == 200
        assert response.json()["total"] == 4
        assert api.get("/api/metrics/?since=yesterday").status_code == 400
        assert api.get("/api/metrics/?since=2999-01-01T00:00:00Z").json()["total"] == 0

    def test_a_flagged_version_can_be_compared_with_the_one_it_replaces(self, lending_inputs):
        RolloutFlag.objects.create(key="v2", ruleset_name="lending", version="2", percent=50)
        for n in range(30):
            inputs = {**lending_inputs, "requested_amount": Decimal("60000")}
            run("lending", f"CUST-{n}", inputs)
        by_version = metrics.counts(ruleset_name="lending")["by_ruleset"]["lending"]
        assert set(by_version) == {"1", "2"}
        assert by_version["1"] == {"decided": by_version["1"]["decided"]}
        assert by_version["2"] == {"referred": by_version["2"]["referred"]}
