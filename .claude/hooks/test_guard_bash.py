#!/usr/bin/env python3
"""Cases for the Bash guard. A guard that blocks legitimate commands is worse than no guard,
so the false-positive cases carry as much weight as the ones that must block.

    python3 .claude/hooks/test_guard_bash.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from guard_bash import offending_reason  # noqa: E402

MUST_BLOCK = [
    "git add -A",
    "git add .",
    "git add --all",
    "git add -A .",
    "cd frontend && git add -A",
    "git status && git add . && git commit -m 'x'",
    "GIT_AUTHOR_NAME=x git add -A",
    "pkill -f 'python -m scanner'",
    "pgrep -f uvicorn",
    'until ! pgrep -f "python -m scanner"; do sleep 2; done',
]

MUST_ALLOW = [
    # the ordinary forms
    "git add README.md",
    "git add backend/src/backend/routers/admin_jobs.py scanner/run.py",
    "git add -p",
    "git add --update backend/",
    # a path that merely starts with a dot, and a flag that merely contains one
    "git add .github/workflows/ci.yml",
    "git add --pathspec-from-file=list.txt",
    # the strings appear only as DATA — quoted in a message, or in a heredoc body.
    # this is the case a naive grep gets wrong, and we write these strings constantly.
    "git commit -m 'never use git add -A here'",
    'gh issue comment 1 --body "the rule is: no pkill -f from the Bash tool"',
    "git commit -F - <<'EOF'\nfix: stop using git add -A\nEOF",
    # kill by name without the -f matcher is fine; so is killing by PID
    "pkill nginx",
    "kill -9 12345",
    "ss -ltnp | grep 8000",
    # unrelated commands that happen to contain the substrings
    "echo 'git add -A' >> notes.md",
    "rg 'pkill -f' docs/",
]


def main() -> int:
    failures = []
    for cmd in MUST_BLOCK:
        if offending_reason(cmd) is None:
            failures.append(f"  SHOULD BLOCK but allowed: {cmd!r}")
    for cmd in MUST_ALLOW:
        reason = offending_reason(cmd)
        if reason is not None:
            failures.append(f"  SHOULD ALLOW but blocked: {cmd!r}")
    if failures:
        print(f"guard-bash: {len(failures)} failure(s)")
        print("\n".join(failures))
        return 1
    print(
        f"guard-bash: {len(MUST_BLOCK)} blocked, {len(MUST_ALLOW)} allowed, all as expected"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
