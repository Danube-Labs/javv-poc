"""Human-auth passwords (M5a slice 1, FR-18/SEC-6): argon2id hash/verify, the length-based
password policy, and the dummy-hash used to kill the username timing oracle at login. Pure units —
no OpenSearch. The hash is the only thing ever stored; the raw password exists only in the request.
"""

import pytest

from backend.auth.passwords import DUMMY_HASH, check_policy, hash_password, verify_password

PASSWORD = "correct horse battery staple"  # 28 chars, policy-clean


def test_hash_verify_roundtrip() -> None:
    stored = hash_password(PASSWORD)
    assert verify_password(PASSWORD, stored) is True


def test_wrong_password_fails() -> None:
    stored = hash_password(PASSWORD)
    assert verify_password("wrong horse battery staple", stored) is False


def test_hash_is_argon2id_and_salted() -> None:
    a, b = hash_password(PASSWORD), hash_password(PASSWORD)
    assert a.startswith("$argon2id$")
    assert a != b  # per-hash salt — equal passwords never share a hash


def test_hash_never_contains_the_password() -> None:
    assert PASSWORD not in hash_password(PASSWORD)


def test_dummy_hash_verifies_false_without_raising() -> None:
    # login runs verify_password against DUMMY_HASH when the user doesn't exist, so response
    # time can't reveal whether a username is taken — it must behave like any failed verify
    assert verify_password(PASSWORD, DUMMY_HASH) is False


def test_garbage_stored_hash_is_a_clean_false() -> None:
    # a corrupted/legacy row must fail closed, not 500
    assert verify_password(PASSWORD, "not-a-hash") is False
    assert verify_password(PASSWORD, "") is False


# --- policy (length-based, NIST-style — no composition gimmicks) --------------------


def test_policy_accepts_a_long_passphrase() -> None:
    check_policy(PASSWORD)  # must not raise


@pytest.mark.parametrize("bad", ["", "short", "elevenchars"])
def test_policy_rejects_under_minimum(bad: str) -> None:
    with pytest.raises(ValueError, match="12"):
        check_policy(bad)


def test_policy_rejects_absurd_length() -> None:
    with pytest.raises(ValueError, match="256"):
        check_policy("x" * 257)
