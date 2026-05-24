#!/usr/bin/env python3
"""
Convert PixelLab PNG frames to a claudepix-schema JSON ready for
tools/convert_to_c.js.

Supports both:
 * single still — `pixellab_to_claudepix.py <in.png> <name> [out.json]`
 * multi-frame animation — `pixellab_to_claudepix.py --frames f1.png,f2.png,... <name> [out.json]`

Options:
 * --grid SIZE        target square grid (default 48; the original claudepix
                      set is 20, the Wine-Edition uses 48 for more detail).
 * --palette SIZE     adaptive-palette colour count (default 31; slot 0 is
                      reserved for transparent so the total is SIZE+1).
 * --hold MS          per-frame hold in ms (default 600 for multi-frame, 1500
                      for stills).
 * --category NAME    category string written into the JSON.

PixelLab sprites at native size=48 do not need a downscale — the script still
runs the bbox crop + square pad so off-centre PixelLab outputs come out
properly framed, but the resize is a no-op when the source already matches.
"""

import argparse
import json
import os
import sys
from PIL import Image


def to_hex(rgb):
    return "#%02X%02X%02X" % rgb


def crop_and_square(im, padding=2):
    """Crop to alpha bbox then pad to a square canvas with `padding` cells
    of breathing room on every side."""
    bbox = im.split()[3].point(lambda a: 255 if a >= 96 else 0).getbbox()
    if bbox:
        im = im.crop(bbox)
    w, h = im.size
    s = max(w, h) + padding * 2
    sq = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    sq.paste(im, ((s - w) // 2, (s - h) // 2))
    return sq


def load_pixel_grid(path, grid):
    """Return a list of (r, g, b) | None rows of size `grid`×`grid`."""
    im = Image.open(path).convert("RGBA")
    im = crop_and_square(im)
    if im.size != (grid, grid):
        im = im.resize((grid, grid), Image.LANCZOS)
    pixels = []
    for y in range(grid):
        row = []
        for x in range(grid):
            r, g, b, a = im.getpixel((x, y))
            row.append(None if a < 96 else (r, g, b))
        pixels.append(row)
    return pixels


def quantise_frames(frame_pixels, palette_colours):
    """Adaptive-quantise the union of all frames' opaque pixels so every
    frame shares the same palette (required by the on-device renderer)."""
    opaque_all = []
    for px in frame_pixels:
        for row in px:
            for p in row:
                if p is not None:
                    opaque_all.append(p)
    if not opaque_all:
        raise ValueError("all frames are fully transparent")
    src = Image.new("RGB", (len(opaque_all), 1))
    src.putdata(opaque_all)
    q = src.convert("P", palette=Image.ADAPTIVE, colors=palette_colours)
    pal_raw = q.getpalette()[: palette_colours * 3]
    palette = ["transparent"] + [
        to_hex(tuple(pal_raw[i * 3 : i * 3 + 3])) for i in range(palette_colours)
    ]

    # Walk the same pixel order to attach palette indices to every cell.
    qi = 0
    grids = []
    for px in frame_pixels:
        grid_dim = len(px)
        g = [[0] * grid_dim for _ in range(grid_dim)]
        for y in range(grid_dim):
            for x in range(grid_dim):
                if px[y][x] is None:
                    g[y][x] = 0
                else:
                    g[y][x] = q.getpixel((qi, 0)) + 1  # slot 0 = transparent
                    qi += 1
        grids.append(g)
    return palette, grids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", help="PNG path (single-frame mode)")
    ap.add_argument("--frames", help="comma-separated PNG paths for multi-frame animation")
    ap.add_argument("--name", required=True, help="sprite name (used for JSON 'name' field)")
    ap.add_argument("--out", help="output JSON path (default: <first-png-base>.json)")
    ap.add_argument("--grid", type=int, default=48, help="output grid size (default 48)")
    ap.add_argument("--palette", type=int, default=31, help="palette colour count, excluding transparent slot (default 31, total = palette+1)")
    ap.add_argument("--hold", type=int, default=None, help="per-frame hold in ms (default: 600 multi-frame, 1500 single)")
    ap.add_argument("--category", default="Wine", help="category string written to JSON")
    args = ap.parse_args()

    if args.frames:
        paths = [p.strip() for p in args.frames.split(",") if p.strip()]
        if not paths:
            ap.error("--frames is empty")
    elif args.source:
        paths = [args.source]
    else:
        ap.error("specify a PNG path or --frames")

    hold = args.hold if args.hold is not None else (600 if len(paths) > 1 else 1500)

    frame_pixels = [load_pixel_grid(p, args.grid) for p in paths]
    palette, grids = quantise_frames(frame_pixels, args.palette)

    out = args.out
    if not out:
        base = os.path.splitext(paths[0])[0]
        out = base + ".json"

    data = {
        "name": args.name,
        "category": args.category,
        "description": f"PixelLab-generated ({args.grid}px): {args.name}",
        "palette": palette,
        "frame_count": len(grids),
        "frames": [{"hold": hold, "grid": g} for g in grids],
    }
    with open(out, "w") as f:
        json.dump(data, f, indent=2)
    print(f"wrote {out}  ({args.grid}×{args.grid}, {len(grids)} frame(s), {len(palette)} palette entries)")


if __name__ == "__main__":
    main()
