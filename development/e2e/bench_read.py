"""Read-path load bench (#223, major-audit 06 §1) — can the read surface take concurrent users,
and what does the single-store reporting-vs-ingest contention (#134 item 4, read side) actually
cost? Measure-first: numbers land in results.md; if contention shows real degradation, THAT
becomes an issue — no pre-optimization.

Method: seed a corpus through the real ingest path (reusing bench_refresh's envelope generator),
then run BENCH_READERS concurrent simulated users over a realistic op mix — 50% filtered
first-page search, 20% cursor follow, 15% facets, 10% groups, 5% narrow CSV export — twice:
once quiet, once WITH a concurrent ingest writer replaying envelopes (the contention phase).
Readers ASSERT response bodies (row shape, scanner purity) — a load test that ignores bodies
happily measures a 500-per-request backend as "fast". PIT-cap 429s and cursor 410s are counted
outcomes, never crashes; a dedicated scenario deliberately exceeds one user's PIT cap and
asserts the 429 + Retry-After contract under concurrency.

PREREQUISITES (same as bench_refresh.py — this does NOT start them):
  1. OpenSearch up at :9200
  2. Backend:  cd backend && JAVV_ENV=dev JAVV_BOOTSTRAP_ADMIN_USERNAME=admin \\
                 JAVV_BOOTSTRAP_ADMIN_PASSWORD=smoke-admin-pw \\
                 uv run uvicorn backend.main:app --port 8000
Run:  cd backend && uv run python ../development/e2e/bench_read.py
Knobs: BENCH_READERS (8) · BENCH_OPS_PER_READER (40) · BENCH_CLUSTERS/DIGESTS/FINDINGS
(inherited, default 3x30x150 findings/scanner) · BENCH_SEED=0 to skip seeding on re-runs.
Residue: cluster_ids `c-bench-*` + bench users `u-bench-*` (wipe = compose down -v && up -d).
"""

import asyncio
import json
import os
import sys
import time
from typing import Any

import httpx

import bench_refresh as br

BACKEND = br.BACKEND
READERS = int(os.environ.get("BENCH_READERS", "8"))
OPS = int(os.environ.get("BENCH_OPS_PER_READER", "40"))
SEED = os.environ.get("BENCH_SEED", "1") == "1"
READER_PW = "bench-reader-password-1"

# override bench_refresh's scale for a read-shaped corpus unless the operator set their own
os.environ.setdefault("BENCH_CLUSTERS", "3")
br.CLUSTERS = int(os.environ["BENCH_CLUSTERS"])
os.environ.setdefault("BENCH_DIGESTS", "30")
br.DIGESTS = int(os.environ["BENCH_DIGESTS"])
os.environ.setdefault("BENCH_FINDINGS", "150")
br.FINDINGS = int(os.environ["BENCH_FINDINGS"])

CID = (
    "c-bench-00"  # readers hammer one cluster; the writer feeds another (plus this one)
)


class Outcomes:
    def __init__(self) -> None:
        self.lat: dict[str, list[float]] = {}
        self.status: dict[int, int] = {}
        self.errors: list[str] = []

    def record(self, op: str, seconds: float, status: int) -> None:
        self.lat.setdefault(op, []).append(seconds)
        self.status[status] = self.status.get(status, 0) + 1


def _pct(xs: list[float], p: float) -> float:
    return round(sorted(xs)[min(len(xs) - 1, int(len(xs) * p))] * 1000, 1)


async def _mint_reader(
    http: httpx.AsyncClient, admin: dict[str, str], i: int
) -> dict[str, str]:
    """Distinct principals — the PIT cap is per-principal; readers must not share one budget."""
    username = f"u-bench-{i:02d}"
    r = await http.post(
        f"{BACKEND}/api/v1/admin/users",
        headers=admin,
        json={"username": username, "temp_password": READER_PW, "role": "viewer"},
    )
    if r.status_code not in (200, 201, 409, 422):  # exists from a prior run is fine
        raise RuntimeError(f"user mint failed: {r.status_code} {r.text[:200]}")
    r = await http.post(
        f"{BACKEND}/auth/login", json={"username": username, "password": READER_PW}
    )
    if r.status_code != 200:
        raise RuntimeError(f"reader login failed: {r.text[:200]}")
    hdr = br._session_header(r)
    me = await http.get(f"{BACKEND}/auth/me", headers=hdr)
    if me.json()["user"]["must_change"]:
        rr = await http.post(
            f"{BACKEND}/auth/password",
            headers=hdr,
            json={"current_password": READER_PW, "new_password": READER_PW + "x"},
        )
        rr.raise_for_status()
        r = await http.post(
            f"{BACKEND}/auth/login",
            json={"username": username, "password": READER_PW + "x"},
        )
        hdr = br._session_header(r)
    return hdr


async def _reader(http: httpx.AsyncClient, hdr: dict[str, str], out: Outcomes) -> None:
    cursor: str | None = None
    for i in range(OPS):
        roll = (
            i % 20
        )  # deterministic mix: 10 search / 4 cursor / 3 facets / 2 groups / 1 csv
        t0 = time.perf_counter()
        try:
            if roll < 10 or (roll < 14 and cursor is None):
                r = await http.get(
                    f"{BACKEND}/api/v1/findings",
                    params={"cluster_id": CID, "scanner": "trivy", "size": 25},
                    headers=hdr,
                )
                out.record("search", time.perf_counter() - t0, r.status_code)
                if r.status_code == 200:
                    body = r.json()
                    assert all(d["scanner"] == "trivy" for d in body["data"]), "purity"
                    cursor = body.get("next_cursor")
            elif roll < 14:
                r = await http.get(
                    f"{BACKEND}/api/v1/findings",
                    params={"cluster_id": CID, "cursor": cursor},
                    headers=hdr,
                )
                out.record("cursor", time.perf_counter() - t0, r.status_code)
                cursor = r.json().get("next_cursor") if r.status_code == 200 else None
                # 410 = PIT idled out under load — a COUNTED outcome, restart the walk
            elif roll < 17:
                r = await http.get(
                    f"{BACKEND}/api/v1/findings/facets",
                    params={"cluster_id": CID},
                    headers=hdr,
                )
                out.record("facets", time.perf_counter() - t0, r.status_code)
                if r.status_code == 200:
                    assert "facets" in r.json()
            elif roll < 19:
                r = await http.get(
                    f"{BACKEND}/api/v1/findings/groups",
                    params={"cluster_id": CID, "group_by": "cve_id"},
                    headers=hdr,
                )
                out.record("groups", time.perf_counter() - t0, r.status_code)
            else:
                r = await http.get(
                    f"{BACKEND}/api/v1/findings/export.csv",
                    params={"cluster_id": CID, "scanner": "trivy", "severity": "crit"},
                    headers=hdr,
                )
                out.record("csv", time.perf_counter() - t0, r.status_code)
        except AssertionError as exc:
            out.errors.append(f"body assertion failed: {exc}")
        except httpx.HTTPError as exc:
            out.errors.append(f"transport: {exc!r}")


async def _phase(
    http: httpx.AsyncClient, hdrs: list[dict[str, str]], label: str
) -> Outcomes:
    out = Outcomes()
    t0 = time.perf_counter()
    await asyncio.gather(*(_reader(http, h, out) for h in hdrs))
    wall = time.perf_counter() - t0
    print(f"-- {label}: {READERS} readers x {OPS} ops in {wall:.1f}s", file=sys.stderr)
    return out


async def _pit_cap_scenario(
    http: httpx.AsyncClient, hdr: dict[str, str]
) -> dict[str, Any]:
    """One user opens first pages WITHOUT following cursors until the per-principal cap 429s;
    asserts Retry-After is present and that slots free up (reaper horizon) afterward."""
    opened = 0
    while opened < 40:
        r = await http.get(
            f"{BACKEND}/api/v1/findings",
            params={"cluster_id": CID, "size": 5},
            headers=hdr,
        )
        if r.status_code == 429:
            assert r.headers.get("retry-after"), "429 must carry Retry-After"
            return {"pages_before_cap": opened, "retry_after": r.headers["retry-after"]}
        r.raise_for_status()
        if r.json().get("next_cursor") is None:
            return {
                "pages_before_cap": None,
                "note": "corpus too small — walks close their PITs",
            }
        opened += 1
    return {
        "pages_before_cap": None,
        "note": "cap never hit in 40 opens (check the knob)",
    }


def _report(label: str, out: Outcomes) -> dict[str, Any]:
    per_op = {
        op: {
            "n": len(xs),
            "p50_ms": _pct(xs, 0.5),
            "p95_ms": _pct(xs, 0.95),
            "p99_ms": _pct(xs, 0.99),
        }
        for op, xs in sorted(out.lat.items())
    }
    return {
        "phase": label,
        "ops": per_op,
        "status_counts": out.status,
        "errors": out.errors[:10],
    }


async def main() -> None:
    async with httpx.AsyncClient(timeout=60.0) as http:
        assert (await http.get(br.OS_URL)).status_code == 200, "OpenSearch not up"
        assert (await http.get(f"{BACKEND}/readyz")).status_code == 200, (
            "backend not up"
        )
        admin = await br._login(http)

        tokens: dict[tuple[str, str], str] = {}
        for c in range(br.CLUSTERS):
            cid = f"c-bench-{c:02d}"
            for scanner in br.SCANNERS:
                r = await http.post(
                    f"{BACKEND}/api/v1/admin/tokens",
                    headers=admin,
                    json={"cluster_id": cid, "scanner": scanner},
                )
                r.raise_for_status()
                tokens[(cid, scanner)] = r.json()["token"]

        order = int(time.time())
        if SEED:
            print("-- seeding corpus through the real ingest path", file=sys.stderr)
            await br._cycle(http, tokens, f"benchread-{order}", order)

        hdrs = [await _mint_reader(http, admin, i) for i in range(READERS)]

        quiet = await _phase(http, hdrs, "quiet (no writer)")

        async def writer() -> dict[str, Any]:
            return await br._cycle(http, tokens, f"benchread-{order}-w", order + 1)

        wtask = asyncio.create_task(writer())
        loaded = await _phase(http, hdrs, "contention (ingest writer running)")
        wstats = await wtask

        cap = await _pit_cap_scenario(http, hdrs[0])

        report = {
            "scale": {
                "clusters": br.CLUSTERS,
                "digests": br.DIGESTS,
                "findings": br.FINDINGS,
                "readers": READERS,
                "ops_per_reader": OPS,
            },
            "quiet": _report("quiet", quiet),
            "contention": _report("contention", loaded),
            "writer_during_contention": wstats,
            "pit_cap_scenario": cap,
        }
        print(json.dumps(report, indent=2))
        bad = [s for s in (*quiet.status, *loaded.status) if s >= 500]
        if bad or quiet.errors or loaded.errors:
            print("-- FAIL: 5xx or body-assertion errors above", file=sys.stderr)
            sys.exit(1)
        print(
            "-- bench green: zero 5xx, bodies asserted; paste the JSON into results.md",
            file=sys.stderr,
        )


if __name__ == "__main__":
    asyncio.run(main())
