# M0b - Scanner image publish + compatibility CI

**Status:** tracked in [#60](https://github.com/Danube-Labs/javv-poc/issues/60) — live status on the GitHub issue/board

> Sequences **between M0 and M1**. M0 builds the scanner package + Dockerfiles; this bolt makes the
> self-built images **publishable and compatibility-checked** so operators can pin/swap a known-good tag (D41).

## Goal
Build and **publish** the pinned, self-built Trivy/Grype images (a small **compatible set** of versions), each
gated by a **CI compatibility test** that runs the candidate scanner binary through the JAVV adapters and
asserts the golden contracts still hold. This is where "multiple scanner versions" actually lives — a CI
gate, **not** a runtime switch (D41). The operator later swaps the published tag in their own deploy (M10).

**Canonical refs:** `PLAN_v4` **D41** · `SPEC_v4` FR-2/FR-3 (scan/ingest), NFR-11 (DB cache) ·
M0 (#22, the adapters + golden fixtures + Dockerfiles this gates).

## Depends on
- **M0** (#22) — the `scanner/` package, golden contracts, and `Dockerfile.trivy`/`Dockerfile.grype`.

## Deliverables
- **Matrix build** (`docker buildx bake` + GHA matrix) of one Dockerfile per scanner across the compatible
  versions (`--build-arg TRIVY_VERSION`/`GRYPE_VERSION`) → tagged images `…-trivy:<ver>`, `…-grype:<ver>`.
- **Compatibility test** (CI): run each **candidate** real binary on a fixed image, feed output
  through the adapters, and assert the contracts — severity canonicalization (D16), EPSS/KEV capture,
  envelope shape, and **provenance present** (`scanner_version` + DB fields). **Green → publish as compatible.**
- **Publish** to the registry (GHCR) on green; images **public once the repo is public**; Dockerfiles stay
  public for supply-chain transparency. Each build pushes a **moving `:<ver>`** tag (latest build of that
  scanner version) **+ an immutable `:<ver>-<git-sha>`** tag, with OCI labels (`org.opencontainers.image.
  version`/`revision`/`source`, `javv.scanner`). **Scanner image release ≠ JAVV release** (D41): publishing
  is its own track (`scanner-v*` tag / dispatch), independent of release-please's `v*` app tags — a new
  scanner version or a base-layer rebuild ships without bumping JAVV; the `-<git-sha>` tag/label ties each
  image to the JAVV commit that built its entrypoint.
- **`versions.yaml`** (repo root, D42) — the single source of truth for the compatible set (**current + 1-2 prior**, not 5), each with an explicit
  EOL; **per-vuln-DB-schema** awareness (Grype v5↔v6 incompatible; Grype <0.88 = frozen DB).
- Supply-chain: image **scan + SBOM (+ optional signing)** of the published scanner images themselves.

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus**:
- The matrix builds **both** images for every version in the compatible set; `docker build --check` clean.
- The **compat gate fails the build** when a candidate scanner's output breaks an adapter/golden contract
  (proven with a deliberately-incompatible pin or a recorded drift case) — a red gate **blocks publish**.
- A **published** image runs `python -m scanner` and produces a valid envelope (smoke against the seed target).
- Compatible set + EOL policy documented; an EOL-DB-schema version is flagged (not silently shipped).

## Tests to write
- CI compat matrix: per compatible `(scanner, version)`, real-binary → adapters → contract asserts (incl. provenance).
- A negative case: an incompatible/old pin makes the gate red (so the gate is proven to bite).
- Publish smoke: pull the built image, run it against the dev smoke target, assert a non-error envelope.

## Out of scope (defer)
- Helm chart / CronJob deploy + the **per-schema PVC DB cache** → **M10** (the operator wires the tag there).
- The read-only version display in the UI → **M9d / M9e**.
- The ingest endpoint that accepts the provenance fields → **M1** (`extra="forbid"` coupling, D41).
