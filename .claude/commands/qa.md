# QA — JAVV

What "verify this change" means here. Run the checks that fit the **delta**; skip the rest —
don't run everything reflexively. (The full gate exists: `development/e2e/` — that's for
milestone gates, not per-change QA.)

## Backend / scanner / javv-common delta → static floor + scoped tests
- `uv run ruff check` + `uv run ruff format --check` (from the touched package's dir).
- `uv run pyright` — type-check.
- `uv run pytest -k <scope>` for the touched area while iterating; the **full suite**
  (non-serial + serial, per `backend/pyproject.toml` markers) before opening a PR.
- Touched an index/mapping/query? Verify the DSL against the real store first (OpenSearch MCP) —
  read the mapping, don't guess it. `docs/engineering/INDEX-MAP.md` is the source of truth.

## Frontend delta → type-check + tests + lint
- `npm run type-check` (vue-tsc) — never skip; template type errors hide here.
- `npm run test` (Vitest) — the option-builders/emitted-params units are the contract.
- `npm run lint` (ESLint) + stylelint (raw hex / non-token fonts fail — ui-foundations).
- Touched the API surface? `npm run gen:api` and check `git diff` is clean (the I7 contract gate
  will fail CI otherwise).

## UI changed → `/visual-test` (lean toward it for feature-scale UI; skipping small is fine)
For a delta that adds or meaningfully changes **rendered surfaces** — a new view / panel / dialog /
flow — lean toward running `/visual-test`: it catches what type-checks and unit tests can't
(does it actually render, read clearly, behave, in both themes). For small or non-visual changes
(logic, stores, builders, types, refactors, copy) skipping is fine — don't ceremony-ize it.
When unsure on a broad change, ask. Skipping a genuine UI change can still be the right call —
just make it a *decision*, and report it.

**Always report visual-test status explicitly** — never leave it ambiguous:
- **Ran** → shot count + **the screenshot dir as an absolute path** (linkifies in the terminal),
  e.g. `visual-test: ran · 6 shots · /home/…/javv-poc/tmp/screenshots/visual-test/<run>/`.
- **Skipped** → say so with the reason: `visual-test: skipped (no rendered-surface delta)`.

## Docs-only / config-only
Nothing beyond the pre-commit hooks (commitlint, whitespace). Don't run test suites for a README.
