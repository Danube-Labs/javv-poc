"""Scanner-faceted aggregations (M6 slice 2, FR-12) — pure DSL builders.

Two shapes, both `size:0` (counts come from aggregations, raw findings never ship to the
client — server-side-everything):

- **Facets** — capped `terms` over WHITELISTED bounded-vocabulary keyword/bool fields
  (severity/state/scanner/…). Whitelisting is the "never aggregate on `text`" guard (NFR-1)
  made structural.
- **Groups** — one `composite` source over a whitelisted high-cardinality keyword dim
  (image_repo/namespaces/cve_id/…), paginating via `after_key` behind the same opaque-cursor
  contract as search — every bucket is reachable, none silently capped (DoD).

Every bucket carries a `by_scanner` sub-agg: per-scanner is sacred (the UI can always split;
a cross-scanner merge is never forced). The caller's SearchFilters context applies to every
body, and `tenant_query` (the chokepoint) forces the cluster filter on top at execution.
"""

import base64
import binascii
import json
from typing import Any

from backend.query.search import SearchFilters, build_search_body

# bounded-vocabulary fields — capped terms cannot truncate these (NFR-1: keyword/bool only)
FACET_FIELDS = ("severity", "state", "scanner", "fixable", "kev", "disagree", "present", "ptype")
_FACET_TERMS_SIZE = 32  # ≥ the largest facet vocabulary (ptype's ecosystem strings are widest)

# pre-M8d findings carry ptype: null until a v4 sweep re-observes them (D30) — the facet shows
# them as an explicit "unknown" bucket rather than silently dropping the rows (the B-1 caveat)
_FACET_MISSING = {"ptype": "unknown"}

# high-cardinality keyword dims — composite/after_key territory, never a capped terms
GROUP_FIELDS = ("image_repo", "image_digest", "namespaces", "cve_id", "assignee", "app", "ptype")

_BY_SCANNER = {"by_scanner": {"terms": {"field": "scanner", "size": 4}}}


def _base(filters: SearchFilters) -> dict[str, Any]:
    """The filter context, agg-shaped: same facets as the grid, no hits, no sort."""
    body = build_search_body(filters, size=0)
    del body["sort"], body["track_total_hits"]
    return body


def build_facets_body(filters: SearchFilters, fields: list[str] | None = None) -> dict[str, Any]:
    chosen = fields if fields is not None else list(FACET_FIELDS)
    bad = [f for f in chosen if f not in FACET_FIELDS]
    if bad:
        raise ValueError(f"not facetable (whitelist {FACET_FIELDS}): {bad}")
    body = _base(filters)
    body["aggs"] = {
        f: {
            "terms": {
                "field": f,
                "size": _FACET_TERMS_SIZE,
                **({"missing": _FACET_MISSING[f]} if f in _FACET_MISSING else {}),
            },
            "aggs": dict(_BY_SCANNER),
        }
        for f in chosen
    }
    return body


def build_composite_body(
    filters: SearchFilters,
    *,
    by: str,
    size: int,
    after: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if by not in GROUP_FIELDS:
        raise ValueError(f"not groupable (whitelist {GROUP_FIELDS}): {by!r}")
    composite: dict[str, Any] = {
        "sources": [{"key": {"terms": {"field": by}}}],
        "size": size,
    }
    if after is not None:
        composite["after"] = after
    body = _base(filters)
    body["aggs"] = {"groups": {"composite": composite, "aggs": dict(_BY_SCANNER)}}
    return body


def encode_after(after: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(after).encode()).decode()


def decode_after(cursor: str) -> dict[str, Any]:
    try:
        after = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        if not isinstance(after, dict):
            raise ValueError("after cursor must decode to an object")
        # a composite `after_key` is {source: scalar}; a nested/non-scalar value would sail past
        # decode and blow up inside the aggregation (500) — reject the tampered shape here (A-m1)
        if not all(v is None or isinstance(v, (str, int, float, bool)) for v in after.values()):
            raise ValueError("after cursor values must be scalars")
        return after
    except (binascii.Error, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError("invalid cursor") from exc
