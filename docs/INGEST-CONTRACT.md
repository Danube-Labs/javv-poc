# JAVV public ingest contract

How to push scan results into JAVV **without running the JAVV scanners** — from any
environment that can produce the envelope JSON (Kubernetes, Nomad, plain Docker hosts, CI
pipelines). This is the "cheap now" slice of #327: the wire schema, the call protocol, and the
validation rules, published and CI-pinned. What it does **not** yet give you: a scanner
identity of your own (see [Current limitation](#current-limitation-the-scanner-vocabulary)).

The machine-readable schema lives beside this file:
**[`ingest-envelope.schema.json`](ingest-envelope.schema.json)** — generated from the backend's
Pydantic wire model (`backend/src/backend/models/envelope.py::IngestEnvelope`) and pinned by a
CI test (`backend/tests/test_ingest_contract_doc.py`), so it cannot drift from what the server
actually enforces. Regeneration command: in that test's docstring.

## The protocol — four calls

| Step | Call | Auth | When |
|---|---|---|---|
| 0 | `GET/POST /api/v1/admin/tokens` — mint a machine token scoped to your `(cluster_id, scanner)` | admin session (`can_manage_tokens`), or `python -m backend.core.tokens` | once (rotate/revoke via the admin API) |
| 1 | `POST /api/v1/scan-runs` → `{"scan_order": <int>}` | machine token | once per scan **cycle**, before pushing |
| 2 | `POST /api/v1/ingest/scan` — one envelope per image | machine token | per image in the cycle |
| 3 | `POST /api/v1/inventory-runs` — body `{"scan_run_id", "expected_count", "started_at"}` | machine token | once at cycle **end** |

Notes that keep the data model honest:

- **`scan_order` comes from step 1 — never invent it.** It is the strictly-increasing
  per-`(cluster, scanner)` ordering key (D45) that the whole correctness model sorts by; every
  envelope in the cycle carries the same `scan_order` + your own `scan_run_id`.
- **Scan everything, every cycle** (D30): the model is stateless full sweeps — the server
  reconciles what a committed run no longer reports. Do not push incremental diffs.
- **Step 3 certifies the cycle**: `expected_count` = images you discovered; the server counts
  what actually landed and marks the inventory run `committed` only if complete. Without it,
  "running at T" queries won't trust the cycle.
- The token is **scope-bound** (SEC-3): a payload whose `cluster_id`/`scanner` doesn't match
  the token's scope is a `403`, not a shrug.

## Portable field semantics (nothing here is Kubernetes-specific)

| Field | What it really is |
|---|---|
| `cluster_id` | Any **stable, immutable** environment id — lowercase alnum/hyphen, 8–64 chars. It routes storage; never rename it (labels/display names live elsewhere). |
| `namespaces` | Plain `list[str]` grouping labels for where the image runs. Kube namespaces for us; **Nomad job names, compose project names, host groups** all slot straight in. |
| `replicas` | Instance count of the image in that grouping — any integer ≥ 0. |
| `image_digest` | `sha256:<hex>` — the content identity everything dedupes on. |
| `last_seen_at` etc. | Timestamps must be **timezone-aware** ISO-8601 (`…Z` or offset). |
| `severity` | The scanner's **verbatim** word (D16 raw fidelity). The server derives the canonical bucket itself and never trusts `severity_canonical` from the wire (send it anyway — the schema requires it; verbatim-lowercase is fine). |
| `effective_config` | The tuning + scope the cycle actually ran with — audit/display only, but **required** and its `tuning` shape must match `scanner`. |

## Validation — what gets you a 422 (and friends)

The envelope is validated with `extra="forbid"` at every level: an unknown field anywhere is a
rejection, not a warning. The specific tripwires:

- **Counts invariant**: `counts.total` must equal the six severity buckets' sum **and**
  `len(findings)`. (Bucket *column names* are the historical `crit/med` shorthand; severity
  *values* are always full words.)
- **`cluster_id` shape** (it flows into index names — injection guard): lowercase
  alnum/hyphen, 8–64 chars.
- **`image_digest`**: must match `^sha256:[a-fA-F0-9]{6,64}$`.
- **`scanner` ↔ `effective_config.tuning` mismatch** (a trivy envelope with grype tuning is a
  lying client).
- **`schema_version`** outside the accepted window (currently 3 or 4 — the M8d `ptype`
  rollout; v3 findings simply have no `ptype`).
- Naive (timezone-less) timestamps.

The full error table for `POST /ingest/scan` (400/401/403/413/422/429/503, gzip support, size
caps) is in [`API.md`](API.md) § "the hardened surface". Success is `202` with
`{accepted, findings, commit}` — and pushes are **idempotent** (deterministic doc ids): safe to
retry a failed cycle.

## Worked example

A complete, minimal envelope (1 finding — a real one validated by the golden fixture family;
`backend/tests/fixtures/envelope-trivy-v3-golden.json` is the fuller 29-finding template):

```bash
TOKEN=…            # from step 0, scoped to (my-nomad-fleet-01, trivy)
ORDER=$(curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  https://javv.example/api/v1/scan-runs | jq .scan_order)

curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  https://javv.example/api/v1/ingest/scan -d @- <<EOF
{
  "schema_version": 4,
  "cluster_id": "my-nomad-fleet-01",
  "scanner": "trivy",
  "image_digest": "sha256:aa11bb22cc33dd44ee55ff667788990011223344556677889900aabbccddeeff",
  "image_ref": "python:3.9.16-slim",
  "namespaces": ["billing-job"],
  "replicas": 3,
  "scan_run_id": "cycle-2026-07-10-a",
  "scan_order": $ORDER,
  "last_seen_at": "2026-07-10T12:00:00Z",
  "scanner_version": "0.71.2",
  "scanner_db_version": "2",
  "scanner_db_built": "2026-07-10T01:09:26Z",
  "effective_config": {
    "tuning": {
      "scanners": "vuln",
      "ignore_unfixed": false,
      "severities": null,
      "pkg_types": null,
      "timeout": null
    },
    "scope": {
      "include_namespaces": [],
      "ignore_namespaces": [],
      "exclude_images": [],
      "ignore_kinds": []
    }
  },
  "counts": {
    "crit": 0, "high": 1, "med": 0, "low": 0,
    "negligible": 0, "unknown": 0, "total": 1, "fixable": 1
  },
  "findings": [
    {
      "vuln_id": "CVE-2024-5535",
      "package_name": "openssl",
      "package_version": "1.1.1n-0+deb11u2",
      "severity": "HIGH",
      "cvss": 9.1,
      "fixable": true,
      "fixed_version": "1.1.1w-0+deb11u2",
      "epss": null,
      "kev": false,
      "ptype": "deb",
      "severity_canonical": "high"
    }
  ]
}
EOF

# cycle end — certify the inventory (expected_count = images you discovered this cycle)
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  https://javv.example/api/v1/inventory-runs \
  -d "{\"scan_run_id\": \"cycle-2026-07-10-a\", \"expected_count\": 1, \"started_at\": \"2026-07-10T11:55:00Z\"}"
```

## Current limitation: the scanner vocabulary

`scanner` is `"trivy" | "grype"` — **a third-party pusher must produce trivy- or
grype-compatible output and push AS that scanner** (mint the token for it, match its tuning
shape). This is deliberate for now: per-scanner-is-sacred (never merged, never deduped) means
every scanner value is a facet across the entire system — normalizer coverage (D16),
disagreement pairing, per-scanner tokens. Opening the vocabulary is a **v1.1 ruling**
(a registered-scanner registry, not a free string) tracked on
[#327](https://github.com/Danube-Labs/javv-poc/issues/327); a `generic` tuning shape rides the
same ruling. If you're wrapping a different engine (Snyk, Clair, …) today, map its output onto
one of the two identities and pin your mapping — or wait for the vocabulary.

## Related

- [`API.md`](API.md) — full endpoint reference (auth, error tables, metrics).
- `docs/engineering/INDEX-MAP.md` — where the data lands.
- D16 (raw-fidelity normalizer) · D30 (stateless full sweeps) · D45 (`scan_order`) ·
  SEC-3 (token scope-binding) · M8d/#241 (next envelope bump — schema doc and bump travel together).
