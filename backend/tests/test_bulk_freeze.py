"""Unit: `freeze_targets` bounding (audit A-Mc/#189) — count-don't-collect.

A selector matching more than `max_targets` must raise `SelectorTooBroad` and bail DURING paging,
never page the whole match into memory. Proven with a fake client that counts search calls and
would hand back far more ids than the cap if asked."""

from typing import Any, cast

import pytest

from backend.triage.bulk import SelectorTooBroad, freeze_targets


class _FakeClient:
    """Returns `total` ids across pages of whatever `size` the caller asks for; records how many
    searches ran and the largest page it was ever asked to pull."""

    def __init__(self, total: int) -> None:
        self.total = total
        self.searches = 0
        self.max_page_asked = 0

        class _Indices:
            async def refresh(self, index: str) -> None:  # noqa: ARG002
                return None

        self.indices = _Indices()

    async def search(self, *, index: str, body: dict) -> dict:  # noqa: ARG002
        self.searches += 1
        size = body["size"]
        self.max_page_asked = max(self.max_page_asked, size)
        start = body.get("search_after", [0])[0]
        hits = [
            {"_id": f"fk-{i}", "sort": [i]} for i in range(start, min(start + size, self.total))
        ]
        return {"hits": {"hits": hits}}


async def test_freeze_bails_during_paging_over_cap() -> None:
    client = _FakeClient(total=1_000_000)  # a whole-cluster selector
    with pytest.raises(SelectorTooBroad):
        await freeze_targets(cast(Any, client), "c1", {"severity": "negligible"}, max_targets=2)
    assert client.searches == 1  # bailed on the first page — never paged the million
    assert client.max_page_asked == 3  # never asked for more than cap+1 per page


async def test_freeze_returns_full_set_under_cap() -> None:
    client = _FakeClient(total=5)
    ids = await freeze_targets(cast(Any, client), "c1", {"cve_id": "CVE-x"}, max_targets=100)
    assert len(ids) == 5
