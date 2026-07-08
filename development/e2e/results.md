# JAVV end-to-end smoke — results (2026-07-05)

Level-2 smoke: **real Trivy + Grype scanners run as host processes against the k3d `alpha`
cluster, pushing to a locally-running backend + fresh OpenSearch.** No CronJobs / Helm (that
packaging is deferred to M10). This is risk-register #134's ingest smoke.

Environment: OpenSearch 3.7.0 (docker, wiped fresh), backend on `localhost:8000`
(`JAVV_ENV=dev`), k3d `alpha`, trivy + grype on PATH. Bootstrap admin `admin` / `smoke-admin-pw`
(rotated to `smoke-admin-rotated-pw` on first login).

Per-component logs live in `./logs/` (gitignored): `backend.log`, `scanner-trivy.log`,
`scanner-grype.log`, `jobs.log`, `cluster.log`, `opensearch.log`.

---

## Workloads scanned

Empty scan-scope = **scan everything running**, so all 9 distinct image digests cluster-wide were
scanned (our 4 `javv-smoke` targets + 5 kube-system system images). The `javv-smoke` targets:

| Deployment | Image | Pods | Distinct digest |
|---|---|---|---|
| vuln-nginx | **nginx:1.21.6** | 3 | `sha256:2bcabc…` |
| nginx-second | **nginx:1.23.4** | 1 | `sha256:f5747a…` |
| vuln-python | python:3.9.16-slim | 1 | `sha256:5cde4e…` |
| vuln-alpine | alpine:3.14 | 1 | `sha256:0f2d5c…` |

The two nginx tags were the point of this run — see the tag-comparison result below.

---

## What worked ✅

1. **Fresh bootstrap** — backend startup created all 12 indices + 4 roles + seeded the admin,
   idempotently, MAPPING_VERSION 7 (`backend.log`, "bootstrap complete").
2. **Auth lifecycle** — login → forced `must_change` password rotation → server-side session
   cookie → `/auth/me` shows `must_change:false`, capabilities `["*"]`.
3. **Two nginx tags behave as distinct targets** (the thing you asked to see):
   - nginx:1.21.6 (older): **trivy 759 / grype 745**
   - nginx:1.23.4 (newer): **trivy 634 / grype 620**
   - ~120 fewer findings on the newer tag — real CVE reduction between tags, tracked per-digest,
     never collapsed across tags.
4. **Digest-dedup (D30)** — nginx:1.21.6's 3 pods collapsed to **1 scan / 1 image doc with
   `replicas: 3`**. N pods → 1 scan, as designed.
5. **Both scanners delivered all 9 images, 0 dead-lettered** — Trivy and Grype cycles clean.
6. **Per-scanner separation is sacred** — totals are reported separately (trivy 2064 /
   grype 2168), never summed or merged.
7. **Per-image count disagreement (D5b, `count_delta`)** — populated on every image both scanners
   hit. Most striking: **alpine 3.14 → trivy 0 vs grype 73 (`count_delta -73`)** (see caveat #4).
8. **Per-finding severity disagreement (D5a, `disagree` flag)** — 701 findings flagged on *each*
   scanner's side, symmetric, as designed.
9. **Server-stamped `ingested_at` (task F)** — present on every scan-event and distinct from the
   client `@timestamp` (e.g. `ingested_at 07:50:24` vs `@timestamp 07:50:07`), which is what makes
   retention safe against a backdated scanner clock.
10. **Idempotency / re-scan (watermark CAS)** — a **second** Trivy cycle left the findings count
    unchanged (2064 → 2064, updated in place by `finding_key`, no duplicates) while `scan_order`
    advanced monotonically **1 → 2**. Each cycle is its own catalog commit (distinct `commit_key`).
11. **Background jobs** — `staleness` and `lifecycle` sweeps both ran with **0 errors**
    (0 staled / 0 rolled / 0 dropped — correct for fresh, tiny indices).
12. **Logging** — structured JSON per event with a `request_id` correlator; the redaction
    processor masks token/secret/password keys and scrubs `Bearer …`. Example ingest line:
    ```json
    {"scan_run_id":"b24a93…","findings":0,"event":"ingest committed",
     "request_id":"9eb3a1c1…","cluster_id":"fcbcbe84…","scanner":"trivy",
     "level":"info","timestamp":"2026-07-05T07:50:22.506991Z"}
    ```

---

## What didn't work / quirks worth noting ⚠️

1. **Redaction is over-broad on field *names*.** At bootstrap the log line for created indices
   rendered `"system-tokens": "[REDACTED]"` — the redactor masks any key containing `token`, so it
   masked the *index name* (a non-secret). Fails safe (never leaks), but it's noisy and can hide
   harmless values. Candidate follow-up: tighten `_SENSITIVE_KEY` or redact by value shape, not key
   substring. (`backend/src/backend/core/logging.py:16`)
2. **`image` docs have no `image_ref` field.** The tag is stored split as `image_repo` + `tag`
   (e.g. `nginx` + `1.21.6`), not as a combined `image_ref`. Anything on the FE expecting
   `image_ref` will get null — align the M9x image views to `image_repo`/`tag`.
3. **Empty scope scans the whole cluster.** With no scan-scope configured, the scanner enumerated
   kube-system system images too (traefik, coredns, metrics-server, local-path, pause). Expected
   (empty scope = scan everything), but if you want to smoke *only* `javv-smoke`, set a namespace
   scan-scope first.
4. **Trivy reported 0 findings on alpine:3.14** (grype found 73). Not a pipeline failure — both
   scanned the digest (the catalog has a trivy scan-event with `total=0`) — but alpine 3.14 is EOL
   and Trivy may skip an EOL secdb. Verify before reading `trivy 0` as "clean". This is exactly the
   cross-scanner divergence the disagreement flags exist to surface.
5. **Present=false reconcile was NOT exercised.** The second cycle scanned an unchanged cluster, so
   nothing flipped `present=false`. To see a real fixed-CVE tombstone, redeploy a workload at a
   patched tag and re-scan — left for a future run.

---

## Reproduce

`./smoke.sh` in this directory (assumes OpenSearch + k3d `alpha` + backend are up; see the header
of the script). It re-runs the workload deploy → token mint → both scan cycles → verification and
refreshes these logs. The manual first pass that produced this file matched the script step-for-step.

---

# Second run — 2026-07-05 (post-#159 logging + the #158 reconcile phase)

Fresh wipe, same workloads. Everything from run 1 reproduced identically (same per-scanner counts:
trivy 2064 / grype 2168; same two-nginx-tag split; jobs 0 errors). New in this run:

## Reconcile / tombstone phase (#158) ✅ — the previously-unexercised path

Reconcile-on-commit is **per-digest**, so the flip needs the *same* digest re-scanned reporting
fewer findings — `JAVV_TRIVY_SEVERITIES=CRITICAL` does exactly that (mirrors a vuln-DB update
dropping findings for an unchanged image). Measured:

| Step | present=true | present=false |
|---|---|---|
| baseline (full cycle) | 2064 | 0 |
| CRITICAL-only cycle | 59 | **2005 — all 2005 with `resolved_at`** |
| full cycle again | **2064 (exact restore)** | 0 |

Also documented (not asserted): a **disappeared image is deliberately NOT reconciled** — a new tag
is a new digest; the old digest keeps `present=true` until the **staleness sweep** (D20) owns it.
The original #158 text got this wrong; corrected on the issue.

## The new logging (#159), live

- `scanner-trivy.log` / `scanner-grype.log`: JSON per-image progress —
  `{"event":"scanning image","position":"3/9",…}` → `{"event":"scan done","findings":759,
  "duration_s":12.4,…}` → `{"event":"cycle complete","scanned":9,"delivered":9,…}` — every line
  carrying `scanner`/`cluster_id`/`scan_run_id`/`scan_order`.
- `backend.log`: one JSON stream (uvicorn access lines bridged too); `bootstrap complete` now
  lists index names unredacted; `ingest committed` per envelope with `request_id`.
- `backend-debug.log` (`JAVV_LOG_LEVEL=debug`): **every OpenSearch touch** —
  `POST http://localhost:9200/findings/_bulk [status:200 request:0.04s]` — plus the ingest
  sub-step seeds (`ingest: findings merged`, `ingest: findings reconciled absent`).
- The script now **asserts** log content (parseable `ingest committed` JSON, per-image progress
  lines) so a silent logging regression fails the smoke.

## New findings from this run (both fixed in the #158 PR)

1. 🔴 **Backend pytest bricks the dev admin.** The task-D last-admin-guard test disabled every
   other `role=admin` user in the *shared* `system-users` index via update_by_query and never
   restored them — the real bootstrap `admin` stayed `disabled:true` (no audit row: it was a
   direct doc write, not the API — the journal proved this in one query). Any full pytest run
   against the dev OpenSearch would break a subsequent smoke/login. **Fixed**: the test snapshots
   the ids it disables and restores them in a `finally`.
2. 🟠 **`JAVV_LOG_LEVEL=debug` dumped full OpenSearch request/response bodies** through the
   `opensearch` logger's own DEBUG lines — one scan cycle → a 6.3 MB backend log, and bodies are
   exactly what the `opensearchpy.trace` ban exists for. **Fixed** in javv-common: that logger is
   capped at INFO (per-request lines, no bodies) even at debug; pinned by test. Same cycle now
   logs 50 KB.

---

# #249 M0→M8 gate run (2026-07-08)

Full gate before M9: real-scanner smoke (extended to M8 + D46), the new `loadbreak.py`
robustness rig, both perf benches, and the full pytest suite — all against a wiped-fresh store
(OpenSearch 3.7.0, backend `JAVV_ENV=dev`, k3d `alpha`, post-#278 scanner binaries).

## Results — all green

| Component | Result | Real data it asserted on |
|---|---|---|
| `smoke.sh` (M0→M8 + D46) | ✅ green | trivy=2080 / grype=2211 findings; disagree=1426; as-of reconstructs present=2080 vs now=59; SLA overdue 100/100 under a 1-day policy; ptype facet = os,deb,go-module,gobinary,apk,python…; CSV severities = CRITICAL/HIGH/MEDIUM/LOW/UNKNOWN |
| `loadbreak.py` (all phases) | ✅ green | LOAD 5000 envelopes / 8000 HTTP attempts (retries incl.) → 4400 accepted (88%), 600 shed after 6-attempt backoff, 3600 attempt-level 429s, **0×5xx**; CAPTURE 25 endpoints, 0 D46 vocab leaks (quiet + under load); BREAK all abuse cases pass incl. D40 stale-replay → present=1; LIFECYCLE bootstrap idempotent @ MAPPING_VERSION 15; INVARIANTS PIT/as-of/metrics/secret all pass |
| `bench_refresh.py` | ✅ | per-envelope refresh 10.7–12.4 ms — matches the #117 baseline, no regression |
| `bench_read.py` | ✅ | reads under write contention p50 29 ms / p95 90 ms / p99 110 ms, **no 5xx** |
| full pytest (645 tests) | ✅ green | non-serial + serial, both exit 0, zero failures |

## Findings from this run — all were TEST bugs; the product was verified correct each time

The smoke's read/report section (#222) and the new M8/D46 sections had bit-rotted / been written
against assumptions that didn't hold on the real corpus. Each failure was investigated product-side
BEFORE touching the assertion; none masked a product defect.

**smoke.sh:**
1. decision revoke asserted `.revoked` — that field is on the *edit* endpoint; revoke returns `{decision:{revoked_at}}`. Product revokes correctly.
2. SLA read-back compared `="1"` — `critical_days` is a float, reads back `1.0`. Now a numeric `jq ==` compare.
3. `trends/findings` asserted `.series` — that endpoint returns `{new,resolved}` (scans-only has `.series`). Strengthened to require non-empty series.
4. as-of counted page rows with a `<100` corpus guard — real corpus is 2080. Now uses server-side `.total.value`; the check is *stricter* (exact 2080 match).
5. `ingest committed` log line check used `| head -1` under `pipefail` → SIGPIPE race once the log grows. Now `grep -m1`. (Product logs cluster_id on every line — verified.)
6. CSV D46 check matched a quoted `"severity"` header — the header is bare `severity`; the check found its own bug. Also rewrote the `grep -q && fail` pipeline (an early-closing grep could SIGPIPE `sort` and silently miss a real violation).
7. PIT-leak asserted `==0` immediately — but the smoke deliberately opens abandoned first-page cursors whose PITs linger till keep_alive (inherent to pagination). Proved completed reads (contributors/facets/CSV) leak 0 PITs; the check now asserts *completed reads add no PIT*.

**loadbreak.py:**
8. `no_auth` sent `headers={}` through `headers or auth` — `{}` is Python-falsy → resent the token. True no-auth → 401 (verified). Helper now distinguishes `None` from `{}`.
9. scope tests used an uppercase cluster_id / a trivy body with scanner flipped → both 422 on validation *before* the 403 scope check. With valid-shape inputs both correctly 403.
10. D40 ordering replay ran on a load-hammered token (setup pushes 429'd) and built a `shrunk` envelope with inconsistent counts (422). On a fresh token with consistent counts: stale replay → present=1 (watermark held).
11. LOAD classified persistent-429 (correct load-shedding) as a hard failure. Reclassified: fail only on 5xx / non-2xx-non-429 / no-accepts; shed is reported, not fatal.
12. (post-run review) LOAD's summary labeled ATTEMPT counts as envelope counts — "8000 envelopes, 3600 shed" was really 5000 envelopes / 8000 HTTP attempts, with 3600 attempt-level 429s and only 600 envelopes actually shed (each of those after 6 backoff attempts; the other 429s belonged to envelopes that retried and landed). Reporting fixed (`envelopes_sent` vs `http_attempts`); verdict logic was unaffected. The shed itself is arithmetic, not a bug: 20 tokens pushed 250 envelopes each in ~108 s (~139/min demand) against the 120/min/token limiter — no in-window retry can beat a rate limit; the real scanner's next CronJob cycle (D30 rescans everything) is the system-level retry.

Bench idempotency note (pre-existing, not blocking): `bench_read.py` rotates its reader passwords on
first run (must_change), so a second run on the same store can't re-login — run it against a fresh store.
