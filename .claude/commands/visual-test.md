# Visual Test

Visually verify JAVV frontend changes against the live dev stack. Takes screenshots, organizes
them per run, and reports what looks right or wrong. This is the **authoring-time** loop —
distinct from M9f's CI E2E suite (Playwright specs); nothing here runs in CI.

## Step 1: Pick the driver

**Preferred: the committed rig** — `frontend/scripts/visual-capture.mjs` (Playwright library,
already a frontend devDep; Chromium in `/root/.cache/ms-playwright`):

```bash
cd frontend && JAVV_USER=… JAVV_PASS=… node scripts/visual-capture.mjs [outDir]
```

It logs in through the real form, walks the standard screens **including forced non-default
states** (the history banner et al. — defaults-only scans miss conditional UI, which is how an
AA failure once survived two "clean" runs), captures console errors/warnings, and writes
screenshots + **rendered-HTML dumps** for the anti-pattern detector:

```bash
node .claude/skills/impeccable/scripts/detect.mjs <outDir>/*.html
```

Extend the rig (new screens/states) rather than writing throwaway scripts. For ad-hoc
interactive poking, the Playwright MCP (`mcp__playwright__browser_*`) works too when its tools
are mounted — but the rig is the reproducible path and needs no MCP.

## Step 2: Scope what to test

```bash
git status && git branch --show-current
git log main..HEAD --oneline
git diff main..HEAD --name-only -- frontend/
```

Summarize which screens/components the delta touches — that drives the capture plan. If the diff is
non-visual (stores, pure builders, types), say so and stop: `/qa` covers it.

## Step 3: Stack preflight

The FE is useless against a dead or empty backend. Check in order:

```bash
curl -s -o /dev/null -w '%{http_code}' http://localhost:9200        # OpenSearch (expect 200)
curl -s http://localhost:8000/readyz                                 # backend (expect 200 / ok)
```

- Backend down → start it per `development/e2e/README.md` §Running (uvicorn, `JAVV_ENV=dev`,
  stdout piped to `development/e2e/logs/backend.log`).
- **Seeded data check** — screens need real findings to render meaningfully. Log in
  (`POST /auth/login`, dev bootstrap admin) and probe `GET /api/v1/findings?cluster_id=…&size=1`;
  an empty store renders only empty states. If empty, tell the user and offer to seed:
  `./development/e2e/smoke.sh` (real-scanner corpus — the good option, needs k3d) or a gentle
  `LOAD_HEAVY=0 loadbreak.py --phase load` (synthetic). **Wait for confirmation before seeding.**
- Remember the dev admin may be password-rotated (`must_change` flow) — handle the rotation screen
  rather than reporting it as a bug.

## Step 4: Launch the frontend

```bash
cd frontend && npm run dev      # Vite, proxies /api → :8000
```

Record the URL Vite prints. For changes to the build/embed path itself, use `npm run build` +
`npm run preview` instead — that tests what ships.

## Step 5: Drive the browser

- **Set the viewport FIRST — before any navigation.** Playwright MCP defaults to a narrow viewport
  that doesn't match real users: `browser_resize({ width: 1920, height: 1080 })`. JAVV is
  desktop-first; also capture 1280px when the delta touches layout.
- Log in through the real login screen (dev bootstrap admin). Never hardcode credentials into
  committed files.
- Walk the affected screens per the Step-2 plan. For each: screenshot, check the browser console
  for errors/warnings (must be clean), verify **light AND dark** theme when the delta touches
  styling, and verify loading/empty/error states where reachable.
- Screenshots go under `.playwright-mcp/visual-test/<run-timestamp>/` (gitignored), named by
  screen/state.

## Rules

- **Never mutate the store without explicit confirmation.** Read-only navigation is always safe;
  triage writes, decisions, settings changes, renames are writes — ask first, and prefer doing them
  on a throwaway cluster_id. The dev store is disposable but the user decides.
- Kill any process you started (Vite, preview server) when done.

## Report

1. What was captured (screens × states × themes) and what was deliberately skipped.
2. What looks right / wrong — concrete: overflow, contrast, token violations (raw colors where a
   token belongs), missing states, console errors.
3. **The screenshot directory as an absolute path** (or `file://` URL) so it linkifies in the
   terminal — never a relative or `~/` path.
