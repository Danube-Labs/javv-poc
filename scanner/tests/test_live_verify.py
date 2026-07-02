"""Live-cluster verification (PLAN_v4 §9 / M0 DoD) — the integration smoke the golden-fixture
unit tests can't cover: real discovery against k3d, real digest-dedup, and the real trivy/grype
binaries producing an envelope with actual CVEs.

Skipped by default (never runs in CI). To run:
    kubectl apply -f development/setup/seed-vuln-workloads.yaml   # if not already applied
    JAVV_LIVE_VERIFY=1 uv run pytest tests/test_live_verify.py -v
Requires a running k3d cluster (context k3d-alpha) with the javv-smoke workloads + trivy/grype.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("JAVV_LIVE_VERIFY"),
    reason="live-cluster smoke; set JAVV_LIVE_VERIFY=1 with k3d + javv-smoke workloads running",
)

# k8s reports fully-qualified refs (e.g. docker.io/library/nginx:1.21.6), so match by tag suffix.
SEED_TAGS = {"nginx:1.21.6", "python:3.9.16-slim", "alpine:3.14"}


def _core_v1_api():  # noqa: ANN202
    from kubernetes import client, config

    config.load_kube_config()
    return client.CoreV1Api()


def test_discovery_dedups_seed_workloads_on_the_live_cluster() -> None:
    from scanner.discovery import discover

    targets = discover(_core_v1_api())
    refs = {t.image_ref for t in targets}
    for tag in SEED_TAGS:
        assert any(r.endswith(tag) for r in refs), f"seed image {tag} missing: {refs}"

    # nginx runs as 3 replicas of ONE digest → exactly one target with pod_count 3 (D30 dedup)
    nginx = next(t for t in targets if t.image_ref.endswith("nginx:1.21.6"))
    assert nginx.pod_count == 3
    assert len(nginx.locations) >= 3

    # every target is a distinct digest (dedup collapsed replicas, not images)
    digests = [t.image_digest for t in targets]
    assert len(digests) == len(set(digests))


def test_real_trivy_and_grype_drive_produces_envelope_with_cves() -> None:
    from scanner.adapters.grype import scan_grype
    from scanner.adapters.trivy import scan_trivy
    from scanner.envelope import build_envelope, new_scan_run

    run = new_scan_run(1)  # guarded live test, no backend — any positive order (D45)
    image = "python:3.9.16-slim"  # Debian — Trivy and Grype both find CVEs

    trivy = scan_trivy(image)
    grype = scan_grype(image)
    trivy_env = build_envelope(
        run,
        cluster_id="alpha",
        scanner="trivy",
        image_digest="sha256:live",
        findings=trivy.findings,
        provenance=trivy.provenance,
    )
    grype_env = build_envelope(
        run,
        cluster_id="alpha",
        scanner="grype",
        image_digest="sha256:live",
        findings=grype.findings,
        provenance=grype.provenance,
    )

    # the real binaries found real vulnerabilities
    assert trivy_env.counts.total > 0
    assert grype_env.counts.total > 0
    # per-scanner, never merged — two independent envelopes
    assert trivy_env.scanner == "trivy"
    assert grype_env.scanner == "grype"
    # Grype's EPSS signal survives the full drive→parse→envelope path
    assert any(f.epss is not None for f in grype_env.findings)
    # provenance is self-reported by the real binaries (D41)
    assert trivy_env.scanner_version and grype_env.scanner_version
    assert grype_env.scanner_db_version  # Grype reports its vuln-DB schema; Trivy does not
