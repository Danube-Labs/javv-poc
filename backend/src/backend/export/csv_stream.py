"""Streaming CSV export (M6 slice 5, FR-13 inline "run now" path).

Every cell goes through `sanitize_cell`: a STRING whose first character is one of
`=`, `+`, `-`, `@`, tab, CR would execute as a formula when the CSV lands in a spreadsheet
(CSV injection), so it's neutralized with a leading apostrophe — the value stays readable,
the formula never arms. Non-strings can't be formulas and serialize plainly (bools lowercase
to match the JSON wire shape; lists — `namespaces` — join on `;`).

Rows stream one at a time over the constant-memory sweep (`export/sweep.py`); nothing buffers
the full result. Scheduled/throttled exports (`system-reports`) are M7 — this is the inline path.
"""

import csv
import io
from collections.abc import AsyncIterator
from typing import Any

from opensearchpy import AsyncOpenSearch

from backend.export.sweep import sweep_findings
from backend.query.search import SearchFilters

_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")

CSV_COLUMNS = (
    "finding_key",
    "cluster_id",
    "scanner",
    "cve_id",
    "severity",
    "state",
    "vex_justification",
    "package_name",
    "installed_version",
    "fixed_version",
    "fixable",
    "kev",
    "epss",
    "cvss",
    "image_repo",
    "tag",
    "image_digest",
    "namespaces",
    "assignee",
    "first_seen_at",
    "last_seen_at",
    "last_scan_at",
    "present",
    "state_decision_id",
)


def sanitize_cell(value: Any) -> str:
    """One cell → its injection-safe string form."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ";".join(sanitize_cell(v) for v in value)
    text = value if isinstance(value, str) else str(value)
    if isinstance(value, str) and text.startswith(_FORMULA_TRIGGERS):
        return f"'{text}"
    return text


def csv_line(values: list[Any] | tuple[Any, ...]) -> str:
    """One sanitized, csv-quoted line (including the trailing newline)."""
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerow([sanitize_cell(v) for v in values])
    return buf.getvalue()


async def stream_csv(
    client: AsyncOpenSearch, *, cluster_id: str, filters: SearchFilters
) -> AsyncIterator[str]:
    """Header, then one line per finding in the lens — never the buffered whole."""
    yield csv_line(CSV_COLUMNS)
    async for doc in sweep_findings(client, cluster_id=cluster_id, filters=filters):
        yield csv_line([doc.get(col) for col in CSV_COLUMNS])
