# Build pipelines

The firmware ingests several flavours of generated data — splash sprites,
bitmap fonts, icons, and the boot logo. Each one is a single command from
its source asset to its compiled-in C array. Two sprite *sets* are
maintained side-by-side: the original Claudepix Clawd library (20×20) and
the Wine-Edition fork (48×48). `splash.cpp` renders both — the on-device
struct carries grid + palette length per sprite.

## Sprite schema

Each per-sprite JSON the converter ingests looks like:

```json
{
  "name": "wine glass red",
  "category": "Glass",
  "description": "...",
  "palette": ["transparent", "#E8E8EC", "#A0A0A8", "..."],
  "frame_count": 7,
  "frames": [
    { "hold": 160, "grid": [[0, 0, ...], [0, 1, ...], ...] },
    ...
  ]
}
```

- `grid` is the per-frame 2-D array of palette indices. Must be square; all
  frames in one sprite must share the same dimension. The converter
  auto-detects the side length so the Claudepix 20×20 set and Wine 48×48
  set can coexist in the same build.
- `palette` starts with `"transparent"` (alpha 0). The remaining entries
  are `#RRGGBB` strings. Up to 256 colours are supported.
- `frames[*].hold` is in milliseconds.
- The directory's `_index.json` lists which files to include and is the
  source of truth for sprite ordering.

## Splash animations — original Claudepix set (20×20, 13 sprites)

```bash
node scrape_claudepix.js              # → tools/claudepix_data/*.json
node convert_to_c.js                  # → firmware/src/splash_animations.h
```

`scrape_claudepix.js` fetches the manifest from `claudepix.vercel.app/app.js`,
evaluates each animation's embedded JS in a Node VM (loading the same
`creature-engine.js` the site uses), and writes resolved frame data to
`claudepix_data/*.json`. Override URL or output dir with `--base` and
`--out`.

## Splash animations — Wine Edition (48×48, 4 sprites, PixelLab MCP)

The Wine set is generated through PixelLab's MCP server (Tier 2: Pixel
Artisan subscription is required because it uses `animate_object`). Per
sprite:

1. **`create_1_direction_object(description, size=48, view='sidescroller')`**
   queues a 16-candidate review pack. Costs 20 generations.
2. **`get_object(object_id)`** when status flips to `review` returns
   inline previews of the 16 candidates.
3. **`select_object_frames(object_id, indices=[k])`** promotes the chosen
   candidate to its own completed sprite. Free.
4. **`animate_object(object_id, animation_description, frame_count=6)`**
   queues a multi-frame animation. ~1 generation per frame.
5. Download the resulting PNGs with `curl` into
   `tools/wine_data/pixellab/<sprite>_anim/` (one PNG per frame).

Then convert to the JSON schema and bake into the on-device header:

```bash
# Multi-frame sprite from animated PNGs
python3 pixellab_to_claudepix.py \
    --frames "wine_data/pixellab/bottle_anim/0.png,1.png,2.png,3.png,4.png,5.png,6.png" \
    --name "wine bottle bordeaux" \
    --out wine_data/wine_bottle_bordeaux.json \
    --category Bottle --grid 48 --palette 31 --hold 150

# Single-frame still
python3 pixellab_to_claudepix.py \
    --source wine_data/pixellab/cork_still.png \
    --name "wine cork" --out wine_data/wine_cork.json \
    --category Cork --grid 48 --palette 16 --hold 1500

# Rebuild the on-device header from every JSON listed in _index.json
node convert_to_c.js --in wine_data --out ../firmware/src/splash_animations_wine.h
```

`pixellab_to_claudepix.py` does bbox crop → square pad → resize-to-grid
(no-op when the source already matches) → adaptive quantise across the
union of all frames so every frame in one sprite shares the same palette
(required by the on-device renderer). Options:

- `--grid SIZE` — target square grid (default 48; the Claudepix set uses 20)
- `--palette N` — adaptive-palette colour count (default 31, plus the
  reserved transparent slot 0)
- `--hold MS` — per-frame hold in ms (default 600 multi-frame, 1500 still)
- `--category NAME` — category string written to JSON
- `--frames a.png,b.png,...` — multi-frame mode (otherwise `--source` is
  a single PNG)

The list of active wine sprites lives in `wine_data/_index.json`; the
on-device grouping into the four usage-rate buckets is defined inside the
`#ifdef SPLASH_THEME_WINE` block in `firmware/src/splash.cpp`.

### Legacy hand-pixel fallback

`tools/legacy/build_wine_sprites.py` describes the wine sprites as inline
20×20 ASCII art and writes the same JSON schema. Kept for offline /
no-subscription work; **not** part of the active 48×48 workflow. It writes
to `tools/wine_data_handpixel/` (a separate directory) so it cannot
overwrite the PixelLab-generated JSONs. To activate this set instead,
point the converter at the hand-pixel dir:

```bash
python3 tools/legacy/build_wine_sprites.py
node tools/convert_to_c.js --in tools/wine_data_handpixel \
    --out firmware/src/splash_animations_wine.h
```

## Bitmap fonts

```bash
python3 build_fonts.py                                       # all 11 fonts
python3 build_fonts.py font_styrene_28.c font_mono_32.c      # just a subset
```

Wraps `lv_font_conv` (via `npx`, no global install needed). For every
font:

- Glyph range covers ASCII (`0x20-0x7E`) plus the German Latin-1
  supplement (`§ · Ä Ö Ü ß ä ö ü`) so the German UI strings render
  without `?` glyphs. Mono fonts add `· … ✢ ✳ ✶ ✻ ✽` for the spinner.
- LVGL 9 struct patch is applied automatically. `lv_font_conv` v1.5.3
  emits an LVGL-version-guarded struct; the guards evaluate true under
  LVGL 9 so the new fields (`release_glyph`, `kerning`, `static_bitmap`,
  `fallback`, `user_data`) end up populated. If you regenerate fonts by
  hand-calling `lv_font_conv`, replicate this — otherwise fonts compile
  but render invisible.

## Wine logo

```bash
python3 build_wine_logo.py            # → firmware/src/logo_wine.h
```

Describes the 80×80 wine-glass logo as a 20×20 logical grid scaled 4×
nearest-neighbour. Edit the `ART` and `PALETTE` literals in
`build_wine_logo.py` and re-run. Output is RGB565A8 (RGB565 plane +
alpha plane), the same format the rest of the icons use.

`firmware/src/ui.cpp` switches between `logo.h` and `logo_wine.h` via
`#ifdef SPLASH_THEME_WINE`; the macros `LOGO_DATA`, `LOGO_W`, `LOGO_H`
are exported so the rest of the file doesn't carry its own `#ifdef`.

## Icons

```bash
node png_to_lvgl.js assets/icon_bluetooth_48.png icon_bluetooth_data \
     ICON_BLUETOOTH_WIDTH ICON_BLUETOOTH_HEIGHT
```

Converts an alpha PNG to RGB565A8. Default tint is white (`0xFFFFFF`) —
Lucide PNGs are black-on-transparent and would render invisible on the
dark UI without it. Pass `--no-tint` for pre-coloured artwork. Paste the
output into `firmware/src/icons.h`. Battery icons (5) use the RGB565A8
format so they blend cleanly over the splash; the rest are baked RGB565
over the panel background.

## Re-running

All converters are idempotent. Re-run any time the source data changes.
Rebuild firmware afterwards (`pio run -d firmware -e <env> -t upload`).

## License notes

- `scrape_claudepix.js` hits a public site without a stated license.
  Confirm reuse is appropriate before redistributing the output.
- `pixellab_to_claudepix.py` produces derivative works from PixelLab API
  output. See [PixelLab Terms](https://pixellab.ai/termsofservice).
