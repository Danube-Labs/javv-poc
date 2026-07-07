"""M7 slice 3 (#32) — the short-lived signed download token (SEC-10 intent, no object store).

The status view mints it for a `done`, unexpired report; the download endpoint verifies it ON TOP
of the session (belt and braces: a pasted download URL goes stale in minutes even though report
ids are unguessable uuid4 and the endpoint is session-gated anyway). Stateless HMAC over the
deployment pepper — no new secret, no storage. Format: `<exp_epoch>.<hex sig>`.
"""

import hashlib
import hmac
import time

from backend.core.settings import get_settings

TOKEN_TTL_SECONDS = 900  # 15 min — frozen internal constant, refetch the status view for a new one


def _sig(report_id: str, exp: int) -> str:
    pepper = get_settings().token_pepper.encode()
    msg = f"report-download|{report_id}|{exp}".encode()
    return hmac.new(pepper, msg, hashlib.sha256).hexdigest()


def mint(report_id: str, *, now: float | None = None) -> str:
    exp = int(now if now is not None else time.time()) + TOKEN_TTL_SECONDS
    return f"{exp}.{_sig(report_id, exp)}"


def verify(report_id: str, token: str, *, now: float | None = None) -> bool:
    exp_part, _, sig_part = token.partition(".")
    if not exp_part.isdigit() or not sig_part:
        return False
    exp = int(exp_part)
    if (now if now is not None else time.time()) > exp:
        return False
    return hmac.compare_digest(_sig(report_id, exp), sig_part)
