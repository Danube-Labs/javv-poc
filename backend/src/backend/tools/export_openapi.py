"""Export the FastAPI OpenAPI schema as deterministic JSON (the I4/I7 contract source).

Operator CLI (`python -m backend.tools.export_openapi [out_path]`) — the printed/written schema is
what `frontend/openapi.json` pins and `npm run gen:api` consumes; the CI Frontend gate re-exports
and fails on any diff, so a backend contract change without a client regen breaks the build.
Import-only (no store connection): `app.openapi()` is computed from the route/model definitions.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from backend.main import app


def export() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":  # operator interface — print/write is the point (observability.md A-n)
    schema = export()
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(schema)
        print(f"wrote {sys.argv[1]}")
    else:
        print(schema, end="")
