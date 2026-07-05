"""Envelope → documents, written in commit-then-cache order (D39): images append →
scan-events commit doc → watermark CAS → findings cache last. All `_id`s are deterministic (D18) so
a re-push of the same envelope is idempotent. The findings cache is a **partial-doc merge** (D31, M3
slice 2 — scanner fields refresh, human fields survive; see `services.merge`), gated by the
per-digest **watermark CAS** (D40, M3 slice 3 — a stale/out-of-order run skips the cache entirely;
see `services.watermarks`), then **reconciled** (D37/D38, M3 slice 5 — findings the fresh run
omitted flip `present=false` so resolved CVEs leave the "now" grid; see `services.reconcile`).
"""

import hashlib
from datetime import UTC, datetime
from typing import Any

from opensearchpy import AsyncOpenSearch

from backend.models.envelope import IngestEnvelope
from backend.repositories.bulk import bulk_write
from backend.services.aliases import ensure_write_alias
from backend.services.disagreement import (
    count_pair,
    latest_committed_total,
    recompute_disagreement,
)
from backend.services.merge import merge_action
from backend.services.reconcile import reconcile_absent
from backend.services.watermarks import advance_watermark


def _h(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _repo_tag(image_ref: str) -> tuple[str, str]:
    """nginx:1.21.6 → (nginx, 1.21.6); digest-only/untagged refs get tag ''."""
    if "@" in image_ref:
        return image_ref.split("@", 1)[0], ""
    if ":" in image_ref:
        repo, tag = image_ref.rsplit(":", 1)
        if "/" not in tag:
            return repo, tag
    return image_ref, ""


def build_docs(env: IngestEnvelope) -> dict[str, Any]:
    """All docs + ids for one envelope. Pure — unit-testable without OpenSearch."""
    repo, tag = _repo_tag(env.image_ref)
    counts = env.counts.model_dump()
    commit_key = _h(env.cluster_id, env.scanner, env.image_digest, env.scan_run_id)
    ts = env.last_seen_at.isoformat()
    # SERVER-stamped append time (task F m-4): the retention clock must never trust the
    # client-supplied @timestamp — a backdated scanner clock could age-out recent data
    ingested_at = datetime.now(UTC).isoformat()

    findings = []
    for f in env.findings:
        finding_key = _h(
            env.cluster_id,
            env.image_digest,
            env.scanner,
            f.vuln_id,
            f.package_name,
            f.package_version,
        )
        findings.append(
            {
                "finding_key": finding_key,
                "cluster_id": env.cluster_id,
                "scanner": env.scanner,
                "image_digest": env.image_digest,
                "image_repo": repo,
                "tag": tag,
                "namespaces": env.namespaces,
                "cve_id": f.vuln_id,
                "package_name": f.package_name,
                "installed_version": f.package_version,
                "severity": f.severity,  # verbatim (D16); lc normalizer folds for aggs
                "severity_rank": f.severity_rank,  # server-derived, never the client's
                "cvss": f.cvss,
                "fixable": f.fixable,
                "fixed_version": f.fixed_version,
                "epss": f.epss,
                "kev": f.kev,
                "first_seen_at": ts,  # naive in M1; M3's partial-merge preserves it
                "last_seen_at": ts,
                "last_scan_run_id": env.scan_run_id,
                "last_scan_order": env.scan_order,
                "last_scan_at": ts,
                "present": True,
                "state": "open",
                "schema_version": env.schema_version,
            }
        )

    scan_event = {
        "@timestamp": ts,
        "ingested_at": ingested_at,
        "scan_run_id": env.scan_run_id,
        "scan_order": env.scan_order,
        "commit_key": commit_key,
        "cluster_id": env.cluster_id,
        "scanner": env.scanner,
        "scanner_version": env.scanner_version,
        "scanner_db_version": env.scanner_db_version,
        "scanner_db_built": env.scanner_db_built.isoformat() if env.scanner_db_built else None,
        "namespaces": env.namespaces,
        "image_repo": repo,
        "image_digest": env.image_digest,
        "tag": tag,
        # what the cycle ran with (D44/FR-25) — run-level, scan-events only, display/audit
        "effective_config": env.effective_config.model_dump(mode="json"),
        **counts,
        "schema_version": env.schema_version,
    }
    image = {
        "@timestamp": ts,
        "ingested_at": ingested_at,
        "scan_run_id": env.scan_run_id,
        "cluster_id": env.cluster_id,
        "image_digest": env.image_digest,
        "image_repo": repo,
        "tag": tag,
        "namespaces": env.namespaces,
        "scanners": [env.scanner],
        **counts,
        "replicas": env.replicas,
        "schema_version": env.schema_version,
    }
    return {
        "findings": findings,
        "scan_event": scan_event,
        "scan_event_id": _h(env.scan_run_id, env.image_digest, env.scanner),
        "image": image,
        "image_id": _h(env.scan_run_id, env.image_digest),
        "commit_key": commit_key,
    }


async def ingest_envelope(client: AsyncOpenSearch, env: IngestEnvelope, *, prefix: str = "") -> int:
    """Write one envelope in commit-then-cache order (D39). Returns findings written.
    `prefix` isolates index names (tests only), same convention as `bootstrap`."""
    docs = build_docs(env)
    # append writes go through the series write alias (M4/n-2): ISM rollover retargets the
    # backing index (-000001, -000002, …) and this code never changes
    seq = f"{prefix}javv-scan-events-{env.cluster_id}"
    img = f"{prefix}javv-images-{env.cluster_id}"
    await ensure_write_alias(client, seq)
    await ensure_write_alias(client, img)

    # 1) history append: the image inventory doc — decorated with the D5b count pair when the
    #    OTHER scanner has a committed scan of this digest (as-of-append; single scanner = no pair)
    other = "grype" if env.scanner == "trivy" else "trivy"
    other_total = await latest_committed_total(
        client, env.cluster_id, other, env.image_digest, prefix=prefix
    )
    docs["image"] |= count_pair(env.scanner, env.counts.total, other_total)
    await bulk_write(client, [{"index": {"_index": img, "_id": docs["image_id"]}}, docs["image"]])
    # 2) the commit doc — the catalog marker; a clean scan (0 findings) still commits (D30)
    await bulk_write(
        client,
        [{"index": {"_index": seq, "_id": docs["scan_event_id"]}}, docs["scan_event"]],
    )
    # 3a) advance the per-digest watermark (CAS at commit, D40) — the create+update guard; a
    #     stale/out-of-order run (scan_order < max_committed) skips ALL cache writes so it can never
    #     resurrect a since-retired finding (history above is idempotent + scan_order-ordered)
    fresh = await advance_watermark(
        client,
        env.cluster_id,
        env.scanner,
        env.image_digest,
        env.scan_order,
        env.last_seen_at,
        prefix=prefix,
    )
    if not fresh:
        return 0
    # 3b) cache: partial-doc merge — scanner fields refresh, human fields survive (D31)
    actions: list[dict[str, Any]] = []
    for doc in docs["findings"]:
        actions += merge_action(doc, index=f"{prefix}findings")
    written = await bulk_write(client, actions)
    # 3c) reconcile-on-commit — findings of this digest omitted by the fresh run flip present=false
    #     (+ resolved_at) so resolved CVEs leave the "now" grid immediately; cache-only, history
    #     stays tombstone-free (D37/D38). Runs even for a 0-finding clean scan (whole image fixed).
    await reconcile_absent(
        client,
        env.cluster_id,
        env.scanner,
        env.image_digest,
        env.scan_order,
        env.last_seen_at,
        prefix=prefix,
    )
    # 3d) D5a severity-disagreement flags — recomputed for the whole digest AFTER merge+reconcile
    #     (fresh presence), so reconvergence / a dropped finding clears the flag on both sides
    await recompute_disagreement(client, env.cluster_id, env.image_digest, prefix=prefix)
    return written
