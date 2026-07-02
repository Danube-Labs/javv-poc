"""Ingest-token primitives (D38/M14): 256-bit random tokens, stored only as peppered SHA-256,
verified with a constant-time compare. The raw token exists once — at mint time — and is never
logged or persisted."""

import hashlib
import hmac
import secrets


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
