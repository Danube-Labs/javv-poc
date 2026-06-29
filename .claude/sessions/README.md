# Session handoffs (Claude's working memory for this repo)

Project-local **context snapshots** so a new or post-compaction Claude session can pick up *fast* —
without re-deriving where we are. Think "save game before you quit."

## How it works
- **Writing one:** before ending a session or a big `/compact`, run **`/save-context`** (or just ask Claude
  to "save context"). Claude writes `YYYY-MM-DD-<slug>.md` here from [`TEMPLATE.md`](TEMPLATE.md).
- **Resuming:** at the start of a session, Claude reads the **newest** file here (the project `CLAUDE.md`
  points it here) to re-orient before doing anything else.
- **Newest wins.** These are point-in-time snapshots, not a running log — the latest is the truth; older
  ones are just history.

## Committed vs local
- **Committed (shared):** this `README.md` + `TEMPLATE.md` — the infrastructure.
- **Local by default (gitignored):** the actual `YYYY-MM-DD-*.md` snapshots — zero-friction to write before
  compacting, no repo noise. They persist on *this machine* for the next session.
- Want a snapshot to travel (other dev / fresh clone) or be a durable decision record? **`git add -f`** that
  one file deliberately.

## Relationship to the other "memories"
| Where | What | Scope |
|---|---|---|
| **here** (`.claude/sessions/`) | latest where-are-we handoff | this repo, this machine |
| `/end-session` → `~/Claudiu/sessions-history/` | cross-project session journal | global, personal |
| `/root/.claude/.../memory/` (auto-memory) | durable *facts* (prefs, decisions) | global, persists |
| bolt READMEs `## Updates` + GitHub issues | per-bolt spec changes + live status | the build |

This one is the **fast-resume** layer; the others are durable facts / per-bolt detail.
