"""The external integration: timeout, retry, partial failure, bad data."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from integrations.bureau import BureauClient, enrich_inputs


class ScriptedTransport:
    """Plays back a list of responses, or raises when an entry is an exception."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def __call__(self, url, timeout):
        self.calls.append((url, timeout))
        step = self.script.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step


def client(script, **kwargs):
    transport = ScriptedTransport(script)
    return BureauClient(
        "http://bureau.test", transport=transport, sleep=lambda s: None, **kwargs
    ), transport


def ok(score=612, **extra):
    return 200, json.dumps({"reference": "CUST-1", "score": score, **extra}).encode()


class TestHappyPath:
    def test_a_good_response_is_a_score(self):
        bureau, transport = client([ok()])
        report = bureau.fetch("CUST-1")
        assert report.available
        assert report.score == 612
        assert report.attempts == 1
        assert transport.calls == [("http://bureau.test/subjects/CUST-1", 2.0)]


class TestTimeoutsAndRetries:
    def test_a_timeout_is_retried_then_reported(self):
        bureau, transport = client([TimeoutError(), TimeoutError(), TimeoutError()], retries=2)
        report = bureau.fetch("CUST-1")
        assert not report.available
        assert report.attempts == 3
        assert report.status == "unavailable after 3 attempts: timeout"

    def test_a_timeout_followed_by_success_is_a_score(self):
        bureau, _ = client([TimeoutError(), ok(500)])
        report = bureau.fetch("CUST-1")
        assert report.score == 500
        assert report.attempts == 2

    def test_server_errors_are_retried(self):
        bureau, _ = client([(503, b""), (502, b""), ok(450)])
        assert bureau.fetch("CUST-1").score == 450

    def test_client_errors_are_not_retried(self):
        bureau, transport = client([(404, b"")])
        report = bureau.fetch("CUST-1")
        assert report.status == "http 404"
        assert len(transport.calls) == 1

    def test_backoff_grows_between_attempts(self):
        waits = []
        transport = ScriptedTransport([(500, b""), (500, b""), ok()])
        bureau = BureauClient("http://b", transport=transport, sleep=waits.append, backoff=0.1)
        bureau.fetch("CUST-1")
        assert waits == [pytest.approx(0.1), pytest.approx(0.2)]


class TestPartialFailure:
    def test_a_response_without_a_score_is_partial(self):
        bureau, _ = client([(200, json.dumps({"reference": "CUST-1", "name": "x"}).encode())])
        report = bureau.fetch("CUST-1")
        assert not report.available
        assert report.status == "partial: no score in response"
        assert report.missing == ("score",)


class TestBadData:
    @pytest.mark.parametrize(
        "body, status",
        [
            (b"<html>gateway</html>", "bad data: not json"),
            (b"[1, 2]", "bad data: not an object"),
            (b'{"reference": "CUST-2", "score": 500}', "bad data: reference mismatch"),
            (b'{"score": "high"}', "bad data: score 'high'"),
            (b'{"score": 5000}', "bad data: score 5000"),
            (b'{"score": true}', "bad data: score True"),
        ],
    )
    def test_malformed_bodies_do_not_raise(self, body, status):
        bureau, _ = client([(200, body)])
        report = bureau.fetch("CUST-1")
        assert not report.available
        assert report.status == status


class TestEnrichment:
    def test_inputs_gain_a_score_and_a_status(self):
        bureau, _ = client([ok(700)])
        enriched = enrich_inputs({"loans_repaid": 1}, "CUST-1", bureau)
        assert enriched == {"loans_repaid": 1, "bureau_score": 700, "bureau_status": "ok"}

    def test_unavailable_becomes_a_null_score_with_the_reason(self):
        bureau, _ = client([TimeoutError()], retries=0)
        enriched = enrich_inputs({}, "CUST-1", bureau)
        assert enriched["bureau_score"] is None
        assert "timeout" in enriched["bureau_status"]


class SlowHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        time.sleep(0.3)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"score": 500}')

    def log_message(self, *args):
        pass


@pytest.fixture
def slow_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), SlowHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_a_real_socket_timeout_is_survived(slow_server):
    bureau = BureauClient(slow_server, timeout=0.05, retries=1, sleep=lambda s: None)
    report = bureau.fetch("CUST-1")
    assert not report.available
    assert report.attempts == 2
    assert report.status.endswith("timeout")
