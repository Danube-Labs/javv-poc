"""scan_order allocation, scanner side (D45): the fail-closed cycle-start fetch — the backend
mints the order (`POST /api/v1/scan-runs`); None on any failure means do not scan this cycle
(same contract as the D43 scope fetch)."""

from typing import Any

import httpx

from scanner.envelope import new_scan_run
from scanner.orders import fetch_scan_order


def _client(handler: Any) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://backend")


def test_fetch_returns_the_allocated_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST" and request.url.path == "/api/v1/scan-runs"
        assert request.headers["Authorization"] == "Bearer tok"
        return httpx.Response(200, json={"scan_order": 42})

    with _client(handler) as http:
        assert fetch_scan_order(http, token="tok") == 42


def test_fetch_is_fail_closed_on_any_backend_failure() -> None:
    # 401 / 5xx / garbage body / transport error → None → the caller must NOT scan
    with _client(lambda r: httpx.Response(401)) as http:
        assert fetch_scan_order(http, token="bad") is None
    with _client(lambda r: httpx.Response(200, json={"nope": 1})) as http:
        assert fetch_scan_order(http, token="tok") is None
    with _client(lambda r: httpx.Response(200, json={"scan_order": "abc"})) as http:
        assert fetch_scan_order(http, token="tok") is None

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("backend down")

    with _client(boom) as http:
        assert fetch_scan_order(http, token="tok") is None


def test_new_scan_run_carries_the_backend_allocated_order() -> None:
    run = new_scan_run(42)
    assert run.scan_order == 42
    assert run.scan_run_id and run.started_at is not None
