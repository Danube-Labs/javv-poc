"""Inventory commit, scanner side (M8a slice 2, D39/H4-r2). At cycle END the scanner certifies
its run: "I discovered `expected_count` images; every envelope has been pushed." The backend
counts what actually landed and writes the manifest — `committed` only when complete.

Best-effort, unlike the fail-CLOSED cycle-start calls (scope/scan_order): by commit time every
envelope is already pushed, so a failed commit loses nothing — the run just stays uncertified and
inventory reads fall back to the prior committed run (+ the staleness banner). Log and move on."""

from datetime import datetime

import httpx
import structlog

log = structlog.get_logger()


def commit_inventory(
    http: httpx.Client,
    *,
    token: str | None,
    scan_run_id: str,
    expected_count: int,
    started_at: datetime,
) -> bool:
    """Certify the cycle's inventory. True when the backend answered `status=committed`."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        resp = http.post(
            "/api/v1/inventory-runs",
            headers=headers,
            json={
                "scan_run_id": scan_run_id,
                "expected_count": expected_count,
                "started_at": started_at.isoformat(),
            },
        )
        resp.raise_for_status()
        manifest = resp.json()
    except Exception:
        log.warning("inventory commit failed — run stays uncertified", exc_info=True)
        return False
    committed = manifest.get("status") == "committed"
    if not committed:
        # expected vs written mismatch: some image never landed (scan failure / dead letter)
        log.warning(
            "inventory run partial — not readable as live inventory",
            expected=manifest.get("expected_count"),
            written=manifest.get("written_count"),
        )
    return committed
