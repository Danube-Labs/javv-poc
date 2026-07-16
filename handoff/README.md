# JAVV - design handoff bundles

UI/product reference for JAVV. These are **reference points, not 1:1 contracts** - the
canonical engineering spec is `../docs/engineering/V4/` and **wins on any disagreement**.

| Folder | What it is | Status |
|--------|-----------|--------|
| `v5/` | **Current UI contract**: `docs/SCREENS-v5.md` + `docs/DATA_MODEL-v5.md` - the design refreshed against everything ruled/built through M8 (#237 rulings). Docs only - there is **no v5 prototype**; the v4 jsx below stays the markup/fidelity source. | **Active** |
| `v4/` | React/CDN prototype, UI docs (SCREENS, DESIGN_SYSTEM, V4-DELTA…), brand assets. Frozen trail - port its markup per `frontend/DESIGN.md` §8, then apply the v5 deltas. | **Frozen (fidelity source)** |
| `../.deprecated/handoff/v1/` | The original 12-screen bundle (v3-era). Archived to `.deprecated/`. | **Frozen** |

## Reading order
1. `v5/docs/SCREENS-v5.md` - the per-screen contract (§ numbers the bolts cite).
2. `v5/docs/DATA_MODEL-v5.md` - the UI-facing data shapes.
3. `v4/README.md` + `v4/prototype/` - open `JAVV Prototype.html` in a browser (fabricated
   dataset); the jsx is what DESIGN.md §8 means by "build with the prototype open".
4. `v4/docs/V4-DELTA.md` - the ⚠ list of places the prototype conflicts with the spec.

## Canonical hierarchy (when sources disagree)
`docs/engineering/V4/` (engineering spec)  >  `v5/docs/` (UI contract)  >  `v4/docs/` (UI handoff)  >  `v4/prototype/` (reference)

Brand assets in `v4/brand/` are an embedded **copy** so the bundle stays self-contained/zippable.
The brand **source** of record is `../design/brand/`.
