"""Client for an external bureau. Every failure mode becomes a report with no score and a
status saying why."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

Transport = Callable[[str, float], tuple[int, bytes]]

RETRY_STATUSES = frozenset({500, 502, 503, 504})


class BureauUnavailable(Exception):
    pass


class BureauBadData(Exception):
    pass


@dataclass(frozen=True)
class BureauReport:
    reference: str
    score: int | None
    status: str
    attempts: int
    missing: tuple[str, ...] = ()

    @property
    def available(self) -> bool:
        return self.score is not None


def urllib_transport(url: str, timeout: float) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


class BureauClient:
    def __init__(
        self,
        base_url: str,
        *,
        transport: Transport = urllib_transport,
        timeout: float = 2.0,
        retries: int = 2,
        backoff: float = 0.1,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.sleep = sleep

    def fetch(self, reference: str) -> BureauReport:
        url = f"{self.base_url}/subjects/{reference}"
        attempts = 0
        last_error = ""
        while attempts <= self.retries:
            attempts += 1
            try:
                status, body = self.transport(url, self.timeout)
            except TimeoutError:
                last_error = "timeout"
            except (urllib.error.URLError, ConnectionError, OSError) as exc:
                last_error = f"connection error: {exc}"
            else:
                if status in RETRY_STATUSES:
                    last_error = f"http {status}"
                elif status != 200:
                    return BureauReport(reference, None, f"http {status}", attempts)
                else:
                    return self.parse(reference, body, attempts)
            if attempts <= self.retries:
                self.sleep(self.backoff * attempts)
        return BureauReport(
            reference, None, f"unavailable after {attempts} attempts: {last_error}", attempts
        )

    def parse(self, reference: str, body: bytes, attempts: int) -> BureauReport:
        try:
            data: Any = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return BureauReport(reference, None, "bad data: not json", attempts)
        if not isinstance(data, dict):
            return BureauReport(reference, None, "bad data: not an object", attempts)
        if data.get("reference") not in (None, reference):
            return BureauReport(reference, None, "bad data: reference mismatch", attempts)
        score = data.get("score")
        if score is None:
            missing = tuple(k for k in ("score",) if k not in data)
            return BureauReport(reference, None, "partial: no score in response", attempts, missing)
        if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 1000:
            return BureauReport(reference, None, f"bad data: score {score!r}", attempts)
        return BureauReport(reference, score, "ok", attempts)


def enrich_inputs(inputs: dict, reference: str, client: BureauClient) -> dict:
    report = client.fetch(reference)
    return {**inputs, "bureau_score": report.score, "bureau_status": report.status}


def client_from_settings() -> BureauClient:
    from django.conf import settings

    return BureauClient(settings.BUREAU_BASE_URL, timeout=settings.BUREAU_TIMEOUT_SECONDS)
