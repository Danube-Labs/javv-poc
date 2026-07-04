"""argon2id password hashing (M5a, FR-18/SEC-6). The raw password exists only inside the request
handler; only the argon2id hash is stored (`system-users.password_hash`) and neither is ever
logged. Policy is length-based (NIST-style): length is the one factor that provably helps;
composition rules push users to predictable substitutions.

`DUMMY_HASH` kills the username timing oracle: when a login names a user that doesn't exist, the
route verifies the candidate password against this hash anyway, so "unknown user" and "wrong
password" take the same time and return the same generic 401.
"""

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError

MIN_LENGTH = 12
MAX_LENGTH = 256  # argon2 hashes any length; the cap just bounds request work

_hasher = PasswordHasher()  # library defaults track RFC 9106; pinned by the lockfile

DUMMY_HASH = PasswordHasher().hash("javv-dummy-timing-equalizer")


def hash_password(password: str) -> str:
    """argon2id hash with a fresh per-hash salt."""
    return _hasher.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time-comparable verify. Fails CLOSED: a mismatch, a corrupted/legacy hash, or an
    empty value is a clean False (the caller returns the same generic 401 either way)."""
    try:
        return _hasher.verify(stored_hash, password)
    except (Argon2Error, InvalidHashError, ValueError):
        return False


def check_policy(password: str) -> None:
    """Raise ValueError when the password violates policy (message is user-facing)."""
    if len(password) < MIN_LENGTH:
        raise ValueError(f"password must be at least {MIN_LENGTH} characters")
    if len(password) > MAX_LENGTH:
        raise ValueError(f"password must be at most {MAX_LENGTH} characters")
