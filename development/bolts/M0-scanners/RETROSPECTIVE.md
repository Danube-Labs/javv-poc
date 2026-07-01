# M0 / M0b retrospective — fresh-eyes review (2026-07-01)

> Independent cold review of the scanner arc (`scanner/`) and the publish/versions arc. Read the code
> and specs first, formed judgment, then checked it against the canonical design. Tests run locally:
> `76 passed, 4 skipped` (the 4 skips are the live-cluster + real-binary smokes, correctly gated).

## Verdict
This is **ship-quality, genuinely clean work** — disciplined TDD, golden fixtures cut from real scanner
output, defensive parsing of untrusted input, and every hard constraint (per-scanner-never-merged,
self-built images, immutable `cluster_id`, no broker) actually honored in code, not just claimed. The
biggest concern is a **silent data-loss gap**: discovery computes namespace / replica-count / image_ref,
but `run.py` drops all of it — the envelope's `namespace` field is wired to nothing and "replicas
observed at scan time" (which only the scanner can observe) never leaves the pod. Secondary concerns:
`scan_order` uses wall-clock `time.time_ns()`, which quietly contradicts D40's "never order by clock";
the cycle has no per-image error isolation; and several **M0b DoD line-items were silently dropped**
(SBOM/scan/sign of published images, publish-smoke, EOL + DB-schema policy in `versions.yaml`). None
are merge-blockers for a pre-MVP leaf bolt, but the dropped DoD items were closed as "done" without
acknowledgement, which is the thing to fix culturally.

## What was done well
- **Per-scanner is sacred — enforced, not just asserted.** Separate `adapters/trivy.py` + `grype.py`, no
  merge path anywhere; `Envelope.scanner` is a `Literal["trivy","grype"]` (`envelope.py:26,70`); the live
  test asserts two independent envelopes for one image (`tests/test_live_verify.py:78-86`).
- **Untrusted-input hardening is real and tested.** Every parser skips malformed entries instead of
  raising (`adapters/trivy.py:38-46`, `adapters/grype.py:53-60`); `canonical_severity` never raises and
  maps anything unrecognized/non-string to `unknown`, never `crit` (`normalize.py:27-31`), with explicit
  tests for `None/123/[]/{}` and garbage strings (`tests/test_normalize.py:48-56`).
- **Multi-tenant constraint honored at the source.** `cluster_id` defaults to the immutable kube-system
  namespace UID, explicitly not the relabelable `cluster_name` (`run.py:63-66`).
- **Self-built images, never the operator.** Both Dockerfiles `COPY --from` the pinned official image's
  binary into a JAVV-owned python-slim with our entrypoint (`Dockerfile.trivy:8-11`,
  `Dockerfile.grype:8-11`); version pinned via build `ARG` per D41.
- **Idempotent push done right.** gzip with `mtime=0` for byte-identical bodies (`push.py:59`), exponential
  backoff + *full* jitter, clean transient (429/5xx/transport) vs permanent (other 4xx) split, dead-letter
  on exhaustion — all tested with `httpx.MockTransport`, no network (`tests/test_push.py`).
- **Dependency injection throughout makes the units honest.** `runner`, `scan_fn`/`push_fn`, kube `api`,
  `sleep`/`rng` are all injected, so tests exercise real logic rather than mocks-of-themselves.
- **D42 versions.yaml is tidy.** Single source + Renovate annotations + a real drift gate
  (`check-versions.sh` + `versions.yml`) + `setup-dev.sh` reading it directly (`setup-dev.sh:62-69`) so the
  installer cannot drift. The CI compat matrix and bake both derive versions from it.
- **Compat gate is sequenced correctly.** `publish` `needs: compat` and only fires on dispatch/tag
  (`scanner-images.yml:70-73`) — a red gate genuinely blocks publish, and there's a unit proof the checker
  bites on format drift (`tests/test_compat.py:37-43`).
- **Severity buckets match the canonical INDEX-MAP exactly** (six buckets, Grype `Negligible`/`Unknown`
  kept distinct, not folded — `INDEX-MAP_v4.md:62-63`, `PLAN_v4.md:470`).

## Overengineering / simplicity concerns
Very little — this is a lean codebase that mostly resists the urge to generalize. Honest nitpicks only:
- **`severity_canonical` shipped per-finding is mildly redundant** (`models.py:41-45`). It's a computed
  field on every finding in the envelope, but the backend stores verbatim `severity` + derives its own
  `severity_rank`/bucket (INDEX-MAP). The envelope's own `counts` already carry the buckets. Harmless and
  cheap, but it's a normalized field travelling alongside the raw one that the consumer will re-derive.
- **`compat.py` rebuilds an envelope just to assert the bucket invariant** (`compat.py:37-49`). Belt-and-
  suspenders, but it's a handful of lines and it does catch a whole class of regression, so it earns its
  keep. Not worth changing.

No premature abstraction, no speculative config, no dead flexibility found. Good restraint.

## Spec / issue drift
- **`scan_order = time.time_ns()` (wall clock) vs D40 "monotonic … never `@timestamp`."**
  `new_scan_run()` mints the ordering key from wall-clock nanoseconds (`envelope.py:40`). D40's entire
  point is that ordering must survive clock untrustworthiness (watermark CAS keyed on `scan_order`).
  Wall-clock-as-order is fine for single-node k3d dev and the `Forbid` CronJob *on one node*, but across
  nodes an NTP step-back can make a newer run's `scan_order` regress — at which point D40's server-side
  watermark would (correctly, per its rules) **reject the newer scan as stale and drop its findings**. The
  key itself is the weak link. **Verdict: acceptable MVP shortcut, but it contradicts D40's intent and is a
  latent multi-node bug.** At minimum document the single-clock assumption; ideally derive order from a
  source that can't regress.
- **Bolt README says normalize `negligible`/`unknown` → "other"** (`M0-scanners/README.md` Tests section),
  **code keeps them as distinct buckets.** The code follows the *canonical* doc (`INDEX-MAP_v4.md:470` /
  D16: "kept, not folded; 'other' is a UI concern"). **Verdict: code is correct; the bolt README's wording
  is the outlier** — a doc nit, not a code defect.

## Gaps / missed items
- **[Medium] namespace / replicas / image_ref are computed then dropped.** `discovery.py` carefully builds
  `locations` (namespace/pod/container) and `pod_count`, but `scan_all` forwards only `image_digest` to
  `build_envelope` (`run.py:33-41`) — `namespace` is never passed, so `Envelope.namespace`
  (`envelope.py:72`) is permanently `None`, a vestigial field. `INDEX-MAP_v4.md:450` expects per-image
  `replicas` "observed at scan time" and a `namespace`; **the scanner is the only component that can
  observe replica counts**, so once it drops them they're unrecoverable downstream. Possibly intended for
  M1/M3 to consume later, but nothing in the envelope carries it, and a single optional `namespace` is the
  wrong shape anyway since a digest can span namespaces (proven by
  `tests/test_discovery.py:45-53`). **Looks forgotten, not deferred** — there's a half-wired field rather
  than an explicit "out of scope" note.
- **[Medium] M0b DoD: SBOM + image scan + (optional) signing of the published images — not done.** The
  `publish` job bakes and pushes only (`scanner-images.yml:95-102`); no syft/cosign/scan step exists. The
  bolt lists this as a deliverable ("Supply-chain: image scan + SBOM (+ optional signing)") and the issue
  was closed "M0b complete" without flagging it. **Dropped, unacknowledged.**
- **[Medium] M0b DoD: EOL + per-vuln-DB-schema policy absent from `versions.yaml`.** The bolt requires
  "each with an explicit EOL; per-vuln-DB-schema awareness (Grype v5↔v6 incompatible; <0.88 frozen DB)"
  and "an EOL-DB-schema version is flagged (not silently shipped)." `versions.yaml:12-20` carries only
  `current` + `also_supported` strings — no EOL dates, no schema annotations, no flagging. **Dropped.**
- **[Low-Med] M0b DoD: publish-smoke not automated.** "Pull the built image, run `python -m scanner`,
  assert a non-error envelope" — done once manually via dispatch (per issue #60) but absent from the
  pipeline, so it won't catch a future regression. `docker build --check` (also in the DoD) is likewise
  not in CI.
- **[Medium] No per-image error isolation in the scan cycle.** `scan_trivy`/`scan_grype` use
  `subprocess.run(..., check=True)` then `json.loads` with no try/except (`adapters/trivy.py:71-72`,
  `adapters/grype.py:96-97`), and `scan_all` has no guard around `scan_fn` (`run.py:32-42`). One
  un-pullable image or one scanner non-zero exit raises and **aborts the rest of the cycle** — directly at
  odds with D30's "scan everything every cycle." No `subprocess` timeout either (a hung scanner blocks
  forever absent an `activeDeadlineSeconds`, which is M10). The defensive parsing is undone by the
  undefended driver.
- **[Low-Med] Dead-letter persistence is illusory in production.** `_dead_letter` appends to a local file
  (`push.py:41-44`); in a CronJob pod that filesystem is destroyed on completion, so "nothing is silently
  lost" is not actually true until M10 wires a PVC. The unit DoD is met; the operational guarantee isn't,
  and nothing surfaces the caveat. (Reasonably deferred to M10, but worth a code comment.)
- **[Nit] M0b README has no `## Updates` log** (the git-workflow convention); M0's is thorough.

## Recommendations
**P1 (before this data feeds M1/M3):**
1. Wire `namespace` (and a `replicas`/`pod_count`, plus `image_ref` for display) from `ImageTarget`
   through `scan_all` → `build_envelope`, or explicitly mark them out-of-scope in the bolt and remove the
   dead `Envelope.namespace` field. Don't lose scanner-only observations silently.
2. Add per-target error isolation in `scan_all`: wrap `scan_fn` in try/except so one bad image dead-letters
   or is skipped without aborting the cycle (D30); add a `subprocess` timeout to the drivers.

**P2:**
3. Reconcile `scan_order` with D40: either document the single-clock/`Forbid` assumption explicitly next to
   `new_scan_run()`, or move to an ordering source that can't regress under NTP. This interacts with M3's
   watermark CAS and should be settled before M3.
4. Close the M0b DoD gaps or formally defer them on #60 with a written note: SBOM + image scan (+ optional
   cosign) of the published images; automated publish-smoke; `docker build --check` in CI.
5. Add EOL dates + per-DB-schema annotations to `versions.yaml` and a check that flags an EOL/frozen-DB
   version instead of shipping it silently.

**P3:**
6. Add a code comment on `_dead_letter` noting it needs an M10 PVC to actually persist; consider a stderr
   warning when a dead-letter is written so it's at least visible in CronJob logs today.
7. Add an `## Updates` log to the M0b README for consistency.
8. Drop the README "negligible/unknown → other" wording to match the canonical "kept distinct" buckets.
