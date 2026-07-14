# development/e2e — end-to-end rigs against a live stack

Everything here runs against a **real, live stack** (OpenSearch + backend, and for the smoke also
k3d + real scanners) — unlike `backend/tests/`, which is the pytest suite. Nothing here runs in CI;
these are operator-driven rigs for proving the whole pipe and for measure-first perf questions.
(The CI **route smoke** is a different, lighter animal: fixture-seeded, no k3d, gating every PR —
`frontend/scripts/ci-smoke.mjs` + `development/scripts/seed-smoke.sh`, spec in
`development/standards/testing.md` §4.)

## Contents

| File | What it is |
|---|---|
| [`smoke.sh`](smoke.sh) | The **level-2 e2e smoke** (risk-register #134): real Trivy + Grype as host processes scan a k3d cluster, push through the live backend into OpenSearch. Covers: auth + must-change rotation, token mint, two scan cycles (idempotency), per-scanner counts, disagreement, the **reconcile/tombstone phase** (severity-filtered cycle → present shrinks → full cycle → exact restore), scheduled jobs, log-content assertions, and (since #222) the **read/report phase**: search + cursor paging, facets, triage→journal, decision round-trip (ignore_rule projection + revoke), SLA round-trip, trends/contributors, sanitized CSV + per-scanner VEX export, M7 report enqueue, /metrics. The **M8 section** (#249) adds: point-in-time reconstruction (`as_of` at a T before a state-changing rescan returns the OLD state, and is stable across re-reads — D28), the M8c reads (provenance exact `scan_order`, images inventory, cursor-paged audit, clusters rename journal+CAS round-trip), the M8d `ptype` facet, and the M8e saved-view CRUD round-trip. The **D46 vocabulary section** (#274) proves crit→critical end-to-end: full-word `severity_canonical` on finding docs + short `crit`/`med` count columns on scan-events (the wire), the SLA-overdue regression (a near-zero `critical_days` tips a real critical overdue — the bug that hid since M5d), and full-word severities in CSV/VEX exports. Closes with a **PIT-leak-zero** check. Idempotent (decision revoked, SLA/name restored in-phase). CronJob/Helm packaging is deliberately NOT here — that's M10. |
| [`loadbreak.py`](loadbreak.py) | The **#249 load / capture / break rig**: synthetic envelopes (no k3d) drive the live backend hard and then try to break it. **LOAD** floods `/api/v1/ingest/scan` with mixed v3+v4 envelopes across a synthetic fleet (~250k rows on `LOAD_HEAVY`, enough to provoke the 429/503 backpressure that is the broker-less flow control — pass = backoff-and-succeed, never a drop or a 500). **CAPTURE** walks every GET endpoint discovered from `/openapi.json` (+ `/metrics`), once quiet and once under load, logging every response to `logs/api-capture/` and running the whole-surface D46 lint (any severity VALUE reading `crit/med/moderate` = FAIL). **BREAK** runs named abuse cases (malformed/oversized ingest, garbage/oversized/absent auth, wrong-cluster/wrong-scanner scope, tampered cursors, the D40 stale-scan_order replay, CAS-rename hammering) — any 500 or internals-leak = FAIL. **LIFECYCLE** proves index create/delete: bootstrap idempotency (every managed index/template at the code's `MAPPING_VERSION`, so a re-run is a no-op) and, behind `--lifecycle`, a real rollover+retention drop on a sacrificial `c-load-life` cluster. **INVARIANTS**: PIT-leak zero, as-of-T determinism, metrics-move, store vitals (heap %/index count/doc count/open PITs before-and-after each phase), and a secret-leak grep over `backend.log`. `--chaos-store` pauses the OpenSearch container mid-run (503-without-internals + `/readyz` degrade + recovery without restart). |
| [`bench_refresh.py`](bench_refresh.py) | The **#117 refresh-cost bench**: synthetic schema-v3 envelopes at fleet scale (clusters × scanners × digests, concurrent senders) straight at `/api/v1/ingest/scan`, sampling `findings/_stats/refresh` per cycle. Answered #117 (verdict: the per-envelope refresh is flat, ~10–13 ms — keep it). Re-run if M6+ read load changes the picture. Knobs: `BENCH_CLUSTERS/BENCH_DIGESTS/BENCH_FINDINGS/BENCH_CONCURRENCY`. |
| [`bench_read.py`](bench_read.py) | The read-under-ingest contention bench (#134 item 4 read side): read latency while a write load runs. |
| [`results.md`](results.md) | Findings log of the runs — what worked, what didn't, and the numbers. |
| `logs/` | Per-run artifacts — **gitignored**, refreshed on every run: `backend.log`, `scanner-*.log`, `cluster.log`, `jobs.log`, `opensearch.log` (smoke); `api-capture/*.jsonl`, `loadbreak-*.jsonl`, `loadbreak-summary.md`, `metrics-capture.txt` (loadbreak). |

## Running

Prerequisites (neither script starts these — see each script's header for the exact commands):

1. **OpenSearch**: `docker compose -f development/setup/opensearch-dev.yml up -d` (wipe first with
   `down -v` for a clean run).
2. **Backend**: from `backend/`, uvicorn with the dev bootstrap-admin env, stdout piped to
   `development/e2e/logs/backend.log` (the smoke's log-assertion phase reads it).
3. *(smoke only)* k3d cluster `alpha` with the seeded workloads + `trivy`/`grype` on PATH.

```bash
./development/e2e/smoke.sh                                    # the full smoke (real scanners)
cd backend && uv run python ../development/e2e/bench_refresh.py   # the refresh-cost bench
cd backend && uv run python ../development/e2e/bench_read.py      # the read-under-ingest bench
```

All are idempotent across re-runs. Residue: the smoke writes under the k3d cluster's real
`cluster_id`, the benches under `c-bench-*`, loadbreak under `c-load-*` — wipe OpenSearch before demos.

> **Scanner images:** the smoke's D46 wire check reads what the *running* scanner binaries push, so
> run it against the **post-#278 scanner build** (full-word canonicals). Against stale images the wire
> check fails honestly — that's the point.

### Running `loadbreak.py` manually

Same two prerequisites as above (OpenSearch up, backend up **with stdout piped to
`development/e2e/logs/backend.log`** — the secret-leak grep and log audit read it). No k3d or real
scanners needed; it's synthetic-envelope, backend+store only, so it runs anywhere in a few minutes.

```bash
cd backend
# everything (load → capture-under-load + quiet → break → lifecycle-idempotency → invariants):
uv run python ../development/e2e/loadbreak.py

# one phase at a time:
uv run python ../development/e2e/loadbreak.py --phase load
uv run python ../development/e2e/loadbreak.py --phase capture
uv run python ../development/e2e/loadbreak.py --phase break
uv run python ../development/e2e/loadbreak.py --phase invariants

# destructive extras (off by default — they mutate/interrupt the store):
uv run python ../development/e2e/loadbreak.py --lifecycle     # real retention drop on c-load-life
uv run python ../development/e2e/loadbreak.py --chaos-store   # pause/unpause javv-opensearch mid-run

# gentle run (no backpressure) — a tenth of the default volume:
LOAD_HEAVY=0 uv run python ../development/e2e/loadbreak.py --phase load
```

**Knobs** (env): `LOAD_HEAVY=1` (default; `0` = gentle) · `LB_CLUSTERS`/`LB_DIGESTS`/`LB_FINDINGS`/
`LB_CYCLES`/`LB_CONCURRENCY` (scale) · `LB_BACKEND`/`LB_OPENSEARCH`/`LB_OS_CONTAINER` (targets).
Default heavy scale is ~250k finding rows and takes a few minutes on this VM; expect a band of
429/503 during LOAD — that is the backpressure working, not a failure.

**Reading the result:** the script prints a per-section verdict map and exits non-zero if any section
FAILed. The human-readable roll-up is `logs/loadbreak-summary.md`; the raw evidence is in
`logs/loadbreak-*.jsonl`, every captured response in `logs/api-capture/<method>-<path>.jsonl`, and the
`/metrics` snapshots in `logs/metrics-capture.txt`. Residue: `c-load-*` (wipe = compose `down -v && up -d`).
