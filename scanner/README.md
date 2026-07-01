# JAVV scanner

In-cluster vulnerability scanner. Discovers running images, scans each with **Trivy** and **Grype**
(per-scanner, **never merged**), normalizes severity, builds a current-only envelope (stamped with the
scanner's self-reported version provenance), and pushes it to the backend.
Bolts: M0 (`development/bolts/M0-scanners/`, #22) · M0b publish/compat (`…/M0b-scanner-image-publish/`, #60).

```
discovery → adapters(trivy|grype) → normalize → envelope (+scanner_version) → push
```

## Run it
The package is the CronJob entrypoint — one cycle = discover → scan → envelope → push:
```bash
JAVV_SCANNER=trivy JAVV_BACKEND_URL=http://backend python -m scanner
```
| Env | Meaning |
|---|---|
| `JAVV_SCANNER` | `trivy` \| `grype` — which scanner this Job runs (default `trivy`) |
| `JAVV_BACKEND_URL` | ingest endpoint base (default `http://localhost:8000`) |
| `JAVV_CLUSTER_ID` | tenant id; defaults to the live `kube-system` namespace UID |
| `JAVV_DEAD_LETTER` | dead-letter sink path (default `<scanner>.dead-letter.jsonl`) |

## Trivy and Grype are two separate CronJobs
Each scanner is its own self-built image (`Dockerfile.trivy`, `Dockerfile.grype`, pinned binary) run as its
**own CronJob** — independent, never merged. Each emits its own envelope stream with a monotonic `scan_order`
per `(cluster, scanner)`. They may run at the same wall-clock time but neither knows about the other;
disagreement (e.g. Trivy=0 vs Grype=73 on the same image) is **signal**, not an error. `concurrencyPolicy:
Forbid` is **per-CronJob**, which keeps each scanner's `scan_order` monotonic (D40). Within one run, images
are scanned **sequentially** (stateless; intra-run parallelism is a possible later optimization).

## Versions & publishing (M0b / D41–D42)
- **Supported versions** live in [`/versions.yaml`](../versions.yaml) (single source of truth) — `current` +
  a small set of prior versions per scanner. Edit there; Renovate watches it.
- **Compatibility gate:** `python -m scanner.compat --scanner trivy` drives the real binary against a
  CVE-bearing image and asserts the JAVV adapter contracts (provenance present, findings parse, severities
  canonical, envelope builds). CI runs it per supported version; green → publishable.
- **DB-compat policy:** `versions.yaml` records each scanner's factual `vuln_db` compatibility (no invented
  EOL). `development/scripts/check-scanner-db-policy.sh` fails CI if a supported version would run a frozen/
  incompatible vuln DB — e.g. Grype < 0.88.0 (schema v5, EOL 2026-03-06, runs silently).
- **Publish pipeline** (`.github/workflows/scanner-images.yml`, dispatch/tag): builds locally → **publish-smoke**
  (runs each image's entrypoint before pushing) → pushes → **SBOM (`syft`) + self-scan (`grype`, report-only)**
  uploaded as a CI artifact. Cosign signing is deferred until the repo is public (#74).
- **Published images:** `ghcr.io/danube-labs/javv-scanner-{trivy,grype}:<ver>` (moving) + `:<ver>-<git-sha>`
  (immutable) with OCI labels. **Scanner image release ≠ JAVV release** — versions are changed by swapping the
  published image tag in your deploy; JAVV never changes versions in a running cluster (D41).

## Runtime & failure modes
Status: ✅ implemented (M0/M0b) · 🏗 M10 (Helm/CronJob hygiene, PVC vuln-DB cache, RBAC).

| Scenario | What happens | Mechanism / decision | Status |
|---|---|---|---|
| Push fails transiently (429/5xx, network) | Retry with **exponential backoff + jitter**; same envelope re-sent | only flow control without a broker | ✅ |
| Push fails permanently (other 4xx, retries exhausted) | Envelope written to a **dead-letter sink** (`*.dead-letter.jsonl`); run continues | nothing silently lost | ✅ |
| Push "timed out" but backend got it | Safe re-push — gzipped body is byte-identical; backend **upserts by deterministic `_id`** | idempotent appends (D18); server-side M1 | ✅ / M1 |
| Backend fully down | Pushes retry → dead-letter; Job exits non-zero; "running at T" still shows last committed run | commit-then-cache: no push = no partial state (D39) | ✅ / M1 |
| Clean image (0 vulns) | **Still emits a full envelope** (`total:0`) | no skip-unchanged (D30); catalog needs the marker | ✅ |
| Pod pending / digest unresolved | Image **ignored this cycle**, retried next once `image_id` resolves | discovery requires a `sha256:` digest | ✅ |
| N replicas of one image | Scanned **once**, attributed to all locations | digest-dedup (D30) | ✅ |
| Same digest across namespaces | One scan target spanning both | dedup keyed on digest | ✅ |
| kube API unreachable at start | Discovery raises → run fails fast → next CronJob retry | injected client; fail-fast | ✅ / 🏗 retry |
| Scanner crashes mid-run | Committed pushes stand (idempotent); next CronJob run re-scans from scratch | stateless, scan-ALL (D30) | ✅ / 🏗 schedule |
| A run overruns the next schedule | Next run is **skipped** (not queued) | `concurrencyPolicy: Forbid` → monotonic `scan_order` | 🏗 |
| Vuln-DB unavailable (offline) | Scan uses the **cached DB from a PVC**; succeeds without upstream | M10 PVC cache (per-schema, D42) | 🏗 |
| Trivy vs Grype disagree | Both kept verbatim, **never merged** | per-scanner sacred | ✅ |

**"Fails to push, then what?"** transient → backoff retry; permanent → dead-letter (preserved for replay);
either way the backend never sees a partial commit, and the next cycle re-scans and re-pushes anyway because
the scanner holds no state.

## Provenance (D41)
Each envelope stamps the scanner's self-reported **`scanner_version`** (+ vuln-DB version/built where the
scanner provides it — Grype yes, Trivy's standalone JSON no). It's ingested for the read-only scanner-status
version view + audit version matrix; the binary is the source of truth for "what actually ran."

## Dev
```bash
cd scanner
uv sync --all-extras --dev
uv run pytest && uv run ruff check . && uv run pyright
```
Unit tests run against frozen golden fixtures in `tests/fixtures/` (no network). Two **guarded** integration
suites are skipped by default:
- `JAVV_LIVE_VERIFY=1 uv run pytest tests/test_live_verify.py` — discovery + real scans against the k3d
  `alpha` cluster (needs the `javv-smoke` seed workloads).
- `JAVV_COMPAT_VERIFY=1 uv run pytest tests/test_compat.py` — runs the real installed binaries through the
  compatibility gate.
