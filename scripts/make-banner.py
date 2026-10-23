"""Generate the Memotext banner: a terminal window with text as outlines and a timed animation.

Usage: python3 scripts/make-banner.py [--accent HEX] [--regular FONT.ttf] [--bold FONT.ttf]
       [--out PATH]

The output defaults to .github/memotext-banner.svg and the wordmark colour to #ff6b6b.

Follows the Stratarc banner (window chrome, palette, timing, outlined DejaVu Sans Mono) and
changes only the command, the wordmark, the tagline and the result rows. Text is converted to
paths so the banner renders identically in every viewer, with no font dependency.

This script is the one place that needs `fonttools` (pip install fonttools). It is a development
tool, not a dependency of the package, and the package never imports it. The default fonts are the
DejaVu Sans Mono files that most Linux distributions ship; pass --regular and --bold elsewhere.
"""

import argparse
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

PACKAGES = {
    "memotext": {
        "folder": "~",
        "command": "memotext list",
        "tagline": "read the Voice Memos library and the transcripts iOS made",
        "label": (
            "A terminal window: memotext list is typed, the memotext wordmark appears, "
            "and recordings are listed with their transcripts"
        ),
        "status_column": False,
        "rows": [
            ("ok", "2026-10-18", "03:41", "standup notes, transcript found"),
            ("ok", "2026-10-17", "12:05", "design review, transcript found"),
            ("warn", "2026-10-16", "00:48", "kitchen idea, no transcript yet"),
            ("ok", "2026-10-15", "07:22", "call with the bank, transcript found"),
        ],
    },
}

ap = argparse.ArgumentParser()
ap.add_argument("--accent", default="#ff6b6b", help="wordmark colour")
ap.add_argument("--regular", default="/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
ap.add_argument("--bold", default="/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf")
ap.add_argument("--out", default=".github/memotext-banner.svg")
args = ap.parse_args()
name = "memotext"
spec = PACKAGES[name]
out = Path(args.out)

REG = TTFont(args.regular)
BOLD = TTFont(args.bold)

CYCLE = 10.0  # seconds per loop


def glyph_paths(font, text, x, y, size, per_char=False):
    """Return a list of (path_d, advance_x) for text at baseline (x, y), per run or per char."""
    upem = font["head"].unitsPerEm
    s = size / upem
    cmap = font.getBestCmap()
    gs = font.getGlyphSet()
    hmtx = font["hmtx"]
    result = []
    pen = None
    cx = x
    for ch in text:
        glyph = cmap.get(ord(ch), ".notdef")
        if per_char or pen is None:
            pen = SVGPathPen(gs, ntos=lambda v: f"{v:.1f}".rstrip("0").rstrip("."))
        tp = TransformPen(pen, (s, 0, 0, -s, cx, y))
        gs[glyph].draw(tp)
        cx += hmtx[glyph][0] * s
        if per_char:
            result.append((pen.getCommands(), cx))
            pen = None
    if not per_char:
        result.append((pen.getCommands(), cx))
    return result


def text_width(font, text, size):
    upem = font["head"].unitsPerEm
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    return sum(hmtx[cmap.get(ord(c), ".notdef")][0] for c in text) * size / upem


def pct(t):
    return f"{t / CYCLE * 100:.2f}%"


parts = []
css = []

# static chrome, identical to the Stratarc banner
parts.append(
    '<rect x="40" y="28" width="800" height="344" rx="14" fill="url(#bg)" '
    'stroke="#23344a" filter="url(#shadow)"/>'
)
parts.append('<rect x="40" y="28" width="800" height="40" rx="14" fill="#1b2a3d"/>')
parts.append('<rect x="40" y="54" width="800" height="14" fill="#1b2a3d"/>')
parts.append(
    '<circle cx="66" cy="48" r="6.5" fill="#ff5f57"/>'
    '<circle cx="88" cy="48" r="6.5" fill="#febc2e"/>'
    '<circle cx="110" cy="48" r="6.5" fill="#28c840"/>'
)

w = text_width(REG, name, 13)
((d, _),) = glyph_paths(REG, name, 440 - w / 2, 53, 13)
parts.append(f'<path class="dim" d="{d}"/>')

# prompt line
x = 76
((d, x),) = glyph_paths(REG, spec["folder"], x, 112, 15)
parts.append(f'<path class="prompt" d="{d}"/>')
((d, x),) = glyph_paths(REG, " $ ", x, 112, 15)
parts.append(f'<path class="dim" d="{d}"/>')

# typed command, one path per character with staggered appearance
T_TYPE0 = 0.7
T_STEP = 0.09
cmd = spec["command"]
chars = glyph_paths(REG, cmd, x, 112, 15, per_char=True)
cursor_x = x
for i, (d, _nx) in enumerate(chars):
    t = T_TYPE0 + i * T_STEP
    css.append(
        f".c{i}{{animation:show{i} {CYCLE}s steps(1) infinite}} "
        f"@keyframes show{i}{{0%,{pct(t)}{{opacity:0}}{pct(t + 0.001)},100%{{opacity:1}}}}"
    )
    parts.append(f'<path class="txt c{i}" d="{d}"/>')
T_TYPED = T_TYPE0 + len(cmd) * T_STEP

# cursor follows the typing, then blinks
cursor_positions = [cursor_x] + [nx for _, nx in chars]
for i, cx in enumerate(cursor_positions):
    t0 = T_TYPE0 + (i - 1) * T_STEP if i > 0 else 0.0
    t1 = T_TYPE0 + i * T_STEP if i < len(chars) else CYCLE
    parts.append(f'<rect class="cursor k{i}" x="{cx + 3:.1f}" y="100" width="8" height="15"/>')
    if i < len(chars):
        css.append(
            f".k{i}{{animation:cur{i} {CYCLE}s steps(1) infinite}} "
            f"@keyframes cur{i}{{0%{{opacity:0}}{pct(t0)}{{opacity:1}}{pct(t1)},100%{{opacity:0}}}}"
        )
    else:
        css.append(
            f".k{i}{{animation:cur{i} {CYCLE}s steps(1) infinite, blink 1.1s steps(1) infinite}} "
            f"@keyframes cur{i}{{0%,{pct(t0)}{{visibility:hidden}}"
            f"{pct(t0 + 0.001)},100%{{visibility:visible}}}}"
        )

# wordmark and tagline
T_WORD = T_TYPED + 0.35
((d, _),) = glyph_paths(BOLD, name, 76, 196, 64)
parts.append(f'<path class="word show-word" d="{d}"/>')
((d, _),) = glyph_paths(REG, spec["tagline"], 76, 228, 15)
parts.append(f'<path class="dim show-word" d="{d}"/>')
css.append(
    f".show-word{{animation:sw {CYCLE}s steps(1) infinite}} "
    f"@keyframes sw{{0%,{pct(T_WORD)}{{opacity:0}}{pct(T_WORD + 0.001)},100%{{opacity:1}}}}"
)

# result rows: a green tick, an amber dot or a red cross, drawn after the row lands
T_ROW0 = T_WORD + 0.7
T_ROWSTEP = 0.55
for i, (mark, first, second, third) in enumerate(spec["rows"]):
    y = 272 + i * 22
    t = T_ROW0 + i * T_ROWSTEP
    ((d1, _),) = glyph_paths(REG, first, 100, y, 14)
    ((d2, _),) = glyph_paths(REG, second, 250, y, 14)
    ((d3, _),) = glyph_paths(REG, third, 390, y, 14)
    status_column = spec.get("status_column", True)
    cls2 = {"ok": "dim", "warn": "warn", "deny": "deny"}[mark] if status_column else "dim"
    parts.append(
        f'<g class="r{i}"><path class="txt" d="{d1}"/><path class="{cls2}" d="{d2}"/>'
        f'<path class="dim" d="{d3}"/></g>'
    )
    cy = y - 5
    if mark == "ok":
        parts.append(f'<path class="ok t{i}" d="M77 {cy} l3.2 3.4 l6.2 -7.2"/>')
    elif mark == "warn":
        parts.append(f'<circle class="warnmark t{i}" cx="82" cy="{cy - 1}" r="4.2"/>')
    else:
        parts.append(f'<path class="denymark t{i}" d="M78 {cy - 5} l8 8 M86 {cy - 5} l-8 8"/>')
    css.append(
        f".r{i}{{animation:row{i} {CYCLE}s steps(1) infinite}} "
        f"@keyframes row{i}{{0%,{pct(t)}{{opacity:0}}{pct(t + 0.001)},100%{{opacity:1}}}}"
    )
    css.append(
        f".t{i}{{animation:tick{i} {CYCLE}s linear infinite}} "
        f"@keyframes tick{i}{{0%,{pct(t + 0.15)}{{stroke-dashoffset:16;opacity:0}}"
        f"{pct(t + 0.45)},100%{{stroke-dashoffset:0;opacity:1}}}}"
    )

style = (
    f"""
.dim{{fill:#7c93ad}}.txt{{fill:#d7e3ee}}.prompt{{fill:#5aa9ff}}.word{{fill:{args.accent}}}
.warn{{fill:#febc2e}}.deny{{fill:#ff5f57}}
.cursor{{fill:#d7dce6}}
"""
    ".ok{fill:none;stroke:#3ddc84;stroke-width:2.2;stroke-linecap:round;"
    "stroke-linejoin:round;stroke-dasharray:16;stroke-dashoffset:16}\n"
    ".warnmark{fill:#febc2e}\n"
    ".denymark{fill:none;stroke:#ff5f57;stroke-width:2.2;stroke-linecap:round;"
    "stroke-dasharray:16;stroke-dashoffset:16}\n"
    "@keyframes blink{50%{opacity:0}}\n" + "\n".join(css)
)

body = "\n".join("  " + p for p in parts)
svg = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="880" height="400" viewBox="0 0 880 400" '
    f'role="img" aria-label="{spec["label"]}">\n'
    "  <!-- Generated by scripts/make-banner.py. Text is set as outlines of DejaVu Sans Mono "
    "(Bitstream Vera license) so it renders identically everywhere. "
    "Edit the generator, not these paths. -->\n"
    "  <defs>\n"
    '    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0" stop-color="#162233"/><stop offset="1" stop-color="#0d1520"/>'
    "</linearGradient>\n"
    '    <filter id="shadow" x="-10%" y="-10%" width="120%" height="130%">'
    '<feDropShadow dx="0" dy="18" stdDeviation="18" flood-color="#000" flood-opacity="0.45"/>'
    "</filter>\n"
    f"    <style>{style}</style>\n"
    "  </defs>\n"
    f"  {body}\n"
    "</svg>\n"
)
out.write_text(svg)
settles = T_ROW0 + len(spec["rows"]) * T_ROWSTEP
print(f"wrote {out}: {len(svg)} bytes; animation settles at {settles:.2f}s of a {CYCLE:.0f}s loop")
