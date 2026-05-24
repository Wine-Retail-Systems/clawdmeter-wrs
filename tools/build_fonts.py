#!/usr/bin/env python3
# Regenerates the LVGL bitmap fonts in firmware/src/font_*.c using
# lv_font_conv, with the glyph range extended to cover German umlauts
# (Ä Ö Ü ß ä ö ü).
#
# lv_font_conv outputs LVGL 8 format; this script applies the LVGL 9
# patch documented in CLAUDE.md (strip version guards, replace .cache
# with .release_glyph/.kerning/.static_bitmap/.fallback/.user_data).
#
# Requires: npx (Node.js). Run from repo root.

import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASSETS = os.path.join(ROOT, "assets")
SRC = os.path.join(ROOT, "firmware", "src")

STYRENE = os.path.join(ASSETS, "StyreneB-Regular.otf")
TIEMPOS = os.path.join(ASSETS, "TiemposText-400-Regular.otf")
MONO    = os.path.join(ASSETS, "DejaVuSansMono.ttf")

# ASCII + Latin-1 umlauts (Ä Ö Ü ß ä ö ü, plus § and · used by some labels)
# plus currency symbols £ (0xA3) and € (0x20AC) used by the cost_budget screens.
TEXT_RANGE = (
    "0x20-0x7E,0xA3,0xA7,0xB7,0xC4,0xD6,0xDC,0xDF,0xE4,0xF6,0xFC,0x20AC"
)
# Mono adds the spinner star + ellipsis glyphs the original used, plus the
# pace-indicator glyphs (— ↑ ↓ ▲ ▼) — Styrene/Tiempos lack arrows, DejaVu
# Mono has them, so the pace label uses a mono font (see ui.cpp).
MONO_RANGE = TEXT_RANGE + (
    ",0x2026,0x2722,0x2733,0x2736,0x273B,0x273D"
    ",0x2014,0x2191,0x2193,0x25B2,0x25BC"
)

FONTS = [
    ("font_styrene_12.c", STYRENE, 12, TEXT_RANGE),
    ("font_styrene_14.c", STYRENE, 14, TEXT_RANGE),
    ("font_styrene_16.c", STYRENE, 16, TEXT_RANGE),
    ("font_styrene_20.c", STYRENE, 20, TEXT_RANGE),
    ("font_styrene_24.c", STYRENE, 24, TEXT_RANGE),
    ("font_styrene_28.c", STYRENE, 28, TEXT_RANGE),
    ("font_styrene_48.c", STYRENE, 48, TEXT_RANGE),
    ("font_tiempos_34.c", TIEMPOS, 34, TEXT_RANGE),
    ("font_tiempos_56.c", TIEMPOS, 56, TEXT_RANGE),
    ("font_mono_18.c",    MONO,    18, MONO_RANGE),
    ("font_mono_32.c",    MONO,    32, MONO_RANGE),
]


def run_lv_font_conv(font_path, size, ranges, out_path):
    cmd = [
        "npx", "--yes", "lv_font_conv@1.5.3",
        "--font", font_path,
        "-r", ranges,
        "--size", str(size),
        "--format", "lvgl",
        "--bpp", "4",
        "--no-compress",
        "-o", out_path,
        "--lv-include", "lvgl.h",
    ]
    subprocess.run(cmd, check=True)


def patch_lvgl9(path):
    """Strip LVGL8 version guards and rewrite the lv_font_t initialiser
    so it matches the LVGL 9 struct layout."""
    with open(path, "r") as f:
        text = f.read()

    # 1. Remove every "#if LVGL_VERSION_MAJOR >= 8 ... #endif" block but keep
    #    the body. (lv_font_conv wraps the new-format struct in such a guard.)
    out = []
    i = 0
    lines = text.splitlines(keepends=True)
    while i < len(lines):
        ln = lines[i]
        if re.match(r"\s*#if\s+LVGL_VERSION_MAJOR\s*>=\s*8\s*$", ln):
            # Skip the #if line itself.
            i += 1
            # Track nesting in case the body contains further #if/#endif.
            depth = 1
            inside_else = False
            while i < len(lines) and depth > 0:
                cur = lines[i]
                if re.match(r"\s*#if\b", cur):
                    depth += 1
                elif re.match(r"\s*#endif\b", cur):
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                elif depth == 1 and re.match(r"\s*#else\b", cur):
                    inside_else = True
                    i += 1
                    continue
                if not inside_else:
                    out.append(cur)
                i += 1
            continue
        out.append(ln)
        i += 1
    text = "".join(out)

    # 2. Patch the public font initialiser. lv_font_conv (LVGL 8 mode)
    #    emits `.cache = ...`. Replace the trailing fields so the struct
    #    matches LVGL 9.
    def repl(match):
        block = match.group(0)
        # Drop any `.cache = ...,` line.
        block = re.sub(r"\n\s*\.cache\s*=\s*[^,\n]+,?", "", block)
        # If the LVGL9 fields are already present, leave it alone.
        if ".release_glyph" in block:
            return block
        # Inject the LVGL9 fields right after .subpx line.
        inject = (
            "    .release_glyph = NULL,\n"
            "    .kerning = 0,\n"
            "    .static_bitmap = 0,\n"
        )
        block = re.sub(
            r"(\.subpx\s*=\s*[^,\n]+,?\n)",
            r"\1" + inject,
            block,
            count=1,
        )
        # Add fallback + user_data before the closing brace if missing.
        if ".fallback" not in block:
            block = block.replace(
                "};",
                "    .fallback = NULL,\n    .user_data = NULL,\n};",
                1,
            )
        return block

    text = re.sub(
        r"const lv_font_t\s+\w+\s*=\s*\{[^}]*\};",
        repl,
        text,
        flags=re.DOTALL,
    )

    with open(path, "w") as f:
        f.write(text)


def main():
    for asset in (STYRENE, TIEMPOS, MONO):
        if not os.path.exists(asset):
            print(f"missing font asset: {asset}", file=sys.stderr)
            sys.exit(1)

    only = set(sys.argv[1:])
    for name, asset, size, rng in FONTS:
        if only and name not in only:
            continue
        out = os.path.join(SRC, name)
        print(f"  generating {name}  (size={size})")
        run_lv_font_conv(asset, size, rng, out)
        patch_lvgl9(out)
    print("done")


if __name__ == "__main__":
    main()
