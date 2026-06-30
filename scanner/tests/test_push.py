"""Push delivers an envelope to the backend ingest endpoint: gzipped body, idempotent
(deterministic content — a retried push double-counts nothing server-side, D18), transient
failures (network / 429 / 5xx) retried with backoff+jitter, permanent failures (other 4xx) or
exhausted retries written to a dead-letter sink. Tested with httpx.MockTransport — no network."""

import gzip
import json
from pathlib import Path

import httpx
import pytest

from scanner.envelope import Envelope, build_envelope, new_scan_run
from scanner.models import Finding
from scanner.push import push_envelope

ERR = "ERR"  # sentinel: handler raises a transport error on this attempt


def make_envelope() -> Envelope:
    return build_envelope(
        new_scan_run(),
        cluster_id="c",
        scanner="trivy",
        image_digest="sha256:x",
        findings=[Finding(vuln_id="CVE-1", package_name="p", package_version="1", severity="HIGH")],
    )


def client_for(steps: list[object]) -> tuple[httpx.Client, list[httpx.Request]]:
    """A client whose Nth request yields steps[N] (an int status or ERR sentinel)."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        step = steps[len(requests)]
        requests.append(request)
        if step == ERR:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(int(step))  # type: ignore[arg-type]

    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://backend"), requests


def push(env: Envelope, client: httpx.Client, dead_letter: Path, **kw: object):  # noqa: ANN201
    sleeps: list[float] = []
    result = push_envelope(
        env,
        client=client,
        dead_letter_path=dead_letter,
        sleep=sleeps.append,
        rng=lambda: 0.0,
        **kw,  # type: ignore[arg-type]
    )
    return result, sleeps


def test_delivers_gzipped_body_on_first_success(tmp_path: Path) -> None:
    env = make_envelope()
    client, requests = client_for([200])
    result, sleeps = push(env, client, tmp_path / "dl.jsonl")

    assert (result.delivered, result.attempts, result.dead_lettered) == (True, 1, False)
    assert sleeps == []
    req = requests[0]
    assert req.headers["content-encoding"] == "gzip"
    assert gzip.decompress(req.content).decode() == env.model_dump_json()  # body is the envelope


def test_gzip_body_is_deterministic_for_idempotent_retries(tmp_path: Path) -> None:
    env = make_envelope()
    c1, r1 = client_for([200])
    c2, r2 = client_for([200])
    push(env, c1, tmp_path / "a.jsonl")
    push(env, c2, tmp_path / "b.jsonl")
    assert r1[0].content == r2[0].content  # byte-identical → safe to re-send


@pytest.mark.parametrize("transient", [503, 429, 500, ERR])
def test_retries_transient_then_succeeds(tmp_path: Path, transient: object) -> None:
    client, requests = client_for([transient, 200])
    result, sleeps = push(make_envelope(), client, tmp_path / "dl.jsonl")
    assert result.delivered is True
    assert result.attempts == 2
    assert len(requests) == 2
    assert len(sleeps) == 1  # backed off once between the two attempts


def test_permanent_4xx_is_not_retried_and_is_dead_lettered(tmp_path: Path) -> None:
    env = make_envelope()
    dl = tmp_path / "dl.jsonl"
    client, requests = client_for([400, 200])  # 200 would be used if it (wrongly) retried
    result, sleeps = push(env, client, dl)

    assert (result.delivered, result.dead_lettered, result.attempts) == (False, True, 1)
    assert len(requests) == 1  # not retried
    assert sleeps == []
    lines = dl.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == json.loads(env.model_dump_json())


def test_exhausted_transient_retries_dead_letter(tmp_path: Path) -> None:
    dl = tmp_path / "dl.jsonl"
    client, requests = client_for([503, 503, 503])
    result, sleeps = push(make_envelope(), client, dl, max_attempts=3)

    assert (result.delivered, result.dead_lettered, result.attempts) == (False, True, 3)
    assert len(requests) == 3
    assert len(sleeps) == 2  # slept between attempts, not after the last
    assert len(dl.read_text().splitlines()) == 1
