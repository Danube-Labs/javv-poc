"""Token admin API (M5a slice 6, D38/M14) — the capability-gated (`can_manage_tokens`) surface
over the EXISTING ingest-token machinery (`core/security.py` crypto, SEC-3 binding at ingest);
one token path only, the CLI (`core/tokens.py`) stays for bootstrap use. The raw token appears
exactly once — in the mint/rotate response — and is never recoverable. Revoke = `disabled:true`
(the ingest 401s on its next push); rotate = mint-new + disable-old in that order (a rotation
never leaves the scanner with zero valid tokens; the staleness sweep already dedupes rotated
tokens per audit M-2). Every mutation is journaled (D17). Registered in the standing RBAC/IDOR
suite (`tests/security/test_rbac_idor_contract.py`)."""

from datetime import UTC, datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from opensearchpy import NotFoundError
from pydantic import BaseModel, ConfigDict, Field

from backend.audit.writer import append_auth_event
from backend.auth.capabilities import require_capability
from backend.auth.principal import Principal
from backend.core.security import hash_token, mint_token
from backend.core.settings import get_settings

router = APIRouter(prefix="/api/v1/admin/tokens", tags=["token-admin"])

TOKENS_INDEX = "system-tokens"
_PUBLIC_FIELDS = (  # never token_hash — the hash never leaves the server either
    "cluster_id",
    "scanner",
    "scope",
    "created_by",
    "created_at",
    "expiry",
    "disabled",
    "last_ingest_at",
)

ManageTokens = Annotated[Principal, Depends(require_capability("can_manage_tokens"))]


class MintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cluster_id: str = Field(min_length=1, max_length=256)
    scanner: str = Field(pattern="^(trivy|grype)$")  # per-scanner is sacred — no other value


def _os(request: Request) -> Any:
    return cast(Any, request.app.state.opensearch)


def _public(token_id: str, doc: dict[str, Any]) -> dict[str, Any]:
    return {"id": token_id, **{k: doc.get(k) for k in _PUBLIC_FIELDS}}


async def _mint_doc(
    client: Any, *, cluster_id: str, scanner: str, created_by: str
) -> tuple[str, str]:
    """Create a token doc; returns (doc_id, RAW token) — the raw value's only server-side moment."""
    raw = mint_token()
    doc = {
        "token_hash": hash_token(raw, pepper=get_settings().token_pepper),
        "cluster_id": cluster_id,
        "scanner": scanner,
        "scope": "push:findings",
        "created_by": created_by,
        "created_at": datetime.now(UTC).isoformat(),
        "disabled": False,
    }
    resp = await client.index(index=TOKENS_INDEX, body=doc, params={"refresh": "true"})
    return resp["_id"], raw


@router.get("")
async def list_tokens(
    request: Request, principal: ManageTokens, cluster_id: str | None = None
) -> dict[str, Any]:
    filters: list[dict[str, Any]] = []
    if cluster_id:
        filters.append({"term": {"cluster_id": cluster_id}})
    hits = await _os(request).search(
        index=TOKENS_INDEX,
        body={"size": 10_000, "query": {"bool": {"filter": filters}}},
    )
    return {"tokens": [_public(h["_id"], h["_source"]) for h in hits["hits"]["hits"]]}


@router.post("", status_code=201)
async def mint(request: Request, body: MintRequest, principal: ManageTokens) -> dict[str, Any]:
    client = _os(request)
    token_id, raw = await _mint_doc(
        client, cluster_id=body.cluster_id, scanner=body.scanner, created_by=principal.user_id
    )
    await append_auth_event(
        client,
        actor=principal.user_id,
        action="token_mint",
        entity_type="token",
        entity_id=token_id,
        cluster_id=body.cluster_id,
    )
    return {"id": token_id, "token": raw}  # shown once — not recoverable


@router.post("/{token_id}/revoke")
async def revoke(request: Request, token_id: str, principal: ManageTokens) -> dict[str, Any]:
    client = _os(request)
    doc = await _load(client, token_id)
    await client.update(
        index=TOKENS_INDEX,
        id=token_id,
        body={"doc": {"disabled": True}},
        params={"refresh": "true"},
    )
    await append_auth_event(
        client,
        actor=principal.user_id,
        action="token_revoke",
        entity_type="token",
        entity_id=token_id,
        cluster_id=doc.get("cluster_id"),
    )
    return {"id": token_id, "disabled": True}


@router.post("/{token_id}/rotate", status_code=201)
async def rotate(request: Request, token_id: str, principal: ManageTokens) -> dict[str, Any]:
    """Mint the sibling FIRST, then disable the old — the scanner is never token-less."""
    client = _os(request)
    old = await _load(client, token_id)
    new_id, raw = await _mint_doc(
        client,
        cluster_id=old["cluster_id"],
        scanner=old["scanner"],
        created_by=principal.user_id,
    )
    await client.update(
        index=TOKENS_INDEX,
        id=token_id,
        body={"doc": {"disabled": True}},
        params={"refresh": "true"},
    )
    for action, entity in (("token_mint", new_id), ("token_revoke", token_id)):
        await append_auth_event(
            client,
            actor=principal.user_id,
            action=action,
            entity_type="token",
            entity_id=entity,
            cluster_id=old["cluster_id"],
        )
    return {"id": new_id, "token": raw}


async def _load(client: Any, token_id: str) -> dict[str, Any]:
    try:
        return (await client.get(index=TOKENS_INDEX, id=token_id))["_source"]
    except NotFoundError:
        raise HTTPException(404, "token not found") from None
