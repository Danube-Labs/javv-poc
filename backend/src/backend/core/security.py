"""Ingest-token primitives (D38/M14): 256-bit random tokens, stored only as peppered SHA-256,
verified with a constant-time compare. The raw token exists once — at mint time — and is never
logged or persisted."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from typing import Any


def mint_token() -> str:
    """A new 256-bit random bearer token (urlsafe). Shown once; only its hash is stored."""
    return secrets.token_urlsafe(32)


def hash_token(token: str, *, pepper: str) -> str:
    """Peppered SHA-256 (hex). The pepper lives in config, never in the index — DB theft alone
    is not enough to forge a token."""
    return hashlib.sha256((pepper + token).encode()).hexdigest()


def tokens_match(candidate_hash: str, stored_hash: str) -> bool:
    """Constant-time comparison (no timing oracle on the hash tail)."""
    return hmac.compare_digest(candidate_hash, stored_hash)


def token_expired(token: dict[str, Any], *, now: datetime | None = None) -> bool:
    """True if the token doc carries an `expiry` at or before now (audit m-3). A null/absent expiry
    never expires. tz-naive stored values are coerced to UTC (defensive, like the sweep)."""
    exp = token.get("expiry")
    if not exp:
        return False
    dt = datetime.fromisoformat(exp.replace("Z", "+00:00")) if isinstance(exp, str) else exp
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt <= (now or datetime.now(UTC))
