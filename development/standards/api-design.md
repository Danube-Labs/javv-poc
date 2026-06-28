# API design

JAVV's HTTP conventions, so every router looks the same and the FE↔BE contract is predictable.
This is the **success/shape** side; errors live in [`observability.md`](observability.md) (one envelope,
one status taxonomy). Don't restate index mappings or requirements - link to them.

> Owned by **M1** (skeleton + ingest sets the conventions) and **M6** (read/reporting applies them at scale).
> The generated TS client (`@hey-api/openapi-ts`, M9a) is downstream of these - keep OpenAPI honest.

## Versioning & shape
- All app routes are under **`/api/v1/`** (e.g. `POST /api/v1/ingest/scan`). Bump the prefix only on a
  breaking change; additive fields are not breaking (guarded by the I8 oasdiff check).
- **JSON only.** Request **and** response bodies are `snake_case` (matches Pydantic v2 / OpenSearch fields).
- **Paths:** lowercase, **kebab-case**, **plural** resource nouns (`/findings`, `/scan-events`,
  `/audit-log`); item by id `/findings/{finding_id}`; sub-resources nest one level max.

## The tenant rule (hard constraint)
Every read/export endpoint carries an explicit **`cluster_id`** and filters on it **in the query layer**,
never UI-only - routed through the single `tenant_search` chokepoint (SEC-4), entitlement re-checked on every
fetch **and export** (IDOR). See [`../../CLAUDE.md`](../../CLAUDE.md) hard constraints + INDEX-MAP routing.
`cluster_id` **shape is validated at the edge**; an absent/!malformed one is `400`, not a silent all-tenant read.

## Requests
- Request models are **Pydantic v2 `extra="forbid"`**, with per-field `max_length` + bounded collections
  (NFR-7). Unknown field → `400` (validation envelope).
- **Reads use `GET`** with query params; **writes use `POST`/`PATCH`** with a JSON body. No state-changing `GET`.
- **Filtering** is driven by the shared `fields` config (the same one that powers the FE FilterBar, M9a) -
  `terms` / `range` / `date` / `bool` per field. Don't invent ad-hoc query params per endpoint.

## Pagination (no offset past 10k)
- `from`/`size` **only under 10 000**; beyond that, **PIT + `search_after`** (open a PIT, page by the last
  sort key, **delete the PIT in `finally`** - D38). Aggregations paginate via **composite `after_key`**.
- The cursor is **opaque** to the client: respond with `{ "data": [...], "next_cursor": "<opaque>|null" }`;
  the client passes `cursor` back verbatim. Never leak raw `search_after` arrays as a contract.
- Every list response is explicitly **sorted** (stable tiebreak on a unique key) so paging is deterministic.

## Responses & status
- Success: `200` read · `201` create (+ `Location`) · `202` accepted (async/queued ingest) · `204` no content.
- **Counts/pages come from OpenSearch aggregations/queries — never from shipping raw findings to the client**
  to count (server-side-everything hard constraint).
- Errors: **always** the [`observability.md`](observability.md) envelope (`type/title/status/detail/request_id`);
  status taxonomy (400/401/403/404/413/429/503) lives there - don't duplicate it here.

## Time-travel & idempotency
- The global **`as_of` (T)** param rewinds read endpoints (D28/FR-23): absent/`now` → materialized
  current-state; `T<now` → reconstruction (M8b). Every read endpoint accepts it the same way.
- **Ingest is idempotent** (deterministic `_id`, D18) - a retried push double-counts nothing.
