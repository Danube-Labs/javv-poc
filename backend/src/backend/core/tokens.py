"""Mint an ingest token (admin CLI, M1-minimal — the API/RBAC path is M5a).

    uv run python -m backend.core.tokens --cluster <cluster_id> --scanner trivy

Prints the RAW token exactly once; only its peppered SHA-256 lands in `system-tokens` (D38/M14).
"""

import argparse
import asyncio
from datetime import UTC, datetime

from opensearchpy import AsyncOpenSearch

from backend.core.security import hash_token, mint_token
from backend.core.settings import get_settings


async def mint(cluster_id: str, scanner: str) -> str:
    settings = get_settings()
    token = mint_token()
    doc = {
        "token_hash": hash_token(token, pepper=settings.token_pepper),
        "cluster_id": cluster_id,
        "scanner": scanner,
        "scope": "push:findings",
        "created_by": "cli",
        "created_at": datetime.now(UTC).isoformat(),
        "disabled": False,
    }
    client = AsyncOpenSearch(hosts=[settings.opensearch_url])
    try:
        await client.index(index="system-tokens", body=doc, params={"refresh": "true"})
    finally:
        await client.close()
    return token


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Mint a JAVV ingest token")
    ap.add_argument("--cluster", required=True)
    ap.add_argument("--scanner", required=True, choices=["trivy", "grype"])
    args = ap.parse_args()
    from backend.core.identifiers import validate_cluster_id  # shared shape (task E/Codex M2)

    validate_cluster_id(args.cluster)
    raw = asyncio.run(mint(args.cluster, args.scanner))
    print(raw)  # shown once — store it in the scanner's Secret; it is not recoverable
