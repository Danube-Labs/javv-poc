"""One scan cycle: discover running images, drive the configured scanner against each, and push
the envelopes. A single ScanRun is shared across the whole cycle (one scan_run_id + scan_order),
so every image in this run sorts together (D40). The scan and push functions are injected so the
cycle is unit-testable; `main()` wires the real kube client, scanner binaries, and HTTP client.
"""

import os
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, cast

from scanner.discovery import ImageTarget, discover
from scanner.envelope import Envelope, Scanner, build_envelope, new_scan_run
from scanner.models import Finding
from scanner.push import PushResult, push_envelope

ScanFn = Callable[[str], list[Finding]]
PushFn = Callable[[Envelope], PushResult]


def scan_all(
    targets: Iterable[ImageTarget],
    *,
    scanner: Scanner,
    cluster_id: str,
    scan_fn: ScanFn,
    push_fn: PushFn,
) -> list[PushResult]:
    run = new_scan_run()
    results: list[PushResult] = []
    for t in targets:
        envelope = build_envelope(
            run,
            cluster_id=cluster_id,
            scanner=scanner,
            image_digest=t.image_digest,
            findings=scan_fn(t.image_ref),
        )
        results.append(push_fn(envelope))
    return results


def main() -> int:
    import httpx
    from kubernetes import client, config

    from scanner.adapters.grype import scan_grype
    from scanner.adapters.trivy import scan_trivy

    scanner: Scanner = os.environ.get("JAVV_SCANNER", "trivy")  # type: ignore[assignment]
    backend = os.environ.get("JAVV_BACKEND_URL", "http://localhost:8000")
    dead_letter = Path(os.environ.get("JAVV_DEAD_LETTER", f"{scanner}.dead-letter.jsonl"))

    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()
    api = client.CoreV1Api()

    # Tenant identity = the immutable kube-system namespace UID (never cluster_name).
    # kubernetes-client return types are untyped unions; cast for the attribute access.
    kube_system = cast(Any, api.read_namespace("kube-system"))
    cluster_id = os.environ.get("JAVV_CLUSTER_ID") or str(kube_system.metadata.uid)
    scan_fn: ScanFn = {"trivy": scan_trivy, "grype": scan_grype}[scanner]

    targets = discover(api)
    with httpx.Client(base_url=backend, timeout=30.0) as http:
        results = scan_all(
            targets,
            scanner=scanner,
            cluster_id=cluster_id,
            scan_fn=scan_fn,
            push_fn=lambda e: push_envelope(e, client=http, dead_letter_path=dead_letter),
        )

    delivered = sum(1 for r in results if r.delivered)
    print(
        f"{scanner}: scanned {len(results)} image(s) — "
        f"{delivered} delivered, {len(results) - delivered} dead-lettered",
        file=sys.stderr,
    )
    return 0
