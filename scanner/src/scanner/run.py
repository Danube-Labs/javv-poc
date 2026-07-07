"""One scan cycle: discover running images, drive the configured scanner against each, and push
the envelopes. A single ScanRun is shared across the whole cycle (one scan_run_id + scan_order),
so every image in this run sorts together (D40). The scan and push functions are injected so the
cycle is unit-testable; `main()` wires the real kube client, scanner binaries, and HTTP client.
"""

import os
import re
import time
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import structlog

from scanner.discovery import ImageTarget, discover
from scanner.envelope import EffectiveConfig, Envelope, Scanner, build_envelope, new_scan_run
from scanner.inventory import commit_inventory
from scanner.models import ScanResult
from scanner.orders import fetch_scan_order
from scanner.push import PushResult, push_envelope
from scanner.scope import fetch_scan_scope

ScanFn = Callable[[str], ScanResult]
PushFn = Callable[[Envelope], PushResult]
# cycle-end inventory certification (M8a slice 2): (scan_run_id, expected_count, started_at)
CommitFn = Callable[[str, int, datetime], object]

log = structlog.get_logger()


def scan_all(
    targets: Iterable[ImageTarget],
    *,
    scanner: Scanner,
    cluster_id: str,
    scan_fn: ScanFn,
    push_fn: PushFn,
    scan_order: int,
    effective_config: EffectiveConfig | None = None,
    commit_fn: CommitFn | None = None,
) -> list[PushResult]:
    run = new_scan_run(scan_order)  # backend-allocated (D45) — the cycle's ordering key
    structlog.contextvars.bind_contextvars(scan_run_id=run.scan_run_id, scan_order=scan_order)
    cycle_started_at = datetime.now(UTC)
    targets = list(targets)
    results: list[PushResult] = []
    for i, t in enumerate(targets, start=1):
        # D30: scan everything every cycle. One un-pullable image, a scanner non-zero exit, or a
        # subprocess timeout must not abort the rest of the cycle — isolate it, log, and continue.
        # Per-image progress at INFO (#156): a big image can scan for minutes looking hung.
        log.info(
            "scanning image",
            image_ref=t.image_ref,
            image_digest=t.image_digest,
            position=f"{i}/{len(targets)}",
        )
        started = time.monotonic()
        try:
            scanned = scan_fn(t.image_ref)
        except Exception:
            log.warning(
                "scan failed, image skipped",
                image_ref=t.image_ref,
                image_digest=t.image_digest,
                exc_info=True,
            )
            continue
        log.info(
            "scan done",
            image_ref=t.image_ref,
            findings=len(scanned.findings),
            duration_s=round(time.monotonic() - started, 2),
        )
        envelope = build_envelope(
            run,
            cluster_id=cluster_id,
            scanner=scanner,
            image_digest=t.image_digest,
            image_ref=t.image_ref,
            namespaces=t.namespaces,
            replicas=t.pod_count,
            findings=scanned.findings,
            provenance=scanned.provenance,
            effective_config=effective_config,
        )
        results.append(push_fn(envelope))
    if commit_fn is not None:
        # cycle-end inventory certification (M8a slice 2, D39): expected = every DISCOVERED image
        # — a scan failure or dead-letter leaves the run partial, deliberately never "committed"
        commit_fn(run.scan_run_id, len(targets), cycle_started_at)
    return results


def main() -> int:
    import httpx
    from javv_common.logging import configure_logging
    from kubernetes import client, config

    from scanner.adapters.grype import scan_grype
    from scanner.adapters.trivy import scan_trivy, trivy_db_info
    from scanner.config import GrypeConfig, TrivyConfig

    configure_logging()  # JAVV_LOG_LEVEL, same pipeline as the backend (#156)

    scanner_env = os.environ.get("JAVV_SCANNER", "trivy")
    if scanner_env not in ("trivy", "grype"):  # a typo must not silently run grype (#97)
        log.error("unknown JAVV_SCANNER", value=scanner_env, want="trivy|grype")
        return 2
    scanner: Scanner = cast(Scanner, scanner_env)
    backend = os.environ.get("JAVV_BACKEND_URL", "http://localhost:8000")
    if not backend.startswith(("http://", "https://")):  # else httpx fails as a silent skip
        log.error("invalid JAVV_BACKEND_URL", value=backend, want="http(s)://…")
        return 2
    env_cluster_id = os.environ.get("JAVV_CLUSTER_ID")
    if env_cluster_id and not re.fullmatch(r"[a-z0-9-]{8,64}", env_cluster_id):
        # mirrors the backend's shape rule — garbage here would 422 on every push
        log.error(
            "invalid JAVV_CLUSTER_ID", value=env_cluster_id, want="lowercase alnum/hyphen, 8-64"
        )
        return 2
    # bearer token — effectively required: without it the scope fetch 401s and every cycle skips
    token = os.environ.get("JAVV_TOKEN")
    dead_letter = Path(os.environ.get("JAVV_DEAD_LETTER", f"{scanner}.dead-letter.jsonl"))

    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()
    api = client.CoreV1Api()

    # Tenant identity = the immutable kube-system namespace UID (never cluster_name).
    # kubernetes-client return types are untyped unions; cast for the attribute access.
    kube_system = cast(Any, api.read_namespace("kube-system"))
    cluster_id = env_cluster_id or str(kube_system.metadata.uid)
    # every line of this cycle carries who/where (merged by the shared pipeline)
    structlog.contextvars.bind_contextvars(scanner=scanner, cluster_id=cluster_id)

    # scan-behaviour config from JAVV_TRIVY_*/JAVV_GRYPE_* env (#91); defaults = the pinned command.
    scan_fn: ScanFn
    tuning: TrivyConfig | GrypeConfig
    if scanner == "trivy":
        tuning = trivy_cfg = TrivyConfig.from_env()
        trivy_db = trivy_db_info()  # once per cycle, best-effort vuln-DB provenance (#96)
        scan_fn = lambda ref: scan_trivy(ref, config=trivy_cfg, db=trivy_db)  # noqa: E731
    else:
        tuning = grype_cfg = GrypeConfig.from_env()
        scan_fn = lambda ref: scan_grype(ref, config=grype_cfg)  # noqa: E731

    with httpx.Client(base_url=backend, timeout=30.0) as http:
        # D43/FR-24: fetch the cluster's scan scope first. Fail-closed — if the backend is
        # unreachable we can't confirm what to scan (and couldn't push anyway), so skip the cycle.
        # A fetched *empty* scope means scan everything (handled by the discovery filter).
        scope = fetch_scan_scope(http, token=token)
        if scope is None:
            log.error("scan scope unavailable (backend unreachable) — skipping cycle")
            return 0
        # D45: the backend mints the cycle's ordering key — same fail-closed contract as scope
        scan_order = fetch_scan_order(http, token=token)
        if scan_order is None:
            log.error("scan_order allocation failed (backend) — skipping cycle")
            return 0
        targets = discover(api, scope)
        results = scan_all(
            targets,
            scanner=scanner,
            cluster_id=cluster_id,
            scan_fn=scan_fn,
            push_fn=lambda e: push_envelope(
                e, client=http, dead_letter_path=dead_letter, token=token
            ),
            scan_order=scan_order,
            # D44/FR-25: stamp what this cycle ran with (tuning flags + the applied scope)
            effective_config=EffectiveConfig(tuning=tuning, scope=scope),
            # M8a slice 2: certify the cycle's inventory at the end (best-effort — see inventory.py)
            commit_fn=lambda run_id, expected, started: commit_inventory(
                http,
                token=token,
                scan_run_id=run_id,
                expected_count=expected,
                started_at=started,
            ),
        )

    delivered = sum(1 for r in results if r.delivered)
    log.info(
        "cycle complete",
        scanned=len(results),
        delivered=delivered,
        dead_lettered=len(results) - delivered,
    )
    return 0
