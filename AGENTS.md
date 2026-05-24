# Project context

ESP32-S3 firmware for a desk-side Claude Code usage monitor. Each supported
board lives in its own `firmware/src/boards/<name>/` folder and is selected
via PlatformIO's `build_src_filter`. Adding a board means dropping in a new
folder + a new `[env:...]` block — `main.cpp`, `ui.cpp`, and `splash.cpp`
never see board-specific code. See [`docs/porting/adding-a-board.md`](docs/porting/adding-a-board.md).

Two reference ports today, plus one brand variant:

- `boards/waveshare_amoled_216/` — original Waveshare ESP32-S3-Touch-AMOLED-2.16 (CO5300, 480×480 square, CST9220 touch, IMU rotation). Build env: `waveshare_amoled_216`.
- `boards/waveshare_amoled_18/` — Waveshare ESP32-S3-Touch-AMOLED-1.8 (SH8601, 368×448 portrait, FT3168 touch, XCA9554 IO expander). Build env: `waveshare_amoled_18`.
- `waveshare_amoled_216_wine` — same hardware as the 2.16, but `-DSPLASH_THEME_WINE` swaps the splash animation set (PixelLab-generated wine sprites, 48×48), the boot/UI logo (`logo_wine.h`), the accent colour (Bordeaux red), and the spinner vocabulary (German wine verbs). Brand fork for jacques.de. Build env: `waveshare_amoled_216_wine`.

The shared code calls a small HAL (`firmware/src/hal/`) that each board implements: display, touch, input, power, IMU. Optional features are guarded by `BoardCaps` (runtime) and `BOARD_HAS_*` (compile-time) rather than `#ifdef BOARD_*`.

Connects to a host daemon over BLE; daemon polls Anthropic API for usage data. This file is for future agent sessions (Claude Code, Codex CLI, Cursor, etc.) to bootstrap quickly. Read this first. CLAUDE.md is the Claude-specific counterpart and carries the same technical content — keep them in sync when the architecture changes.

## Hardware (critical pins)

### AMOLED-2.16 (original)
- Display: **CO5300** AMOLED via QSPI (CS=12, SCLK=38, SDIO0..3=4..7, RST=2)
- Touch: **CST9220** via I2C (SDA=15, SCL=14, INT=11, addr=0x5A)
- PMU: **AXP2101** on same I2C bus (addr=0x34) — battery, USB VBUS, PWR button IRQ
- IMU: **QMI8658** on same I2C bus (addr=0x6B) — accelerometer for auto-rotation
- Buttons: GPIO 0 (left → Space/voice-mode), GPIO 18 (right → Shift+Tab/mode-toggle), AXP PKEY (middle → cycle screens; on splash → cycle animations)

### AMOLED-1.8 (newer port)
- Display: **SH8601** AMOLED via QSPI (CS=12, **SCLK=11** ← different!, SDIO0..3=4..7, RST routed via XCA9554 EXIO1)
- Touch: **FT3168** via I2C (SDA=15, SCL=14, INT=21, addr=0x38). Driven by minimal inline reader in `main.cpp` (FocalTech standard register layout — avoids vendoring the GPLv3 `Arduino_DriveBus` library).
- PMU: AXP2101 @ 0x34 (same chip as 2.16 — `XPowersLib` reused; battery is an optional kit add-on but PMU + charging circuitry are populated)
- IMU: QMI8658 @ 0x6B (same chip — initialized for I2C bus health, rotation logic disabled)
- IO expander: **XCA9554 / PCA9554** @ I2C 0x20. Gates LCD_RST, TP_RST, audio amp enable, and reads the PWR button. **`io_expander_init()` MUST run before `gfx->begin()` or `ft3168_init()`** — otherwise display/touch stay in reset and silently fail. PWR button is on EXIO4, active HIGH (verified empirically with the deleted `iox` serial debug command).
- Orientation: **fixed at 0°**. IMU auto-rotation is disabled; `rotate_strip()` / `handle_rotation_change()` are excluded via `#ifndef BOARD_AMOLED_18`.
- Buttons: GPIO 0 (BOOT → Space/voice-mode), XCA9554 EXIO4 (PWR → cycle screens; on splash → cycle animations). **No third button** (GPIO 18 button doesn't exist on this board).

## Architecture

```text
firmware/src/
  hal/                      — board-agnostic interfaces shared code calls into
    board_caps.h            — runtime BoardCaps struct (W, H, button_count, has_* flags)
    display_hal.h           — init / begin / set_brightness / draw_bitmap / tick / round_area
    touch_hal.h             — init / read(&x, &y, &pressed)
    input_hal.h             — init / is_held(PRIMARY|SECONDARY)
    power_hal.h             — init / tick / battery_pct / is_charging / pwr_pressed (edge)
    imu_hal.h               — init / tick / rotation_quadrant
  boards/
    waveshare_amoled_216/   — CO5300 + CST9220 + AXP PKEY + QMI8658 rotation
    waveshare_amoled_18/    — SH8601 + FT3168 + AXP + XCA9554 (PWR via EXIO4), no rotation
    template/               — copy this to bootstrap a new port
  main.cpp                  — setup() + loop(): HAL calls only, zero #ifdef BOARD_*
  ui.{h,cpp}                — 3-screen UI (splash, usage, bluetooth). compute_layout() picks fonts/positions from board_caps() (responsive — current breakpoint: H >= 460 → large, else compact). German strings throughout; #ifdef SPLASH_THEME_WINE swaps logo + spinner-word table.
  splash.{h,cpp}            — Grid-agnostic pixel-art engine. Each splash_anim_def_t carries its own `grid` (20 for claudepix, 48 for wine) and `palette_size`. Cell = min(W,H)/grid recomputed per sprite; both sets coexist in one build.
  theme.h                   — Design tokens. #ifdef SPLASH_THEME_WINE switches THEME_ACCENT from terra-cotta to Bordeaux red.
  ble.{h,cpp}               — NimBLE peripheral: custom data service + HID keyboard
  data.h                    — UsageData struct
  icons.h                   — icon arrays. Battery (5×) are RGB565A8 with alpha; rest are raw RGB565.
  logo.h                    — 80×80 RGB565A8 Anthropic logo (default builds)
  logo_wine.h               — 80×80 RGB565A8 wine-glass logo (selected via #ifdef SPLASH_THEME_WINE in ui.cpp)
  font_*.c                  — pre-compiled LVGL 9 bitmap fonts (Tiempos 56/34, Styrene 48/28/24/20/16/14/12, Mono 32/18). Glyph range covers ASCII + German umlauts (Ä Ö Ü ß ä ö ü) + § + spinner symbols.
  splash_animations.h       — generated (claudepix 20×20 set)
  splash_animations_wine.h  — generated (wine 48×48 set)
docs/porting/               — adding-a-board.md, hal-contract.md, capability-flags.md
```

Each board folder contains: `board.h` (pins, I2C addresses, `BOARD_HAS_*` flags),
`board_init.cpp` (Wire.begin + any IO expander), `display.cpp`, `touch.cpp`,
`input.cpp`, `power.cpp`, `imu.cpp`, `caps.cpp` (the `BoardCaps` instance), plus
any board-private hardware drivers (e.g. `io_expander.{h,cpp}` on AMOLED-1.8).
PlatformIO's `build_src_filter` includes shared code + one board's folder per env.

## Build / flash

```bash
pio run -d firmware -e waveshare_amoled_216                                          # build 2.16 (default original)
pio run -d firmware -e waveshare_amoled_18                                           # build 1.8 (new port)
pio run -d firmware -e waveshare_amoled_216_wine                                     # build Wine-Edition (jacques.de)
pio run -d firmware -e waveshare_amoled_18 -t upload --upload-port /dev/cu.usbmodem101        # flash 1.8 on macOS
pio run -d firmware -e waveshare_amoled_216 -t upload --upload-port /dev/ttyACM0              # flash 2.16 on Linux
pio run -d firmware -e waveshare_amoled_216_wine -t upload --upload-port /dev/cu.usbmodem101  # flash Wine-Edition on macOS
```

If `pio` isn't on PATH: try `~/.platformio/penv/bin/pio` (Linux/macOS pio install) or `brew install platformio` on macOS.

Device path differs by OS: `/dev/cu.usbmodem*` on macOS, `/dev/ttyACM0` on Linux. Both expose the ESP32-S3 native USB-JTAG (no boot-mode dance needed).

## QA your own UI changes — don't ask the user

The firmware ships a `screenshot` serial command that dumps the LVGL framebuffer. `./screenshot.sh out.png [port]` captures a PNG sized to the active display (480×480 or 368×448). **Use this on every UI iteration** — Read the PNG, verify the change visually, iterate. Script auto-picks the macOS/Linux default port and falls back to pio's bundled Python if pyserial isn't on the system Python.

The boot screen is `SCREEN_SPLASH` and only advances on a physical button press, so a fresh flash will sit on the splash. Use the serial commands `splash` / `usage` / `bluetooth` to switch screens without touching the device, and `next` to advance the splash to the next sprite. Combining `next` + `screenshot` lets a script walk every sprite without physical input.

## Critical gotchas

1. **CO5300 cannot rotate.** Its MADCTL only supports axis flips, not column/row exchange. Rotation is done by **CPU pixel remapping inside `display_hal_draw_bitmap`** in `boards/waveshare_amoled_216/display.cpp`. We use **PARTIAL render mode with strip rotation** (small 480×40 strips, fast). On rotation change → AMOLED brightness flash → force redraw (handled inside `display_hal_tick`).
2. **OPI PSRAM** required: `board_build.arduino.memory_type = qio_opi` in platformio.ini. Without this, `MALLOC_CAP_SPIRAM` returns NULL and the screen is black.
3. **pioarduino platform required.** GFX Library for Arduino needs Arduino Core 3.x (`esp32-hal-periman.h`), not the 2.x that standard `espressif32` ships. We pin `pioarduino/platform-espressif32` 55.03.38-1.
4. **LVGL 9 font patching.** `lv_font_conv` outputs LVGL 8 format with version-guarded `#if LV_VERSION_CHECK(...)` blocks. Under LVGL 9 those evaluate true and the new fields (`release_glyph`, `kerning`, `static_bitmap`, `fallback`, `user_data`) get populated correctly. `tools/build_fonts.py` handles this automatically; if you bypass it, replicate the patch or fonts compile but render invisible.
5. **Touch reading is centralized inside each board's `touch.cpp`.** The HAL `touch_hal_read()` is called once per loop from `my_touch_cb`; the board's implementation owns its latched `touch_pressed/x/y` state. Don't call the underlying controller from anywhere else — CST9220's `getPoint()` etc. do a full I2C transaction and concurrent callers consume each other's data.
6. **Even-aligned flush regions.** `display_hal_round_area` (called from `rounder_cb`) is what each board uses to enforce this. Required on CO5300, harmless on SH8601.
7. **Touch axis swap/mirror is per-board.** The 2.16's CST9220 needs `setSwapXY(true)` + `setMirrorXY(true, false)` — applied inside `boards/waveshare_amoled_216/touch.cpp::touch_hal_init()`. New ports apply their own.
8. **LVGL RGB565A8 is planar.** `w*h` RGB565 pixels followed by `w*h` alpha bytes; `data_size = w*h*3`, `stride = w*2`. Use `init_icon_dsc_rgb565a8()` for icons that overlap non-uniform backgrounds (e.g. battery over splash). Lucide source PNGs are black-on-transparent — converter must tint to white or icons render invisible. See `tools/png_to_lvgl.js`.
9. **Per-board pre-init is `board_init()`.** Each board's `board_init.cpp` brings up `Wire` and any reset-gating IO expander BEFORE `display_hal_init()`. Skipping the IO expander release on AMOLED-1.8 leaves SH8601 + FT3168 in reset and they silently fail to probe.
10. **No `#ifdef BOARD_*` in shared code.** The whole point of the device-abstraction refactor — if you're about to add one, you probably want a `BoardCaps` field or a per-board file instead. See `docs/porting/capability-flags.md`.
11. **`SPLASH_THEME_WINE` is a brand-theme switch, not a hardware switch.** It's allowed in shared code (`splash.cpp` group map, `ui.cpp` logo include + spinner table, `theme.h` accent colour) because it's a per-build brand decision, not a per-device capability. Treat it the same way you'd treat a `DEFAULT_LANGUAGE` macro.
12. **Splash sprites are grid-agnostic.** The render path reads `grid` and `palette_size` from each `splash_anim_def_t`. Don't reintroduce a hardcoded `GRID` macro — different sprite sets (claudepix 20×20, wine 48×48) coexist in one build. New sets just pick any grid that divides the panel's smaller dimension evenly; cell pitch is computed automatically. Render-loop skips the full-canvas memset when sprite_dim == canvas_dim (no margin) to save ~230 KB of writes per frame.
13. **Font glyph range covers Latin-1 umlauts.** All 11 fonts include `Ä Ö Ü ß ä ö ü § ·` because the UI is German across all build envs. If you regenerate fonts with `lv_font_conv` directly (instead of `tools/build_fonts.py`), keep the range `0x20-0x7E,0xA7,0xB7,0xC4,0xD6,0xDC,0xDF,0xE4,0xF6,0xFC` or umlauts will render as boxes.

## Icons

`tools/png_to_lvgl.js <input.png> <symbol> [W_MACRO] [H_MACRO] [--tint=RRGGBB | --no-tint]` converts an alpha PNG to RGB565A8. Default tint is white (`0xFFFFFF`) — necessary for Lucide PNGs. Splice output into `firmware/src/icons.h` and use `init_icon_dsc_rgb565a8()` in ui.cpp. Currently only the 5 battery icons use this format; the rest are still raw RGB565 baked over the panel background, fine because they live inside opaque zones.

## Splash animations

Two sprite sets coexist in the same firmware build:

**Original Claudepix (default builds, 13 × 20×20 sprites)** sourced from
[claudepix.vercel.app](https://claudepix.vercel.app). Pipeline:

```bash
node tools/scrape_claudepix.js  # → tools/claudepix_data/*.json
node tools/convert_to_c.js      # → firmware/src/splash_animations.h
```

**Wine Edition (jacques.de fork, 4 × 48×48 sprites)** generated via PixelLab
MCP (Tier 2 subscription required for `animate_object`). Pipeline:

```bash
# 1. PixelLab MCP: create_1_direction_object(size=48) → select_object_frames → animate_object
# 2. Download frame PNGs to tools/wine_data/pixellab/<sprite>_anim/
python3 tools/pixellab_to_claudepix.py \
    --frames "tools/wine_data/pixellab/<sprite>_anim/0.png,...,6.png" \
    --name "wine X" --out "tools/wine_data/wine_X.json" \
    --grid 48 --palette 31 --hold 160 --category Glass
node tools/convert_to_c.js --in tools/wine_data --out firmware/src/splash_animations_wine.h
```

The shared converter `convert_to_c.js` auto-detects the grid and palette
length from each JSON, so both sets are produced by the exact same tooling.
A legacy hand-pixel 20×20 fallback lives at `tools/legacy/build_wine_sprites.py`
(writes to a separate `tools/wine_data_handpixel/` directory so it can't
overwrite the PixelLab JSONs).

## Fonts and logo

```bash
python3 tools/build_fonts.py             # regenerate all 11 LVGL bitmap fonts
python3 tools/build_wine_logo.py         # regenerate firmware/src/logo_wine.h (80×80 RGB565A8)
```

`build_fonts.py` wraps `lv_font_conv` via npx and applies the LVGL 9 struct
patch automatically. Glyph range includes German umlauts (`Ä Ö Ü ß ä ö ü`)
and the spinner symbols on the mono variants.

`build_wine_logo.py` describes the wine-glass logo as a 20×20 logical grid
that's 4× scaled to 80×80. Edit the `ART` and `PALETTE` literals in that
file and re-run.

`ui.cpp` switches the active logo at compile time via `#ifdef SPLASH_THEME_WINE`
→ `logo_wine.h` else `logo.h`. The macros `LOGO_DATA`, `LOGO_W`, `LOGO_H` are
exported so the rest of `ui.cpp` doesn't need its own `#ifdef`.

## Recent session highlights

- **Wine Edition full brand-fork (2026-05-24).** Splash engine made grid-agnostic (`splash_anim_def_t` carries its own `grid` + `palette_size`, render path computes cell pitch per sprite). New PixelLab Tier-2 pipeline generates 48×48 animated wine sprites (bottle/glass/grapes/cork, 6–7 frames each, native size=48 via `create_1_direction_object` + `animate_object`). `#ifdef SPLASH_THEME_WINE` switches splash set + 80×80 wine logo (`logo_wine.h`) + Bordeaux accent colour + German wine-spinner vocabulary. Both original Claudepix and Wine sets coexist in the same build. UI labels translated to German across all envs (Standard-Build spinner gets German general verbs, Wine-Build gets German wine verbs); fonts regenerated with Latin-1 umlaut range (`tools/build_fonts.py` automates `lv_font_conv` + LVGL 9 struct patch). Serial commands `next` / `splash` / `usage` / `bluetooth` added for hands-free QA cycling.
- **Device-abstraction refactor (2026-05-18).** All board-conditional code moved out of shared files into `boards/<name>/` and behind a HAL in `hal/`. ~30 `#ifdef BOARD_*` blocks went to zero. UI is responsive via `compute_layout()` driven by `board_caps()`. New ports add a folder + a PlatformIO env — no shared file edits.
- Added second board port: Waveshare AMOLED-1.8 (368×448 portrait, SH8601, FT3168, XCA9554 IO expander).
- Migrated from Panlee SC01 Plus (480×320 IPS) to Waveshare 2.16" AMOLED (480×480 square). Full hardware/library swap.
- Added IMU auto-rotation, battery indicator, USB-state-aware screen switching.
- Added splash screen with scraped pixel-art animations and 3-button physical input layout.
- Fonts and icons re-scaled ~1.9× for the higher-DPI panel.
- All UI margins widened to 20px to clear the rounded display corners.
- Battery icons converted to RGB565A8 alpha so they blend cleanly over the splash animations.

## Daemon / host side

Bash daemon (`daemon/claude-usage-daemon.sh`) reads OAuth token, polls Anthropic API, sends JSON over BLE GATT. Run with `systemctl --user start claude-usage-daemon`. The unit file's `ExecStart` is the absolute path to the script — repoint it when switching between the worktree and the main checkout.

**Discovery & resilience:**

- Connects by name (`"Claude Controller"`) on first run, caches resolved MAC at `~/.config/claude-usage-monitor/ble-address`. ESP32 BLE addresses are factory-burned per-chip, so swapping any board invalidates the cache.
- On connect failure: cache is dropped AND device is removed from bluez (`bluetoothctl remove`) so the next scan won't re-pick a dead MAC. Multi-candidate scans pick `head -1` and let the failure cycle converge.
- `POLL_INTERVAL=60`, `TICK=5`. Inner loop wakes every 5s to detect disconnects fast; polls Anthropic when 60s elapsed OR when ESP fires a refresh request.

**GATT characteristics on service `4c41555a-...0001`:**

- `...0002` RX — daemon writes JSON usage payload here.
- `...0003` TX — firmware notifies ack/nack (daemon doesn't subscribe).
- `...0004` REQ — firmware fires `0x01` notify in `onSubscribe` if `has_received_data` is false. Daemon subscribes via `setsid bash -c "stdbuf -oL dbus-monitor … | awk …"`; awk drops a flag file the inner loop picks up.
