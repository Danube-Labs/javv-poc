"""Every stored-setting reader goes through the lenient parser (issue 640).

The parametrized test feeds each of the seven readers a stored document carrying a field the
running release doesn't know, and expects a value, not a `ValidationError`. The guard fails the
build when code outside `core/stored_settings.py` validates a stored `_source` value directly, so
a new setting can't bring the rollback 500 back."""

import ast
from pathlib import Path
from typing import Any

import pytest

from backend.admin.report_ttl import REPORT_TTL_KEY, read_report_ttl_hours
from backend.admin.scan_scope import read_scan_scope
from backend.admin.snapshot import SNAPSHOT_REPO_KEY, read_snapshot_repo_ref
from backend.core import stored_settings
from backend.jobs.findings_cleanup import FINDINGS_CLEANUP_KEY, read_findings_cleanup_setting
from backend.jobs.lifecycle import LIFECYCLE_KEY, read_lifecycle_settings
from backend.jobs.staleness import STALENESS_KEY, read_staleness_timers
from backend.sla.policy import SLA_KEY, read_sla_policy

SRC = Path(__file__).resolve().parents[1] / "src" / "backend"


class _OneDocClient:
    """Answers `get` for one system-config doc id; anything else raises (a reader that asks for a
    different doc would surface here rather than silently read nothing)."""

    def __init__(self, doc_id: str, value: dict[str, Any]) -> None:
        self.doc_id = doc_id
        self.value = value

    async def get(self, *, index: str, id: str) -> dict[str, Any]:
        assert index == "system-config" and id == self.doc_id, (index, id)
        return {"_source": {"key": id, "value": self.value}}


READERS = [
    ("sla", SLA_KEY, {"critical_days": 3}, lambda c: read_sla_policy(c)),
    (
        "scan_scope",
        "scan_scope:c1",
        {"ignore_kinds": ["Job"]},
        lambda c: read_scan_scope(c, "c1"),
    ),
    (
        "snapshot_repo",
        SNAPSHOT_REPO_KEY,
        {"repository": "r", "type": "fs", "settings": {"location": "/snap"}},
        lambda c: read_snapshot_repo_ref(c),
    ),
    ("report_ttl", REPORT_TTL_KEY, {"hours": 12}, lambda c: read_report_ttl_hours(c)),
    ("lifecycle", LIFECYCLE_KEY, {"retention_days": 60}, lambda c: read_lifecycle_settings(c)),
    (
        "findings_cleanup",
        FINDINGS_CLEANUP_KEY,
        {"cleanup_days": 90},
        lambda c: read_findings_cleanup_setting(c),
    ),
    ("staleness", STALENESS_KEY, {"freshness_days": 5}, lambda c: read_staleness_timers(c)),
]


@pytest.mark.parametrize(("name", "doc_id", "known", "read"), READERS, ids=[r[0] for r in READERS])
async def test_each_reader_drops_a_field_this_release_lacks(
    monkeypatch, name, doc_id, known, read
) -> None:
    monkeypatch.setattr(stored_settings, "_warned", set())
    with_extra = await read(_OneDocClient(doc_id, {**known, "added_later": 1}))
    without = await read(_OneDocClient(doc_id, known))
    assert with_extra == without
    assert doc_id in stored_settings._warned


def _direct_stored_validations(path: Path) -> list[int]:
    """Lines calling `<X>.model_validate(<expr containing a "_source" subscript>)`."""
    hits = []
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "model_validate"
            and node.args
        ):
            continue
        for sub in ast.walk(node.args[0]):
            if (
                isinstance(sub, ast.Subscript)
                and isinstance(sub.slice, ast.Constant)
                and sub.slice.value == "_source"
            ):
                hits.append(node.lineno)
                break
    return hits


def test_no_stored_setting_is_validated_outside_the_lenient_parser() -> None:
    offenders = [
        f"{path.relative_to(SRC)}:{line}"
        for path in sorted(SRC.rglob("*.py"))
        if path.name != "stored_settings.py"
        for line in _direct_stored_validations(path)
    ]
    assert offenders == [], (
        "validate stored settings with backend.core.stored_settings.parse_stored_setting, "
        f"so a rollback can still read them: {offenders}"
    )


def test_the_guard_catches_the_old_pattern(tmp_path) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text('x = Timers.model_validate(got["_source"]["value"])\n')
    assert _direct_stored_validations(sample) == [1]
