#!/usr/bin/env bash
#
# Encode the README demo GIF from the .webm that frontend/scripts/record-demo.mjs leaves in
# tmp/demo/ (issue 469).
#
# GIF rather than mp4/webm on purpose: GitHub strips <video> and will not play a video
# referenced by a repo-relative path in a README, so an animated GIF in an <img> is the only
# format that actually moves on the rendered page.
#
# Two-pass palette (palettegen/paletteuse) because a single-pass GIF of flat UI chrome bands
# badly on the severity chips and the slate table heads. gifsicle then squeezes the result.
#
# Iterate in tmp/ (gitignored) and commit the output ONCE: every revision of a multi-megabyte
# GIF stays in .git forever.
#
#   development/scripts/make-demo-gif.sh [input.webm] [output.gif]
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
IN="${1:-$(ls -t "$ROOT"/tmp/demo/*.webm 2>/dev/null | head -1)}"
OUT="${2:-$ROOT/tmp/demo/demo.gif}"

# Tuned by measuring this UI, not by guessing. The dense findings/audit tables make every
# frame expensive, so duration and frame count dominate the file size far more than quality
# settings do. 8fps still reads smoothly for pointer motion; 880px keeps headings and the
# mono table columns legible; 96 colours costs almost nothing on flat UI chrome (there is no
# photographic content here) and buys a lot. Together: ~3MB for a ~23s walk.
FPS="${DEMO_FPS:-8}"
WIDTH="${DEMO_WIDTH:-880}"
COLORS="${DEMO_COLORS:-96}"
LOSSY="${DEMO_LOSSY:-150}"
# Recording starts when the browser context opens, a beat before the first paint, so the head
# is blank for a moment. Trim it rather than making the recorder guess at load timing.
START="${DEMO_START:-2}"

[ -n "$IN" ] && [ -f "$IN" ] || { echo "no input .webm found (run frontend/scripts/record-demo.mjs first)" >&2; exit 1; }

echo "in:    $IN"
echo "params: ${FPS}fps ${WIDTH}px ${COLORS}col lossy=${LOSSY} start=${START}s"

ffmpeg -v error -ss "$START" -i "$IN" \
  -vf "fps=${FPS},scale=${WIDTH}:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=${COLORS}:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3" \
  -loop 0 "$OUT.tmp.gif" -y

gifsicle -O3 --lossy="$LOSSY" --colors "$COLORS" "$OUT.tmp.gif" -o "$OUT"
rm -f "$OUT.tmp.gif"

echo "out:   $OUT ($(du -h "$OUT" | cut -f1), $(gifsicle --info "$OUT" 2>/dev/null | grep -oE '^\* .* [0-9]+ images' | grep -oE '[0-9]+ images'))"
