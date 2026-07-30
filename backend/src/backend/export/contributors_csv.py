"""CSV rendering of the contributors leaderboard (issue 359).

Unlike the findings/audit exports this is NOT a PIT sweep: the leaderboard is a terms
aggregation the route has already computed, so the rows are in hand and bounded by the board's
own size. The export re-drives the SAME payload the screen reads — one code path, so the file
and the screen can never disagree.

The per-action split becomes one column per action of the closed triage vocabulary, prefixed
`action_` so a bare `note`/`assign` header can't be mistaken for a metric. Fixed columns in a
fixed order: a spreadsheet pivot breaks when columns appear and vanish with the data.
"""

import csv
import io
from collections.abc import Iterator
from typing import Any

from backend.export.csv_stream import csv_line
from backend.query.contributors import TRIAGE_ACTIONS

_ACTION_COLUMNS = tuple(f"action_{action}" for action in sorted(TRIAGE_ACTIONS))

CONTRIBUTORS_CSV_COLUMNS = (
    "actor",
    "actions",
    "handled",
    "median_ttr_seconds",
    "sla_hit_pct",
    *_ACTION_COLUMNS,
)


def stream_contributors_csv(payload: dict[str, Any]) -> Iterator[str]:
    """Header, then one line per contributor — the leaderboard in the payload's own order
    (the aggregation's, which is the screen's before its client-side sort).

    Measures stay at wire precision rather than the screen's rounded display: the file is
    data to compute on, and a reader can always round.
    """
    # the header cells are OUR constants, not data — `csv_line` would apostrophe-quote any
    # leading `-`/`=` as a formula trigger (the audit_csv lesson)
    header = io.StringIO()
    csv.writer(header, lineterminator="\n").writerow(CONTRIBUTORS_CSV_COLUMNS)
    yield header.getvalue()

    for row in payload["leaderboard"]:
        by_action = row.get("by_action") or {}
        yield csv_line(
            [
                row.get("actor"),
                row.get("actions"),
                row.get("handled"),
                row.get("median_ttr_seconds"),
                row.get("sla_hit_pct"),
                *(by_action.get(action, 0) for action in sorted(TRIAGE_ACTIONS)),
            ]
        )
