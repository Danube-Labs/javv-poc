# JAVV scanner

In-cluster vulnerability scanner. Discovers running images, scans each with **Trivy** and **Grype**
(per-scanner, **never merged**), normalizes severity, builds a current-only envelope, and pushes it to
the backend. Bolt: `development/bolts/M0-scanners/README.md` (issue #22).

```
discovery → adapters(trivy|grype) → normalize → envelope → push
```

## Trivy and Grype are two separate CronJobs
Each scanner is its own self-built image (`Dockerfile.trivy`, `Dockerfile.grype`) run as its **own
CronJob** — independent, never merged. Each emits its own envelope stream with a monotonic `scan_order`
per `(cluster, scanner)`. They may run at the same wall-clock time (independent Jobs) but neither knows
about the other; disagreement (e.g. Trivy=0 vs Grype=73 on the same image) is **signal**, not an error.
`concurrencyPolicy: Forbid` is **per-CronJob**, which is what keeps each scanner's `scan_order` monotonic
(D40). Within one run, images are scanned **sequentially** (stateless; intra-run parallelism is a possible
later optimization, not designed in).

## Runtime & failure modes
Status: ✅ implemented · 🔜 `push.py` · 🔬 live verification · 🏗 M10 (Helm/CronJob/PVC).

| Scenario | What happens | Mechanism / decision | Status |
|---|---|---|---|
| Push fails transiently (429/503, network) | Retry with **exponential backoff + jitter**; same envelope re-sent | only flow control without a broker | 🔜 |
| Push fails permanently (4xx, retries exhausted) | Envelope written to a **dead-letter sink** (`*.dead-letter.jsonl`); run continues | nothing silently lost | 🔜 |
| Push "timed out" but backend got it | Safe re-push — backend **upserts by deterministic `_id`** = `hash(scan_run_id+image_digest+scanner)` | idempotent appends (D18) | 🔜 / server M1 |
| Scanner crashes mid-run | Committed pushes stand (idempotent); next CronJob run re-scans from scratch | stateless, scan-ALL (D30) | 🏗 |
| A run overruns the next schedule | Next run is **skipped** (not queued) | `concurrencyPolicy: Forbid` → monotonic `scan_order` | 🏗 |
| Backend fully down | Pushes retry → dead-letter; Job exits non-zero; "running at T" still shows last committed run | commit-then-cache: no push = no partial state (D39) | 🔜 / 🏗 |
| Clean image (0 vulns) | **Still emits a full envelope** (`total:0`) + scan-events commit doc | no skip-unchanged (D30); catalog needs the marker | ✅ |
| Pod pending / digest unresolved | Image **ignored this cycle**, retried next once `image_id` resolves | discovery requires a `sha256:` digest | ✅ |
| N replicas of one image | Scanned **once**, attributed to all locations | digest-dedup (D30) | ✅ |
| Same digest across namespaces | One scan target spanning both | dedup keyed on digest | ✅ |
| kube API unreachable at start | Discovery raises → run fails fast → next CronJob retry | injected client; fail-fast | ✅ (raises) / 🏗 retry |
| Vuln-DB unavailable (offline) | Scan uses the **cached DB from a PVC**; succeeds without upstream | M10 PVC cache | 🏗 |
| Trivy vs Grype disagree | Both kept verbatim, **never merged** | per-scanner sacred | ✅ |

**"Fails to push, then what?"** transient → backoff retry; permanent → dead-letter (preserved for replay);
either way the backend never sees a partial commit, and the next cycle re-scans and re-pushes anyway because
the scanner holds no state.

## Dev
```bash
cd scanner
uv sync --all-extras --dev
uv run pytest && uv run ruff check . && uv run pyright
```
Tests run against frozen golden fixtures in `tests/fixtures/` (no live scanner/DB calls).
