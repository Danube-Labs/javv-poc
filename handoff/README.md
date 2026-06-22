# JAVV - design handoff bundles

UI/product reference for JAVV. These are **reference points, not 1:1 contracts** - the
canonical engineering spec is `../docs/ADR/V4/` and **wins on any disagreement**.

| Folder | What it is | Status |
|--------|-----------|--------|
| `v4/` | Current bundle: React/CDN prototype, UI docs (SCREENS, DESIGN_SYSTEM, V4-DELTA…), brand assets. Targets the v4 design (time-travel, 6-state VEX, scoped risk-accept, per-cluster retention). | **Active** |
| `v1/` | The original 12-screen bundle (v3-era). Kept for the evolution trail. | **Frozen** |

## Reading order (v4)
1. `v4/README.md` - bundle overview + how to open the prototype.
2. `v4/docs/V4-DELTA.md` - what changed from v1, and the ⚠ list of places the prototype
   conflicts with the v4 spec (engineering reconciles these).
3. `v4/docs/SCREENS.md` / `DESIGN_SYSTEM.md` / `DATA_MODEL.md` - the UI contract.
4. `v4/prototype/` - open `JAVV Prototype.html` in a browser (fabricated dataset).

## Canonical hierarchy (when sources disagree)
`docs/ADR/V4/` (engineering spec)  >  `v4/docs/` (UI handoff)  >  `v4/prototype/` (reference)

Brand assets in `v4/brand/` are an embedded **copy** so the bundle stays self-contained/zippable.
The brand **source** of record is `../design/brand/`.
