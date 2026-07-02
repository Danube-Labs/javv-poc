"""Phase 1 of #91 — env-driven Trivy/Grype scan flags. The contract: an **unset** environment
reproduces the previously-hardcoded command exactly (no behaviour change), and each JAVV_* override
is reflected in the built command. Pure builders — no subprocess."""

import pytest

from scanner.adapters.grype import grype_command
from scanner.adapters.trivy import trivy_command
from scanner.config import GrypeConfig, TrivyConfig

# the exact commands that were hardcoded before #91 — the no-behaviour-change anchors
TRIVY_DEFAULT = ["trivy", "image", "--quiet", "--scanners", "vuln", "--format", "json", "img:1"]
GRYPE_DEFAULT = ["grype", "img:1", "-o", "json"]


# --- defaults reproduce the old command exactly -----------------------------


def test_trivy_default_command_is_unchanged() -> None:
    assert trivy_command("img:1", TrivyConfig()) == TRIVY_DEFAULT


def test_grype_default_command_is_unchanged() -> None:
    assert grype_command("img:1", GrypeConfig()) == GRYPE_DEFAULT


def test_empty_env_yields_defaults() -> None:
    assert TrivyConfig.from_env({}) == TrivyConfig()
    assert GrypeConfig.from_env({}) == GrypeConfig()
    assert GrypeConfig.from_env({}).scan_timeout == 600


# --- Trivy overrides --------------------------------------------------------


def test_trivy_ignore_unfixed_adds_flag() -> None:
    cmd = trivy_command("img:1", TrivyConfig(ignore_unfixed=True))
    assert "--ignore-unfixed" in cmd


def test_trivy_severities_and_pkg_types_and_timeout() -> None:
    cfg = TrivyConfig(severities="CRITICAL,HIGH", pkg_types="os,library", timeout="10m0s")
    cmd = trivy_command("img:1", cfg)
    assert cmd[-1] == "img:1"  # image ref stays last
    assert "--severity" in cmd and cmd[cmd.index("--severity") + 1] == "CRITICAL,HIGH"
    assert "--pkg-types" in cmd and cmd[cmd.index("--pkg-types") + 1] == "os,library"
    assert "--timeout" in cmd and cmd[cmd.index("--timeout") + 1] == "10m0s"


def test_trivy_scanners_override() -> None:
    cmd = trivy_command("img:1", TrivyConfig(scanners="vuln,secret"))
    assert cmd[cmd.index("--scanners") + 1] == "vuln,secret"


def test_trivy_from_env_parses_all_knobs() -> None:
    cfg = TrivyConfig.from_env(
        {
            "JAVV_TRIVY_SCANNERS": "vuln,misconfig",
            "JAVV_TRIVY_IGNORE_UNFIXED": "true",
            "JAVV_TRIVY_SEVERITIES": "CRITICAL",
            "JAVV_TRIVY_PKG_TYPES": "library",
            "JAVV_TRIVY_TIMEOUT": "3m0s",
        }
    )
    assert cfg == TrivyConfig(
        scanners="vuln,misconfig",
        ignore_unfixed=True,
        severities="CRITICAL",
        pkg_types="library",
        timeout="3m0s",
    )


# --- Grype overrides --------------------------------------------------------


def test_grype_only_fixed_and_scope() -> None:
    cmd = grype_command("img:1", GrypeConfig(only_fixed=True, scope="all-layers"))
    assert "--only-fixed" in cmd
    assert cmd[cmd.index("--scope") + 1] == "all-layers"


def test_grype_from_env_parses_all_knobs() -> None:
    cfg = GrypeConfig.from_env(
        {
            "JAVV_GRYPE_ONLY_FIXED": "yes",
            "JAVV_GRYPE_SCOPE": "all-layers",
            "JAVV_GRYPE_SCAN_TIMEOUT": "900",
        }
    )
    assert cfg == GrypeConfig(only_fixed=True, scope="all-layers", scan_timeout=900)


def test_flag_parsing_is_lenient_but_safe() -> None:
    # only explicit truthy strings enable a flag; anything else stays off
    assert TrivyConfig.from_env({"JAVV_TRIVY_IGNORE_UNFIXED": "TRUE"}).ignore_unfixed is True
    assert TrivyConfig.from_env({"JAVV_TRIVY_IGNORE_UNFIXED": "0"}).ignore_unfixed is False
    assert TrivyConfig.from_env({"JAVV_TRIVY_IGNORE_UNFIXED": "maybe"}).ignore_unfixed is False


def test_grype_garbage_timeout_fails_fast_with_the_env_name() -> None:
    # a typo'd timeout must not surface as a bare int() ValueError traceback (#97)
    with pytest.raises(ValueError, match="JAVV_GRYPE_SCAN_TIMEOUT.*'abc'"):
        GrypeConfig.from_env({"JAVV_GRYPE_SCAN_TIMEOUT": "abc"})


# --- garbage-value fail-fast (#97): every knob rejects junk, naming its env var


def test_trivy_scanners_rejects_unknown_token() -> None:
    with pytest.raises(ValueError, match="JAVV_TRIVY_SCANNERS.*bogus"):
        TrivyConfig.from_env({"JAVV_TRIVY_SCANNERS": "vuln,bogus"})


def test_trivy_severities_rejects_junk_and_normalizes_case() -> None:
    with pytest.raises(ValueError, match="JAVV_TRIVY_SEVERITIES"):
        TrivyConfig.from_env({"JAVV_TRIVY_SEVERITIES": "CRITICAL,SEVERE"})
    cfg = TrivyConfig.from_env({"JAVV_TRIVY_SEVERITIES": "critical,High"})
    assert cfg.severities == "CRITICAL,HIGH"


def test_trivy_pkg_types_rejects_junk() -> None:
    with pytest.raises(ValueError, match="JAVV_TRIVY_PKG_TYPES.*rpm"):
        TrivyConfig.from_env({"JAVV_TRIVY_PKG_TYPES": "os,rpm"})


def test_trivy_timeout_wants_a_go_duration() -> None:
    for ok in ("5m0s", "300s", "1h30m", "1.5h"):
        assert TrivyConfig.from_env({"JAVV_TRIVY_TIMEOUT": ok}).timeout == ok
    for bad in ("5x", "5", "five minutes", "-5m"):
        with pytest.raises(ValueError, match="JAVV_TRIVY_TIMEOUT"):
            TrivyConfig.from_env({"JAVV_TRIVY_TIMEOUT": bad})


def test_grype_scope_rejects_junk_and_normalizes_case() -> None:
    with pytest.raises(ValueError, match="JAVV_GRYPE_SCOPE.*everything"):
        GrypeConfig.from_env({"JAVV_GRYPE_SCOPE": "everything"})
    assert GrypeConfig.from_env({"JAVV_GRYPE_SCOPE": "All-Layers"}).scope == "all-layers"


def test_grype_timeout_must_be_positive() -> None:
    for bad in ("0", "-5"):
        with pytest.raises(ValueError, match="JAVV_GRYPE_SCAN_TIMEOUT"):
            GrypeConfig.from_env({"JAVV_GRYPE_SCAN_TIMEOUT": bad})
