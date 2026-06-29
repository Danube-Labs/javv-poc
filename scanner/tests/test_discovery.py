"""Discovery enumerates running images from the kube API and dedups by content digest (D30):
N pods of the same digest collapse to one scan target, but every distinct digest is scanned
every cycle (stateless — no skip-unchanged). The digest comes from `container_statuses.image_id`
(content-addressed); pods without a resolved digest or not Running are ignored."""

from types import SimpleNamespace as NS

from scanner.discovery import ImageTarget, discover, running_images

DIG_NGINX = "sha256:" + "a" * 64
DIG_PY = "sha256:" + "b" * 64
DIG_ALPINE = "sha256:" + "c" * 64


def cstatus(name: str, image: str, image_id: str) -> NS:
    return NS(name=name, image=image, image_id=image_id)


def pod(ns: str, name: str, statuses: list[NS] | None, phase: str = "Running") -> NS:
    return NS(
        metadata=NS(namespace=ns, name=name),
        status=NS(phase=phase, container_statuses=statuses),
    )


def test_dedups_replicas_of_one_image_to_a_single_target() -> None:
    # The seed manifest's case: 3 nginx pods (one digest) → 1 scan, across 3 image_id formats.
    pods = [
        pod(
            "javv-smoke",
            "nginx-1",
            [cstatus("nginx", "nginx:1.21.6", f"docker-pullable://nginx@{DIG_NGINX}")],
        ),
        pod("javv-smoke", "nginx-2", [cstatus("nginx", "nginx:1.21.6", f"nginx@{DIG_NGINX}")]),
        pod("javv-smoke", "nginx-3", [cstatus("nginx", "nginx:1.21.6", DIG_NGINX)]),
        pod("javv-smoke", "py-1", [cstatus("python", "python:3.9.16-slim", f"python@{DIG_PY}")]),
    ]
    by_digest = {t.image_digest: t for t in running_images(pods)}
    assert set(by_digest) == {DIG_NGINX, DIG_PY}
    assert by_digest[DIG_NGINX].pod_count == 3
    assert by_digest[DIG_NGINX].image_ref == "nginx:1.21.6"
    assert by_digest[DIG_PY].pod_count == 1


def test_same_digest_across_namespaces_is_one_target_spanning_both() -> None:
    pods = [
        pod("ns-a", "p1", [cstatus("c", "img:1", f"img@{DIG_ALPINE}")]),
        pod("ns-b", "p2", [cstatus("c", "img:1", f"img@{DIG_ALPINE}")]),
    ]
    targets = running_images(pods)
    assert len(targets) == 1
    assert {loc.namespace for loc in targets[0].locations} == {"ns-a", "ns-b"}
    assert targets[0].pod_count == 2


def test_ignores_pods_without_a_resolved_digest_or_not_running() -> None:
    pods = [
        pod("ns", "pending", None, phase="Pending"),  # not scheduled yet
        pod("ns", "no-digest", [cstatus("c", "img:1", "")]),  # image_id not resolved
        pod("ns", "tag-only", [cstatus("c", "img:1", "img:1")]),  # no sha256 digest
        pod("ns", "succeeded", [cstatus("c", "img:1", f"img@{DIG_PY}")], phase="Succeeded"),
    ]
    assert running_images(pods) == []


def test_handles_empty_input() -> None:
    assert running_images([]) == []
    assert running_images(None) == []  # type: ignore[arg-type]


def test_output_is_deterministically_ordered() -> None:
    pods = [
        pod("ns", "b", [cstatus("c", "z", f"z@{DIG_PY}")]),
        pod("ns", "a", [cstatus("c", "a", f"a@{DIG_NGINX}")]),
    ]
    digests = [t.image_digest for t in running_images(pods)]
    assert digests == sorted(digests)


def test_discover_pulls_pods_from_the_api_and_dedups() -> None:
    pods = [
        pod("javv-smoke", "nginx-1", [cstatus("nginx", "nginx:1.21.6", f"nginx@{DIG_NGINX}")]),
        pod("javv-smoke", "nginx-2", [cstatus("nginx", "nginx:1.21.6", f"nginx@{DIG_NGINX}")]),
    ]

    class FakeApi:
        def list_pod_for_all_namespaces(self, *, watch: bool = False) -> NS:
            return NS(items=pods)

    targets = discover(FakeApi())
    assert len(targets) == 1
    assert isinstance(targets[0], ImageTarget)
    assert targets[0].pod_count == 2
