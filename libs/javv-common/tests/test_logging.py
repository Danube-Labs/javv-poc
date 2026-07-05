"""The shared logging pipeline (#156): one structlog config for every JAVV component.

Pins the three contracts the package exists for:
1. **Level filtering** — `JAVV_LOG_LEVEL` (or an explicit arg) is a real threshold; debug lines
   cost nothing until asked for. An unknown level fails fast (config-error house style).
2. **Redaction** — the security control that must never fork: sensitive keys masked, `Bearer …`
   scrubbed in values. Deliberately BROAD on key names (fail-safe): a non-secret key like
   `system-tokens` is masked too — fix noisy call sites, never loosen the regex.
3. **The stdlib bridge** — uvicorn / opensearch-py / kubernetes-client records join the same
   JSON stream (same redaction, same contextvars); per-request `opensearch` lines are
   DEBUG-gated so INFO stays readable, and `opensearchpy.trace` (request BODIES) is always off.
"""

import json
import logging

import pytest
import structlog

from javv_common.logging import REDACTED, configure_logging, redact_processor


@pytest.fixture(autouse=True)
def _reset_logging():
    """Each test configures its own pipeline; leave no cached loggers or handlers behind."""
    yield
    structlog.reset_defaults()
    root = logging.getLogger()
    root.handlers.clear()
    for name in ("opensearch", "opensearchpy.trace", "uvicorn", "uvicorn.access", "test.bridge"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.setLevel(logging.NOTSET)
        lg.propagate = True


def _lines(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


# --- level filtering ---------------------------------------------------------


def test_debug_is_suppressed_at_info_level(capsys) -> None:
    configure_logging(level="info")
    log = structlog.get_logger()
    log.debug("hidden")
    log.info("shown")
    events = [e["event"] for e in _lines(capsys.readouterr().out)]
    assert "hidden" not in events
    assert "shown" in events


def test_debug_is_emitted_at_debug_level(capsys) -> None:
    configure_logging(level="debug")
    structlog.get_logger().debug("visible", detail=42)
    (line,) = _lines(capsys.readouterr().out)
    assert line["event"] == "visible"
    assert line["level"] == "debug"
    assert line["detail"] == 42
    assert line["timestamp"]  # ISO stamp present


def test_level_comes_from_env_when_not_passed(capsys, monkeypatch) -> None:
    monkeypatch.setenv("JAVV_LOG_LEVEL", "warning")
    configure_logging()
    log = structlog.get_logger()
    log.info("hidden")
    log.warning("shown")
    events = [e["event"] for e in _lines(capsys.readouterr().out)]
    assert events == ["shown"]


def test_unknown_level_fails_fast() -> None:
    with pytest.raises(ValueError, match="(?i)log level"):
        configure_logging(level="verbose")


# --- redaction (the security control that must never fork) -------------------


def test_redact_masks_sensitive_keys_and_scrubs_bearer_anywhere() -> None:
    event = {
        "event": "ingest",
        "authorization": "Bearer super-secret-abc123",
        "token_pepper": "p3pp3r",
        "note": "saw header Bearer leaked-token-xyz here",
        "nested": {"api_token": "t0k", "ok": "fine"},
        "safe": "nginx:1.21.6",
    }
    out = redact_processor(None, "info", event)
    assert out["authorization"] == REDACTED
    assert out["token_pepper"] == REDACTED
    assert "leaked-token-xyz" not in out["note"] and REDACTED in out["note"]
    assert out["nested"]["api_token"] == REDACTED and out["nested"]["ok"] == "fine"
    assert out["safe"] == "nginx:1.21.6"


def test_redaction_is_broad_by_design_a_nonsecret_key_containing_token_is_masked() -> None:
    """The e2e smoke's `"system-tokens": "created"` case (#156 finding 2). RULING: keep the
    broad key match — fail-safe beats precision for a security control. The fix for noisy
    lines is the CALL SITE (log names as list values), never loosening this regex."""
    out = redact_processor(None, "info", {"event": "bootstrap", "system-tokens": "created"})
    assert out["system-tokens"] == REDACTED  # masked even though the value is harmless


def test_redaction_applies_to_emitted_structlog_lines(capsys) -> None:
    configure_logging(level="info")
    structlog.get_logger().info("mint", token="raw-secret-value")
    (line,) = _lines(capsys.readouterr().out)
    assert line["token"] == REDACTED


# --- the stdlib bridge --------------------------------------------------------


def test_stdlib_records_come_out_as_redacted_json(capsys) -> None:
    configure_logging(level="info")
    logging.getLogger("test.bridge").warning("upstream said Bearer oops-a-token here")
    (line,) = _lines(capsys.readouterr().err)
    assert line["level"] == "warning"
    assert "oops-a-token" not in line["event"] and REDACTED in line["event"]
    assert line["timestamp"]


def test_stdlib_bridge_respects_the_level(capsys) -> None:
    configure_logging(level="warning")
    logging.getLogger("test.bridge").info("hidden")
    logging.getLogger("test.bridge").error("shown")
    events = [e["event"] for e in _lines(capsys.readouterr().err)]
    assert events == ["shown"]


def test_contextvars_appear_on_stdlib_lines_too(capsys) -> None:
    configure_logging(level="info")
    structlog.contextvars.bind_contextvars(scanner="trivy")
    try:
        logging.getLogger("test.bridge").warning("bridged")
    finally:
        structlog.contextvars.clear_contextvars()
    (line,) = _lines(capsys.readouterr().err)
    assert line["scanner"] == "trivy"


# --- opensearch client gating -------------------------------------------------


def test_opensearch_per_request_lines_are_hidden_at_info(capsys) -> None:
    configure_logging(level="info")
    logging.getLogger("opensearch").info("GET /findings [status:200]")
    assert _lines(capsys.readouterr().err) == []


def test_opensearch_per_request_lines_show_at_debug(capsys) -> None:
    configure_logging(level="debug")
    logging.getLogger("opensearch").info("GET /findings [status:200]")
    (line,) = _lines(capsys.readouterr().err)
    assert "findings" in line["event"]


def test_opensearch_trace_bodies_never_emit_even_at_debug(capsys) -> None:
    configure_logging(level="debug")
    logging.getLogger("opensearchpy.trace").info('{"query": {"term": {"secret": "x"}}}')
    assert _lines(capsys.readouterr().err) == []


def test_opensearch_bodies_never_emit_even_at_debug(capsys) -> None:
    """The client logs full request/response BODIES at its own DEBUG level — one real scan cycle
    produced a 6 MB log (#158). The per-request lines (INFO) are the debug feature; bodies are
    banned at every threshold, same ruling as `opensearchpy.trace`."""
    configure_logging(level="debug")
    logging.getLogger("opensearch").debug('> {"huge": "request body"}')
    assert _lines(capsys.readouterr().err) == []
