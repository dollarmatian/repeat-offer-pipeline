import json

import pytest

from engine.models import DecisionRecord
from engine.pipeline import run

pytestmark = pytest.mark.django_db


def post(api, url, payload):
    return api.post(url, data=json.dumps(payload), content_type="application/json")


def lending_payload(lending_inputs, **overrides):
    return {
        "ruleset": "lending",
        "subject_reference": "CUST-1",
        "inputs": {**{k: str(v) for k, v in lending_inputs.items()}, **overrides},
    }


class TestDecisions:
    def test_post_runs_the_pipeline_and_returns_the_record(self, api, lending_inputs):
        response = post(api, "/api/decisions/", lending_payload(lending_inputs))
        assert response.status_code == 201
        body = response.json()
        assert body["created"] is True
        assert body["decision"]["outcome"] == "decided"
        assert body["decision"]["decision"] == {"rate": "0.019", "amount": "20000"}
        assert len(body["decision"]["stages"]) == 8

    def test_posting_the_same_inputs_again_is_a_200_not_a_second_record(self, api, lending_inputs):
        post(api, "/api/decisions/", lending_payload(lending_inputs))
        response = post(api, "/api/decisions/", lending_payload(lending_inputs))
        assert response.status_code == 200
        assert response.json()["created"] is False
        assert DecisionRecord.objects.count() == 1

    def test_invalid_inputs_are_a_400_with_details_and_no_record(self, api, lending_inputs):
        response = post(
            api, "/api/decisions/", lending_payload(lending_inputs, loans_repaid="lots")
        )
        assert response.status_code == 400
        assert response.json()["details"] == {"loans_repaid": "must be an integer"}
        assert DecisionRecord.objects.count() == 0

    def test_unknown_ruleset_is_a_404(self, api, lending_inputs):
        payload = {**lending_payload(lending_inputs), "ruleset": "insurance"}
        assert post(api, "/api/decisions/", payload).status_code == 404

    def test_a_record_is_readable_by_reference_and_by_legacy_id(self, api, lending_inputs):
        record = run("lending", "CUST-1", lending_inputs).record
        by_reference = api.get(f"/api/decisions/{record.reference}/")
        by_id = api.get(f"/api/decisions/{record.id}/")
        assert by_reference.status_code == by_id.status_code == 200
        assert by_reference.json()["reference"] == by_id.json()["reference"]

    def test_missing_record_is_a_404(self, api):
        assert api.get("/api/decisions/dec_nothing/").status_code == 404

    def test_non_json_body_is_a_400(self, api):
        response = api.post("/api/decisions/", data="nope", content_type="application/json")
        assert response.status_code == 400


class TestExceptions:
    @pytest.fixture
    def referred(self, lending_inputs):
        return run("lending", "CUST-3", {**lending_inputs, "missed_payments_last_12m": 1}).record

    def test_open_exceptions_are_listed_by_default(self, api, referred, lending_inputs):
        run("lending", "CUST-1", lending_inputs)
        body = api.get("/api/exceptions/").json()
        assert [e["decision_reference"] for e in body["exceptions"]] == [referred.reference]
        assert body["exceptions"][0]["rule"] == "lending.missed_payments"

    def test_detail_includes_the_decision_record(self, api, referred):
        body = api.get(f"/api/exceptions/{referred.exception_case.id}/").json()
        assert body["record"]["reference"] == referred.reference
        assert body["record"]["stages"][-1]["outcome"] == "refer"

    def test_resolve_writes_to_the_record(self, api, referred):
        case_id = referred.exception_case.id
        response = post(
            api,
            f"/api/exceptions/{case_id}/resolve/",
            {"action": "override", "resolved_by": "ops", "note": "fine"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "resolved"
        assert body["record"]["outcome"] == "decided"
        assert api.get("/api/exceptions/").json()["exceptions"] == []
        assert len(api.get("/api/exceptions/?status=resolved").json()["exceptions"]) == 1

    def test_resolving_twice_is_a_409(self, api, referred):
        case_id = referred.exception_case.id
        payload = {"action": "decline", "resolved_by": "ops"}
        post(api, f"/api/exceptions/{case_id}/resolve/", payload)
        assert post(api, f"/api/exceptions/{case_id}/resolve/", payload).status_code == 409

    def test_bad_resolution_is_a_400(self, api, referred):
        case_id = referred.exception_case.id
        response = post(
            api, f"/api/exceptions/{case_id}/resolve/", {"action": "shrug", "resolved_by": "x"}
        )
        assert response.status_code == 400

    def test_missing_exception_is_a_404(self, api):
        assert api.get("/api/exceptions/999/").status_code == 404
        assert (
            post(
                api, "/api/exceptions/999/resolve/", {"action": "decline", "resolved_by": "x"}
            ).status_code
            == 404
        )


class TestRulesetsAndHealth:
    def test_rulesets_are_listed_with_their_rules(self, api):
        body = api.get("/api/rulesets/").json()
        names = {r["name"]: r for r in body["rulesets"]}
        assert set(names) == {"lending", "metering"}
        assert names["lending"]["default_version"] == "1"
        v2 = next(v for v in names["lending"]["versions"] if v["version"] == "2")
        assert [r["name"] for r in v2["stages"]["eligibility"]][-1] == "lending.bureau_score"

    def test_health(self, api):
        assert api.get("/api/health/").json() == {"status": "ok"}
