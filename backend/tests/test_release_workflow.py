"""The release run's publish job, read from `.github/workflows/release-please.yml` (issue 615).

A release signs only on a real run (keyless cosign needs the job's OIDC token), so no CI job can
exercise it. These tests hold its shape instead:
- only the publishing job can get a signing identity;
- each pushed digest gets an SBOM, a signature and an attestation, before anyone pulls it;
- the release verifies, signed out, with the identity `docs/DEPLOYING.md` gives operators.
"""

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "release-please.yml"
DEPLOYING = ROOT / "docs" / "DEPLOYING.md"
SIGN_ACTION = "./.github/actions/sign-image"


def _workflow() -> dict[Any, Any]:
    return yaml.safe_load(WORKFLOW.read_text())


def _steps(job: str) -> list[dict[str, Any]]:
    return _workflow()["jobs"][job]["steps"]


def _step(job: str, name: str) -> dict[str, Any]:
    return next(s for s in _steps(job) if s.get("name") == name)


def test_only_the_app_image_publish_job_can_get_a_signing_identity() -> None:
    workflow = _workflow()
    assert "id-token" not in workflow["permissions"]
    signers = {
        name
        for name, job in workflow["jobs"].items()
        if (job.get("permissions") or {}).get("id-token") == "write"
    }
    assert signers == {"publish-app-images"}


def test_each_pushed_digest_is_signed_and_attested_before_anyone_pulls_it() -> None:
    names = [s.get("name") or s.get("uses") for s in _steps("publish-app-images")]
    sign = next(s for s in _steps("publish-app-images") if s.get("uses") == SIGN_ACTION)
    order = [
        "Push both images",
        "An SBOM of each pushed digest",
        sign["name"],
        "Anyone can pull them",
        "Anyone can verify them",
    ]
    where = [names.index(name) for name in order]
    assert where == sorted(where)

    # the push step records digests, the SBOM step reads those, and the action signs its list
    push = _step("publish-app-images", "Push both images")
    assert '"$app=$REGISTRY/javv-$app@$digest"' in push["run"]
    sbom = _step("publish-app-images", "An SBOM of each pushed digest")
    assert sbom["env"] == {
        "BACKEND": "${{ steps.push.outputs.backend }}",
        "FRONTEND": "${{ steps.push.outputs.frontend }}",
    }
    assert sign["with"]["images"] == "${{ steps.sbom.outputs.images }}"


def test_the_release_verifies_with_the_identity_the_docs_give() -> None:
    workflow = _workflow()
    # PyYAML reads the key `on` as True
    assert workflow[True] == {"push": {"branches": ["main"]}}
    verify = _step("publish-app-images", "Anyone can verify them")["env"]
    assert verify["IDENTITY"] == (
        r"^https://github\.com/Danube-Labs/javv-poc/\.github/workflows/release-please\.yml"
        r"@refs/heads/main$"
    )
    assert verify["ISSUER"] == "https://token.actions.githubusercontent.com"

    docs = DEPLOYING.read_text()
    section = docs.split("## Verify the images", 1)[1].split("\n## ", 1)[0]
    identity = re.search(r"^IDENTITY='(.+)'$", section, re.M)
    issuer = re.search(r"^ISSUER=(\S+)$", section, re.M)
    assert identity and issuer
    assert (identity[1], issuer[1]) == (verify["IDENTITY"], verify["ISSUER"])
