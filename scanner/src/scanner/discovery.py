"""Enumerate running images from the kube API and dedup by content digest (D30).

The scanner is stateless: every cycle it lists running pods, pulls each container's
content-addressed digest from `container_statuses.image_id`, and collapses pods sharing a digest
into one scan target (N pods → 1 scan). All distinct digests are returned every cycle — there is
no skip-unchanged. The kube client is injected so this is unit-testable without a live cluster.
"""

from collections.abc import Iterable
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict


class Location(BaseModel):
    model_config = ConfigDict(frozen=True)  # frozen → hashable, dedups cleanly

    namespace: str
    pod: str
    container: str


class ImageTarget(BaseModel):
    model_config = ConfigDict(frozen=True)

    image_digest: str  # content-addressed (sha256:…)
    image_ref: str  # human tag, e.g. nginx:1.21.6
    locations: tuple[Location, ...]  # every pod/container running this digest

    @property
    def pod_count(self) -> int:
        return len({(loc.namespace, loc.pod) for loc in self.locations})

    @property
    def namespaces(self) -> tuple[str, ...]:
        """Distinct namespaces this digest runs in (a digest can span several)."""
        return tuple(sorted({loc.namespace for loc in self.locations}))


class _PodSource(Protocol):
    def list_pod_for_all_namespaces(self, *, watch: bool = ...) -> Any: ...


def _digest(image_id: str) -> str | None:
    """Extract the sha256 content digest from a container status `image_id`, or None.

    Handles `docker-pullable://repo@sha256:…`, `repo@sha256:…`, and a bare `sha256:…`.
    """
    s = image_id
    if "://" in s:
        s = s.split("://", 1)[1]
    if "@" in s:
        s = s.split("@", 1)[1]
    return s if s.startswith("sha256:") else None


def running_images(pods: Iterable[Any] | None) -> list[ImageTarget]:
    by_digest: dict[str, dict[str, Any]] = {}
    for p in pods or []:
        status = getattr(p, "status", None)
        if status is None or getattr(status, "phase", None) != "Running":
            continue
        for cs in getattr(status, "container_statuses", None) or []:
            digest = _digest(getattr(cs, "image_id", "") or "")
            if digest is None:
                continue
            entry = by_digest.setdefault(digest, {"ref": cs.image or "", "locs": set()})
            entry["locs"].add(
                Location(namespace=p.metadata.namespace, pod=p.metadata.name, container=cs.name)
            )
    return [
        ImageTarget(
            image_digest=digest,
            image_ref=entry["ref"],
            locations=tuple(
                sorted(entry["locs"], key=lambda loc: (loc.namespace, loc.pod, loc.container))
            ),
        )
        for digest, entry in sorted(by_digest.items())
    ]


def discover(api: _PodSource) -> list[ImageTarget]:
    return running_images(api.list_pod_for_all_namespaces(watch=False).items)
