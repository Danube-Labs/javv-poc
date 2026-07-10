"""The published ingest contract (docs/ingest-envelope.schema.json) must never drift from the
wire model — the schema file is GENERATED from `IngestEnvelope.model_json_schema()` and this
test is the CI gate that keeps the two identical. Regenerate after any envelope change:

    cd backend && uv run python -c "
    import json
    from backend.models.envelope import IngestEnvelope
    with open('../docs/ingest-envelope.schema.json', 'w') as f:
        json.dump(IngestEnvelope.model_json_schema(), f, indent=2, sort_keys=True)
        f.write('\\n')"
"""

import json
from pathlib import Path

from backend.models.envelope import IngestEnvelope

SCHEMA_DOC = Path(__file__).parents[2] / "docs" / "ingest-envelope.schema.json"


def test_published_schema_matches_the_wire_model() -> None:
    committed = json.loads(SCHEMA_DOC.read_text())
    generated = IngestEnvelope.model_json_schema()
    assert committed == generated, (
        "docs/ingest-envelope.schema.json drifted from IngestEnvelope — regenerate it "
        "(command in this file's docstring) and commit both in the same PR"
    )


def test_golden_fixture_validates_against_the_published_contract() -> None:
    # the worked example in docs/INGEST-CONTRACT.md derives from this fixture — if the fixture
    # stops validating, the doc's example is lying too
    fixture = Path(__file__).parent / "fixtures" / "envelope-trivy-v3-golden.json"
    IngestEnvelope.model_validate_json(fixture.read_text())
