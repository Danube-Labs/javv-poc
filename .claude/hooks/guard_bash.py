#!/usr/bin/env python3
"""PreToolUse guard for Bash: refuse the two footguns that have each cost us a session.

Both are written down in CLAUDE.md and both still fired after being written down, which is
the whole argument for making them mechanical. Blocking here costs one retry; the failures
they cause cost a debugging session each.

Reads the hook payload on stdin, exits 2 with a reason on stderr to block, 0 to allow.
"""

import json
import re
import shlex
import sys

ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# Words that can sit in front of the real command. `until ! pgrep -f ...` is not a hypothetical:
# it is the exact loop that hung two sessions, so the guard has to see past them.
LEADING_NOISE = {
    "!",
    "until",
    "while",
    "if",
    "then",
    "do",
    "else",
    "elif",
    "time",
    "sudo",
    "env",
    "nohup",
    "command",
    "exec",
    "builtin",
}

# `git add -A` has swept gitignored files into commits; `pkill -f` matches the Bash tool's own
# wrapper process, so it kills the shell running it or hangs a wait-loop forever.
GUARDS = [
    (
        ("git", "add"),
        {"-A", "--all", "."},
        "`git add -A` / `git add .` has swept gitignored files into commits here.\n"
        "Stage explicit paths instead:  git add path/one path/two",
    ),
    (
        ("pkill",),
        {"-f"},
        "`pkill -f` matches the Bash tool's own wrapper process — it kills the shell running\n"
        "it, or hangs a wait-loop forever. Find the PID and kill that:  ss -ltnp | grep <port>",
    ),
    (
        ("pgrep",),
        {"-f"},
        "`pgrep -f` matches the Bash tool's own wrapper, so it always reports a match and an\n"
        "`until ! pgrep -f ...` loop never exits. Use `ss -ltnp` or match without -f.",
    ),
]

# Anything after a heredoc marker is data (a commit message, a PR body), not commands to run.
SEPARATORS = {"&&", "||", "|", ";", "&", "(", ")", "{", "}"}


def offending_reason(command: str) -> str | None:
    body = command.split("<<", 1)[0]
    try:
        tokens = shlex.split(body, comments=True)
    except ValueError:
        return None  # unbalanced quotes: not parseable, so not confidently a violation

    # walk each command in the chain; shlex has already collapsed quoted strings into single
    # tokens, so a literal "git add -A" inside a commit message cannot trigger this
    start = 0
    for i, tok in enumerate(tokens + [";"]):
        if tok not in SEPARATORS:
            continue
        segment = tokens[start:i]
        start = i + 1
        while segment and (
            ENV_ASSIGNMENT.match(segment[0]) or segment[0] in LEADING_NOISE
        ):
            segment = segment[1:]  # FOO=bar git add -A · until ! pgrep -f …
        for prefix, flags, reason in GUARDS:
            if len(segment) < len(prefix) or tuple(segment[: len(prefix)]) != prefix:
                continue
            if flags & set(segment[len(prefix) :]):
                return reason
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    command = payload.get("tool_input", {}).get("command", "")
    reason = offending_reason(command)
    if reason is None:
        return 0
    print(
        f"Blocked by the repo's Bash guard (.claude/hooks/guard_bash.py):\n\n{reason}",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
