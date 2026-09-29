"""`GET /api/v1/meta`: what this backend is running (issue 261). Behind login on purpose: `/readyz`
stays anonymous for the Kubernetes probe, so the version must not ride on it. Operators without a
session read the same numbers from the `bootstrap complete` log line."""

from typing import Annotated, Any, get_args

from fastapi import APIRouter, Depends

from backend.auth.principal import Principal, get_current_principal
from backend.core.bootstrap import MAPPING_VERSION
from backend.models.envelope import IngestEnvelope
from backend.version import APP_VERSION

router = APIRouter(prefix="/api/v1/meta", tags=["meta"])

Authenticated = Annotated[Principal, Depends(get_current_principal)]

ENVELOPE_VERSIONS: list[int] = sorted(
    get_args(IngestEnvelope.model_fields["schema_version"].annotation)
)


@router.get("")
async def get_meta(principal: Authenticated) -> dict[str, Any]:
    return {
        "version": APP_VERSION,
        "mapping_version": MAPPING_VERSION,
        "envelope_versions": ENVELOPE_VERSIONS,
    }
