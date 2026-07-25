# Security policy

JAVV is a vulnerability-management tool, so we hold its own security to the standard we help
teams enforce. Thank you for taking the time to report an issue responsibly.

## Reporting a vulnerability

**Please do not open a public issue for a security vulnerability.**

Report it privately through GitHub's
[**Report a vulnerability**](https://github.com/Danube-Labs/javv-poc/security/advisories/new)
form (Security tab → Advisories). It creates a private thread visible only to the maintainers,
and it lets us credit you in the advisory when the fix ships.

Helpful things to include, as far as you can:

- the affected component (backend API, ingest endpoint, frontend, a published scanner image, a job)
- the version or commit you tested against
- reproduction steps, a proof of concept, or a failing request
- the impact you believe it has, and any preconditions (authentication, a specific capability, a
  particular cluster configuration)

## What to expect

JAVV is maintained by a small team, so please treat these as good-faith targets rather than an SLA:

| Stage | Target |
|---|---|
| Acknowledgement of your report | within 3 business days |
| Initial assessment and severity call | within 7 business days |
| Fix or documented mitigation for a confirmed issue | as fast as severity warrants |

We will keep you updated while we work, tell you plainly if we decide something is not a
vulnerability and why, and publish an advisory when a fix ships. Please give us a reasonable window
to release before disclosing publicly.

## Supported versions

JAVV is pre-1.0 and moves quickly. Security fixes land on `main` and go out in the next release, so
**only the latest release is supported**. See
[Releases](https://github.com/Danube-Labs/javv-poc/releases) for the current cut.

## Scope

**In scope** (anything JAVV itself owns):

- the FastAPI backend, especially the **ingest surface**, which parses untrusted scanner output
- authentication, sessions, ingest tokens, and the capability-based RBAC model
- OpenSearch query construction, including tenant isolation by `cluster_id` and injection into
  query DSL
- the Vue frontend, including anything that could leak another tenant's data into a browser
- the **scanner images JAVV publishes** (`ghcr.io/danube-labs/javv-scanner-{trivy,grype}`) and the
  Dockerfiles that build them
- CI/release tooling in this repository, where a flaw could compromise a published artifact

**Out of scope:**

- vulnerabilities in **Trivy or Grype themselves**. Report those to
  [aquasecurity/trivy](https://github.com/aquasecurity/trivy/security) or
  [anchore/grype](https://github.com/anchore/grype/security). If a JAVV-pinned version ships a known
  flaw, that is in scope for us as a **version-bump** issue and a normal issue is fine.
- vulnerabilities in OpenSearch, Kubernetes, or other upstream dependencies, unless JAVV's
  configuration or usage of them is what creates the exposure
- findings that require an already-compromised cluster, host, or administrator account
- a JAVV deployment that an operator has configured insecurely, where JAVV's documented defaults are
  safe. Note that some hardening is deliberately the operator's job, and
  [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) is the reference for every knob.

## Design notes worth knowing before you test

These are deliberate decisions, not oversights, though we still want to hear it if you can break
one of them:

- **Ingest is token-authenticated, not signed.** Scanners push over per-cluster bearer tokens
  (peppered SHA-256, constant-time comparison) with token-to-payload scope binding, so a token
  scoped to one cluster cannot push another cluster's data.
- **The data inspector is structurally read-only.** It is a hard allowlist of read verbs, it denies
  credential indices, and every query is journaled to the audit log. Getting a write through it
  would be a genuine finding.
- **Tenant isolation is enforced server-side**, in the query layer rather than the UI. Every read
  carries an explicit `cluster_id` filter.
- **JAVV never writes to the clusters it monitors.** It only reads workload metadata to discover
  running images.
