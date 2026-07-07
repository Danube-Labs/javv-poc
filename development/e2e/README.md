# development/e2e — end-to-end rigs against a live stack

Everything here runs against a **real, live stack** (OpenSearch + backend, and for the smoke also
k3d + real scanners) — unlike `backend/tests/`, which is the pytest suite. Nothing here runs in CI;
these are operator-driven rigs for proving the whole pipe and for measure-first perf questions.

## Contents

| File | What it is |
|---|---|
| [`smoke.sh`](smoke.sh) | The **level-2 e2e smoke** (risk-register #134): real Trivy + Grype as host processes scan a k3d cluster, push through the live backend into OpenSearch. Covers: auth + must-change rotation, token mint, two scan cycles (idempotency), per-scanner counts, disagreement, the **reconcile/tombstone phase** (severity-filtered cycle → present shrinks → full cycle → exact restore), scheduled jobs, log-content assertions, and (since #222) the **read/report phase**: search + cursor paging, facets, triage→journal, decision round-trip (ignore_rule projection + revoke), SLA round-trip, trends/contributors, sanitized CSV + per-scanner VEX export, M7 report enqueue, /metrics. Idempotent (decision revoked, SLA restored in-phase). CronJob/Helm packaging is deliberately NOT here — that's M10. |
| [`bench_refresh.py`](bench_refresh.py) | The **#117 refresh-cost bench**: synthetic schema-v3 envelopes at fleet scale (clusters × scanners × digests, concurrent senders) straight at `/api/v1/ingest/scan`, sampling `findings/_stats/refresh` per cycle. Answered #117 (verdict: the per-envelope refresh is flat, ~10–13 ms — keep it). Re-run if M6+ read load changes the picture. Knobs: `BENCH_CLUSTERS/BENCH_DIGESTS/BENCH_FINDINGS/BENCH_CONCURRENCY`. |
| [`results.md`](results.md) | Findings log of the smoke runs — what worked, what didn't, and the numbers. |
| `logs/` | Per-component run artifacts (`backend.log`, `scanner-*.log`, `cluster.log`, `jobs.log`, `opensearch.log`) — **gitignored**, refreshed on every run. |

## Running

Prerequisites (neither script starts these — see each script's header for the exact commands):

1. **OpenSearch**: `docker compose -f development/setup/opensearch-dev.yml up -d` (wipe first with
   `down -v` for a clean run).
2. **Backend**: from `backend/`, uvicorn with the dev bootstrap-admin env, stdout piped to
   `development/e2e/logs/backend.log` (the smoke's log-assertion phase reads it).
3. *(smoke only)* k3d cluster `alpha` with the seeded workloads + `trivy`/`grype` on PATH.

```bash
./development/e2e/smoke.sh                                    # the full smoke
cd backend && uv run python ../development/e2e/bench_refresh.py   # the bench
```

Both are idempotent across re-runs. Residue: the smoke writes under the k3d cluster's real
`cluster_id`, the bench under `c-bench-*` — wipe OpenSearch before demos.
