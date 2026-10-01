"""The pinned schema snapshot (`frontend/openapi.json`) is the API's shape, not its release.

The app stamps its running version into the live schema, and release-please bumps that version in
`version.py` on every release PR. If the snapshot carried it too, every release PR would fail the
contract gate, since nothing regenerates the snapshot there.
"""

from __future__ import annotations

import json

from backend.main import app
from backend.tools.export_openapi import SNAPSHOT_VERSION, export
from backend.version import APP_VERSION


def test_snapshot_pins_a_fixed_version_not_the_release() -> None:
    assert json.loads(export())["info"]["version"] == SNAPSHOT_VERSION
    assert SNAPSHOT_VERSION != APP_VERSION


def test_the_live_schema_still_reports_the_running_version() -> None:
    export()
    assert app.openapi()["info"]["version"] == APP_VERSION
