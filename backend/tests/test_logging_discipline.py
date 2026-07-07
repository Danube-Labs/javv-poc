"""Logging discipline (#221, major-audit 01 §1 G-1) — the build-breaking guard behind the
standing rule: ALL app logging goes through the shared javv-common structlog pipeline
(observability.md §1). The redaction guarantees only hold for lines that go THROUGH the
pipeline — a bare `print()` or a direct stdlib logger bypasses redaction entirely.

AST-based (not grep) so strings/comments can't trip it. Exemptions are explicit and
code-reviewed: `if __name__ == "__main__":` blocks in jobs (the §1 print() exemption) and the
`_ALLOWED` set below."""

import ast
from pathlib import Path

SRC = Path(__file__).parent.parent / "src" / "backend"

# module path — every entry is a conscious, reviewed exemption. Keep it SHORT.
_ALLOWED: set[str] = {
    "core/logging.py",  # the stdlib→structlog BRIDGE itself — it must touch logging.getLogger
}

_BANNED_CALLS = {"print"}
_BANNED_LOGGING_ATTRS = {"getLogger", "basicConfig"}  # configuring/using stdlib logging directly


def _in_main_block(node: ast.AST, main_blocks: list[ast.If]) -> bool:
    lineno = getattr(node, "lineno", None)
    if lineno is None:
        return False
    return any(blk.lineno <= lineno <= (blk.end_lineno or blk.lineno) for blk in main_blocks)


def _main_blocks(tree: ast.Module) -> list[ast.If]:
    """Top-level `if __name__ == "__main__":` blocks — the observability.md §1 exemption."""
    blocks = []
    for node in tree.body:
        if isinstance(node, ast.If):
            t = node.test
            if (
                isinstance(t, ast.Compare)
                and isinstance(t.left, ast.Name)
                and t.left.id == "__name__"
            ):
                blocks.append(node)
    return blocks


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    mains = _main_blocks(tree)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        bad = None
        if isinstance(fn, ast.Name) and fn.id in _BANNED_CALLS:
            bad = fn.id
        elif (
            isinstance(fn, ast.Attribute)
            and fn.attr in _BANNED_LOGGING_ATTRS
            and isinstance(fn.value, ast.Name)
            and fn.value.id == "logging"
        ):
            bad = f"logging.{fn.attr}"
        if bad and not _in_main_block(node, mains):
            out.append(f"{path.relative_to(SRC)}:{node.lineno} calls {bad}()")
    return out


def test_app_code_never_bypasses_the_shared_logging_pipeline() -> None:
    violations: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if str(path.relative_to(SRC)) in _ALLOWED:
            continue
        violations.extend(_violations(path))
    assert not violations, (
        "app code must log via the javv-common structlog pipeline only "
        "(observability.md §1) — direct call sites found:\n" + "\n".join(violations)
    )
