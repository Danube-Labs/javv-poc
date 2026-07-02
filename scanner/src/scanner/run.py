"""One scan cycle: discover running images, drive the configured scanner against each, and push
the envelopes. A single ScanRun is shared across the whole cycle (one scan_run_id + scan_order),
so every image in this run sorts together (D40). The scan and push functions are injected so the
cycle is unit-testable; `main()` wires the real kube client, scanner binaries, and HTTP client.
"""

import os
import re
import sys
import traceback
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, cast

from scanner.discovery import ImageTarget, discover
from scanner.envelope import EffectiveConfig, Envelope, Scanner, build_envelope, new_scan_run
from scanner.models import ScanResult
from scanner.push import PushResult, push_envelope
from scanner.scope import fetch_scan_scope

ScanFn = Callable[[str], ScanResult]
PushFn = Callable[[Envelope], PushResult]


def scan_all(
    targets: Iterable[ImageTarget],
    *,
    scanner: Scanner,
    cluster_id: str,
    scan_fn: ScanFn,
    push_fn: PushFn,
    effective_config: EffectiveConfig | None = None,
) -> list[PushResult]:
    run = new_scan_run()
    results: list[PushResult] = []
    for t in targets:
        # D30: scan everything every cycle. One un-pullable image, a scanner non-zero exit, or a
        # subprocess timeout must not abort the rest of the cycle — isolate it, log, and continue.
        try:
            scanned = scan_fn(t.image_ref)
        except Exception:
            print(
                f"{scanner}: scan failed for {t.image_ref} ({t.image_digest}) — skipping:",
                file=sys.stderr,
            )
            traceback.print_exc()
            continue
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
    return results


def main() -> int:
    import httpx
    from kubernetes import client, config

    from scanner.adapters.grype import scan_grype
    from scanner.adapters.trivy import scan_trivy, trivy_db_info
    from scanner.config import GrypeConfig, TrivyConfig

    scanner_env = os.environ.get("JAVV_SCANNER", "trivy")
    if scanner_env not in ("trivy", "grype"):  # a typo must not silently run grype (#97)
        print(f"unknown JAVV_SCANNER: {scanner_env!r} (want trivy|grype)", file=sys.stderr)
        return 2
    scanner: Scanner = cast(Scanner, scanner_env)
    backend = os.environ.get("JAVV_BACKEND_URL", "http://localhost:8000")
    if not backend.startswith(("http://", "https://")):  # else httpx fails as a silent skip
        print(f"invalid JAVV_BACKEND_URL: {backend!r} (want http(s)://…)", file=sys.stderr)
        return 2
    env_cluster_id = os.environ.get("JAVV_CLUSTER_ID")
    if env_cluster_id and not re.fullmatch(r"[a-z0-9-]{8,64}", env_cluster_id):
        # mirrors the backend's shape rule — garbage here would 422 on every push
        print(
            f"invalid JAVV_CLUSTER_ID: {env_cluster_id!r} (want lowercase alnum/hyphen, 8-64)",
            file=sys.stderr,
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
            print(
                f"{scanner}: scan scope unavailable (backend unreachable) — skipping cycle",
                file=sys.stderr,
            )
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
            # D44/FR-25: stamp what this cycle ran with (tuning flags + the applied scope)
            effective_config=EffectiveConfig(tuning=tuning, scope=scope),
        )

    delivered = sum(1 for r in results if r.delivered)
    print(
        f"{scanner}: scanned {len(results)} image(s) — "
        f"{delivered} delivered, {len(results) - delivered} dead-lettered",
        file=sys.stderr,
    )
    return 0
