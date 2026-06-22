# JAVV - Logo design prompt for Claude Code

> Copy the prompt below into a Claude Code session (ideally in a fresh folder like `branding/`), and
> attach your reference images with it. The prompt is self-contained - no other project context needed.

---

Design a logo for **JAVV** (*Just Another Vulnerability Viewer*), a Kubernetes container-vulnerability
dashboard by **Danube Labs**. I'm attaching reference images - treat them as mood/direction, not
something to copy.

## Brand brief
- **Product:** a lightweight, self-hosted security tool - it discovers what's running in a k8s cluster,
  scans it (Trivy/Grype), and gives security engineers Kibana-grade dashboards with a triage workflow.
- **Name tone:** the self-deprecating "just another…" is intentional - approachable, no-hype,
  engineer-first, pragmatic. The logo should feel honest and workmanlike, not enterprise-slick or
  hacker-edgy.
- **Vendor:** Danube Labs - named for the Danube river; a subtle nod to steady flow / Central-European
  engineering heritage is welcome but must stay subtle.

## Visual direction
- **Motif:** a **viewer/lens** (magnifying glass, focus reticle, or eye) over a stylized
  **container/cube**, with a subtle **wave** hinting at a river. Pick the strongest combination - don't
  force all three if two read cleaner.
- **Palette:** anchor on **teal/cyan** (`#2EC4B6`-ish) + **dark slate** for text. Hard rule: the severity
  palette (reds/oranges/yellows) is reserved for *data* in the app - never use it in brand chrome.
- **Wordmark:** clean geometric sans, works lowercase ("javv"), tight and simple.
- **Must scale down:** the icon alone has to stay legible at 16×16 favicon size - no fine detail.

## Deliverables (all as clean, hand-editable SVG - no raster, no base64)
1. `icon.svg` - the mark alone (square canvas).
2. `wordmark.svg` - "javv" text treatment.
3. `lockup.svg` - icon + wordmark horizontal lockup, with a "by Danube Labs" small-text variant.
4. `favicon.svg` - simplified mark optimized for 16–32 px.
5. Dark-background variants of 1–3 (`*-dark.svg`).

## Process
1. First produce **3–4 distinct concept directions** as a single HTML contact sheet I can open in a
   browser (each concept shown at large size, small size, and on dark), with one line on the idea behind
   each. Use the attached reference images to calibrate taste.
2. Wait for me to pick a direction (I may mix elements).
3. Then refine the chosen one and produce the full deliverable set above, plus a short `BRAND.md` noting
   exact hex colors, font choice (must be a free/open font, e.g. Google Fonts), clear-space and
   minimum-size rules.

Constraints: vector-only, flat (no gradients heavier than a subtle duotone, no drop shadows), and every
SVG must render correctly standalone in a browser.
