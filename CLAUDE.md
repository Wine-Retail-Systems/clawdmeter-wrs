# Project context

ESP32-S3 firmware for a desk-side Claude Code usage monitor. Each supported
board lives in its own `firmware/src/boards/<name>/` folder and is selected
via PlatformIO's `build_src_filter`. Adding a board means dropping in a new
folder + a new `[env:...]` block — `main.cpp`, `ui.cpp`, and `splash.cpp`
never see board-specific code. See [`docs/porting/adding-a-board.md`](docs/porting/adding-a-board.md).

Two reference ports today, plus one brand variant:

- `boards/waveshare_amoled_216/` — original Waveshare ESP32-S3-Touch-AMOLED-2.16 (CO5300, 480×480 square, CST9220 touch, IMU rotation). Build env: `standard-216`.
- `boards/waveshare_amoled_18/` — Waveshare ESP32-S3-Touch-AMOLED-1.8 (SH8601, 368×448 portrait, FT3168 touch, XCA9554 IO expander). Build env: `standard-180`.
- `wine-216` — **default env** for `flash-mac.sh` / `flash.sh`. Same hardware as `standard-216`, but `-DSPLASH_THEME_WINE` swaps the splash animation set (PixelLab-generated wine sprites, 48×48), the boot/UI logo (`logo_wine.h`), the accent colour (Bordeaux red), and the spinner vocabulary (German wine verbs). Brand fork for jacques.de.

The shared code calls a small HAL (`firmware/src/hal/`) that each board implements: display, touch, input, power, IMU. Optional features are guarded by `BoardCaps` (runtime) and `BOARD_HAS_*` (compile-time) rather than `#ifdef BOARD_*`.

Connects to a host daemon over BLE; daemon polls multiple LLM providers (Anthropic, Codex, Bifrost/LLM-Gateway, Langdock) for usage data. This file is for future Claude Code sessions to bootstrap quickly. Read this first.

## Dokumentations-Richtlinie

> Im Ordner `feature-documentation/` müssen alle neuen Funktionen und Features sowie deren Anpassungen in einzelnen `.md`-Dateien im Markdown-Format dokumentiert werden. Pro Funktion und Markdown eine Datei. Sollte ein Feature aus mehreren Funktionen bestehen, dürfen Unterordner pro Feature angelegt werden. Diese Dokumentation dient vor allem anderen KI-Coding-Agenten zum besseren Verständnis der Codebase.

> Der aktuelle Entwicklungsfortschritt ist fortlaufend in einer `PROGRESS.md` im Projekt-Root zu dokumentieren. Dort wird festgehalten, welche Features bereits umgesetzt sind, welche in Arbeit sind und welche noch ausstehen. So haben alle Beteiligten (Mensch und KI-Agent) jederzeit einen aktuellen Überblick über den Stand der Entwicklung.

## Graphify — Codebase Knowledge Graph

Dieses Projekt nutzt [Graphify](https://github.com/safishamsi/graphify/tree/v8)
zur strukturierten Codebase-Analyse.

### Setup (einmalig pro Repo)

Wenn `graphify-out/` nicht existiert oder `graphify-out/graph.json` fehlt:

1. Prüfe, ob `graphify` als CLI verfügbar ist (`graphify --version`).
   Falls nicht: `uv tool install graphifyy`
2. Prüfe, ob der Graphify-Skill registriert ist (`~/.claude/skills/graphify/`).
   Falls nicht: `graphify install`
3. Erkenne relevante Dateitypen im Repo und installiere passende Extras:
   - `.pdf` vorhanden → `uv tool install "graphifyy[pdf]"`
   - `.docx` / `.xlsx` vorhanden → `uv tool install "graphifyy[office]"`
   - `.sql` vorhanden → `uv tool install "graphifyy[sql]"`
   - `.mp4` / `.mov` / `.mp3` vorhanden → `uv tool install "graphifyy[video]"`
   - Im Zweifel: `uv tool install "graphifyy[all]"`
4. Baue den Graphen: `/graphify .`
5. Registriere im Global Graph: `graphify global add graphify-out/graph.json --as <repo-name>`
   Verwende den Verzeichnisnamen als `<repo-name>`.
6. Generiere die Architekturübersicht: `graphify export callflow-html`
7. Registriere Graphify für dieses Repo: `graphify claude install`
8. **Nur nach expliziter Freigabe durch den Benutzer:**
   Schlage `graphify hook install` vor (auto-rebuild bei git commit).
   Erkläre kurz, was der Hook tut, und warte auf Bestätigung.

### Nutzung

- Lies `graphify-out/GRAPH_REPORT.md` bevor du Architektur- oder
  Abhängigkeitsfragen beantwortest.
- Nutze `graphify query "<frage>"` für Strukturfragen, bevor du
  manuell Dateien durchsuchst.
- Nutze `graphify explain "<Knoten>"` um einzelne Konzepte zu verstehen.
- Nutze `graphify path "<A>" "<B>"` um Verbindungen zwischen
  Komponenten zu finden.
- Bei `AMBIGUOUS`-Kanten im Graphen: Quellcode gegenchecken.

### Aktualisierung

- Nach größeren Refactorings: `/graphify . --force`
- Nach Änderungen an Docs/PDFs: `/graphify . --update`
- Callflow-Export aktualisieren: `graphify export callflow-html`

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
pio run -d firmware -e wine-216                                                # build Wine Edition (default for flash-*.sh)
pio run -d firmware -e standard-216                                            # build Standard 2.16"
pio run -d firmware -e standard-180                                            # build Standard 1.8"
pio run -d firmware -e wine-216      -t upload --upload-port /dev/cu.usbmodem101  # flash Wine Edition on macOS
pio run -d firmware -e standard-216  -t upload --upload-port /dev/ttyACM0          # flash Standard 2.16" on Linux
pio run -d firmware -e standard-180  -t upload --upload-port /dev/cu.usbmodem101  # flash Standard 1.8" on macOS
```

If `pio` isn't on PATH: try `~/.platformio/penv/bin/pio` (Linux/macOS pio install) or `brew install platformio` on macOS.

Device path differs by OS: `/dev/cu.usbmodem*` on macOS, `/dev/ttyACM0` on Linux. Both expose the ESP32-S3 native USB-JTAG (no boot-mode dance needed).

## QA your own UI changes — don't ask the user

The firmware ships a `screenshot` serial command that dumps the LVGL framebuffer. `./screenshot.sh out.png [port]` captures a PNG sized to the active display (480×480 or 368×448). **Use this on every UI iteration** — Read the PNG with the Read tool, verify the change visually, iterate. Script auto-picks the macOS/Linux default port and falls back to pio's bundled Python if pyserial isn't on the system Python.

The boot screen is `SCREEN_SPLASH` and only advances on a physical button press, so a fresh flash will sit on the splash. Use the serial commands `splash` / `usage` / `slot N` / `cycle` / `bluetooth` to switch screens without touching the device, and `next` to advance the splash to the next sprite. `slot N` jumps directly to provider slot N (0 = first active provider); `cycle` mirrors the PWR-button order (provider 0 → 1 → ... → bluetooth → provider 0). Combining `next` + `screenshot` lets a script walk every sprite without physical input. (No need to recompile by hand-editing the boot screen any more — those serial commands were added for exactly this case.)

## Critical gotchas

1. **CO5300 cannot rotate.** Its MADCTL only supports axis flips, not column/row exchange. Rotation is done by **CPU pixel remapping inside `display_hal_draw_bitmap`** in `boards/waveshare_amoled_216/display.cpp`. We use **PARTIAL render mode with strip rotation** (small 480×40 strips, fast). On rotation change → AMOLED brightness flash → force redraw (handled inside `display_hal_tick`).
2. **OPI PSRAM** required: `board_build.arduino.memory_type = qio_opi` in platformio.ini. Without this, `MALLOC_CAP_SPIRAM` returns NULL and the screen is black.
3. **pioarduino platform required.** GFX Library for Arduino needs Arduino Core 3.x (`esp32-hal-periman.h`), not the 2.x that standard `espressif32` ships. We pin `pioarduino/platform-espressif32` 55.03.38-1.
4. **LVGL 9 font patching.** `lv_font_conv` outputs LVGL 8 format. Must remove `#if LVGL_VERSION_MAJOR >= 8` guards, drop `.cache` field, add `.release_glyph`, `.kerning`, `.static_bitmap`, `.fallback`, `.user_data`. Without patching, fonts render invisible.
5. **Touch reading is centralized inside each board's `touch.cpp`.** The HAL `touch_hal_read()` is called once per loop from `my_touch_cb`; the board's implementation owns its latched `touch_pressed/x/y` state. Don't call the underlying controller from anywhere else — CST9220's `getPoint()` etc. do a full I2C transaction and concurrent callers consume each other's data.
6. **Even-aligned flush regions.** `display_hal_round_area` (called from `rounder_cb`) is what each board uses to enforce this. Required on CO5300, harmless on SH8601.
7. **Touch axis swap/mirror is per-board.** The 2.16's CST9220 needs `setSwapXY(true)` + `setMirrorXY(true, false)` — applied inside `boards/waveshare_amoled_216/touch.cpp::touch_hal_init()`. New ports apply their own.
8. **LVGL RGB565A8 is planar.** `w*h` RGB565 pixels followed by `w*h` alpha bytes; `data_size = w*h*3`, `stride = w*2`. Use `init_icon_dsc_rgb565a8()` for icons that overlap non-uniform backgrounds (e.g. battery over splash). Lucide source PNGs are black-on-transparent — converter must tint to white or icons render invisible. See `tools/png_to_lvgl.js`.
9. **Per-board pre-init is `board_init()`.** Each board's `board_init.cpp` brings up `Wire` and any reset-gating IO expander BEFORE `display_hal_init()`. Skipping the IO expander release on AMOLED-1.8 leaves SH8601 + FT3168 in reset and they silently fail to probe.
10. **No `#ifdef BOARD_*` in shared code.** The whole point of the refactor — if you're about to add one, you probably want a `BoardCaps` field or a per-board file instead. See `docs/porting/capability-flags.md`.
11. **`SPLASH_THEME_WINE` is a brand-theme switch, not a hardware switch.** It's allowed in shared code (`splash.cpp` group map, `ui.cpp` logo include, `theme.h` accent) because it's a per-build brand decision, not a per-device capability. Treat it the same way you'd treat a `DEFAULT_LANGUAGE` macro.
12. **Splash sprites are grid-agnostic.** The render path reads `grid` and `palette_size` from each `splash_anim_def_t`. Don't reintroduce a hardcoded `GRID` macro — different sprite sets (claudepix 20×20, wine 48×48) coexist in one build. New sets just pick any grid that divides the panel's smaller dimension evenly; the cell pitch is computed automatically.
13. **Font glyph range covers Latin-1 umlauts.** All 11 fonts include `Ä Ö Ü ß ä ö ü § ·` because the UI is German. If you regenerate fonts with `lv_font_conv` directly (instead of `tools/build_fonts.py`), keep the range `0x20-0x7E,0xA7,0xB7,0xC4,0xD6,0xDC,0xDF,0xE4,0xF6,0xFC` or umlauts will render as boxes.

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

**Wine Edition (jacques.de fork, 3 × 48×48 sprites — Flasche, Glas, Trauben)** generated via PixelLab
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
`splash.cpp`'s render path reads grid+palette_size from each
`splash_anim_def_t` at frame time — no shared-code change when a new
resolution is added.

## Fonts and logo

```bash
python3 tools/build_fonts.py             # regenerate all 11 LVGL bitmap fonts
python3 tools/build_wine_logo.py         # regenerate firmware/src/logo_wine.h (80×80 RGB565A8)
```

`build_fonts.py` wraps `lv_font_conv` via npx and applies the LVGL 9 struct
patch automatically. Glyph range includes German umlauts (`Ä Ö Ü ß ä ö ü`)
and the spinner symbols on the mono variants.

`build_wine_logo.py` describes the wine-glass logo as a 20×20 logical grid
that's 4× scaled to 80×80. Edit the `ART` string in that file and re-run.

`ui.cpp` switches the active logo at compile time via `#ifdef
SPLASH_THEME_WINE` → `logo_wine.h` else `logo.h`. The macros `LOGO_DATA`,
`LOGO_W`, `LOGO_H` are exported so the rest of `ui.cpp` doesn't need its own
`#ifdef`.

## User profile / preferences

See `~/.claude/projects/.../memory/` files for persistent context (user is an embedded-beginner senior dev, brand-conscious, prefers iterative UI refinement, dislikes me authoring my own art when third-party assets are intended). Always read those memory files at session start.

## Recent session highlights

- **Wine Edition full brand-fork (2026-05-24).** Splash engine made grid-agnostic (`splash_anim_def_t` carries its own `grid` + `palette_size`, render path computes cell pitch per sprite). New PixelLab Tier-2 pipeline generates 48×48 animated wine sprites (bottle/glass/grapes/cork, 6–7 frames each, native size=48 via `create_1_direction_object` + `animate_object`). `#ifdef SPLASH_THEME_WINE` switches splash set + 80×80 wine logo (`logo_wine.h`) + Bordeaux accent colour + German wine-spinner vocabulary. Both original Claudepix and Wine sets coexist in the same build. UI labels translated to German across all envs; fonts regenerated with Latin-1 umlaut range (`tools/build_fonts.py` automates `lv_font_conv` + LVGL 9 struct patch). Serial commands `next` / `splash` / `usage` / `bluetooth` added for hands-free QA cycling.
- **Device-abstraction refactor (2026-05-18).** All board-conditional code moved out of shared files into `boards/<name>/` and behind a HAL in `hal/`. ~30 `#ifdef BOARD_*` blocks went to zero. UI is responsive via `compute_layout()` driven by `board_caps()`. New ports add a folder + a PlatformIO env — no shared file edits.
- Added second board port: Waveshare AMOLED-1.8 (368×448 portrait, SH8601, FT3168, XCA9554 IO expander).
- Migrated from Panlee SC01 Plus (480×320 IPS) to Waveshare 2.16" AMOLED (480×480 square). Full hardware/library swap.
- Added IMU auto-rotation, battery indicator, USB-state-aware screen switching.
- Added splash screen with scraped pixel-art animations and 3-button physical input layout.
- Fonts and icons re-scaled ~1.9× for the higher-DPI panel.
- All UI margins widened to 20px to clear the rounded display corners.
- Battery icons converted to RGB565A8 alpha so they blend cleanly over the splash animations.

## Daemon / host side

Python package `daemon/clawdmeter_daemon/` (BLE via `bleak`), entry shim `daemon/clawdmeter_daemon.py` → `cli.py` with subcommands `run` (default) / `setup` / `config` / `doctor`. Shipped inside the Companion-App as a PyInstaller onefile; the power-user path installs it as a service (`daemon/clawdmeter-daemon.service` for systemd, `daemon/com.clawdmeter.daemon.plist` for launchd — both templated with `__PYTHON_BIN__` / `__DAEMON_PATH__` by the install scripts).

**Modules:**

- `providers/` — one adapter per provider (`anthropic`, `codex`, `bifrost`, `langdock`, `bedrock` — Bedrock is paused) on a shared `base.py`. Each emits a payload with a `kind` (`pct_window`, `cost_budget`, `tokens_abs`, `tpm_rpm`).
- `config.py` — TOML config with `[[provider]]` blocks, every provider opt-in via `enabled = true`; `[device]` holds `name = "Clawdmeter"` and `scan_timeout_seconds`.
- `secrets.py` — API keys live in `secrets.env` next to the config, never in `config.toml`.
- `paths.py` — config at `~/.config/clawdmeter/` (Windows: `%APPDATA%\clawdmeter\`), state/cache under the platform state dir (Windows: `%LOCALAPPDATA%\clawdmeter\`).
- `polling.py` — per-provider deadlines; loop wakes every `TICK = 5` s, polls whatever is due, and runs a forced full cycle on a device refresh request or IPC `trigger-poll`. A failed poll waits one full interval instead of retrying every tick.
- `ipc_server.py` — JSON-Lines over Unix socket (macOS/Linux) / Named Pipe (Windows) for the Companion-App: `status`, `reload-config`, `trigger-poll`, `shutdown`, `provider-detect`, `provider-save`, `secret-write`, `list-providers`, `subscribe-events`. Spec: `feature-documentation/companion-app/ipc-protocol.md`.
- `setup_wizard.py` — auto-detect + interactive provider setup (`clawdmeter setup`).

**Discovery & resilience:**

- Scans for the device name (`"Clawdmeter"`, configurable) on first run and caches the resolved address in `<state_dir>/ble-address` (MAC on Linux/Windows, CoreBluetooth UUID on macOS). Swapping the board invalidates the cache.
- On connect failure the cache is dropped so the next scan re-resolves. A stale pairing on macOS (CoreBluetooth code 14, "Peer removed pairing information") is detected and surfaced as `device-pairing-stale` to the Companion-App.

**BLE protocol v2 on service `4c41555a-4465-7669-6365-000000000001`:**

- `...0002` RX — daemon writes one JSON payload per active provider per cycle, then `{"end":1}` as end-of-cycle marker so the firmware can drop providers that disappeared. Writes are spaced by 80 ms (`INTER_WRITE_DELAY_S`) because NimBLE drops back-to-back writes.
- `...0003` TX — firmware notifies ack/nack (daemon doesn't subscribe).
- `...0004` REQ — firmware notifies `0x01` in `onSubscribe` while it has no data yet; the daemon subscribes via `bleak` `start_notify` and answers with an immediate full cycle.
- Payload fields: `p / n / note / k / m1 / m2 / m3 / r1 / r2 / pace / regen / cur / st / ok`. Any change must land in firmware parser (`main.cpp`, `data.h`) and daemon in the same change.

## LLM-Gateway — Label-Pflicht

> **Verbindlich, nicht abwählbar.** Jede Claude-Code-Session in diesem Projekt
> trägt das Repo-Label `x-bf-lh-repo: Wine-Retail-Systems/clawdmeter-wrs`. Über dieses Label erfasst
> das WRS-LLM-Gateway (Bifrost) Token-Verbrauch und Kosten je Repository — ohne
> Label ist die Nutzung dieses Projekts nicht zuordenbar. Ein separates
> Token-Protokoll in der Codebase ist deshalb nicht nötig und wird nicht geführt.

**Der Header-Name ist nicht frei wählbar.** Bifrost protokolliert Header nicht von
sich aus; automatisch in die Log-Metadaten übernommen wird nur, was den Präfix
`x-bf-lh-` trägt — der Präfix fällt dabei weg, der Rest wird zum Metadaten-Schlüssel
(`repo`). Der früher verwendete Header `x-bf-label` liegt dagegen in Bifrosts
eigenem Steuer-Namensraum, ist dort keine Funktion und wird verworfen: Die
Kostenzuordnung über Labels blieb dadurch von Juli bis September 2026 durchgehend
leer. Den Namen nicht zurückändern und nicht „aufräumen".

Gesetzt wird das Label projektweit über `env` in der eingecheckten
`.claude/settings.json` — nicht über persönliche Shell-Wrapper. Damit gilt es
für jeden, der das Repo klont:

```json
{
  "env": {
    "ANTHROPIC_CUSTOM_HEADERS": "x-bf-lh-repo: Wine-Retail-Systems/clawdmeter-wrs"
  }
}
```

**Die Gateway-Anbindung selbst ist optional.** Base-URL und Key gehören nicht
zum verbindlichen Teil:

- `ANTHROPIC_BASE_URL` steht nur dann in der `settings.json`, wenn dieses Projekt
  bewusst über das Gateway läuft:

  ```json
  {
    "env": {
      "ANTHROPIC_BASE_URL": "<GATEWAY-URL>",
      "ANTHROPIC_CUSTOM_HEADERS": "x-bf-lh-repo: Wine-Retail-Systems/clawdmeter-wrs"
    }
  }
  ```

  Fehlt der Eintrag, läuft die Session an einem anderen Endpunkt und das Label
  wird nirgends ausgewertet. Es bleibt trotzdem gesetzt — es kostet nichts und
  greift, sobald jemand die Session doch über das Gateway führt.
- Der Gateway-Key gehört **nie** ins Repository. Er wird lokal gesetzt — per
  `ANTHROPIC_AUTH_TOKEN` in der Shell oder in `.claude/settings.local.json`
  (gitignored) — oder er fehlt schlicht, wenn kein Gateway im Spiel ist.

Ein SessionStart-Hook (`.claude/scripts/set-repo-header.sh --hook`) prüft bei
jedem Start, ob das Label gesetzt ist und zum aktuellen Repository passt.
Fehlende Base-URL und fehlender Key ergeben dort einen **Hinweis**, keinen
Fehler.

**Regeln für KI-Agenten in diesem Projekt:**

- Den `env`-Eintrag `ANTHROPIC_CUSTOM_HEADERS` und den SessionStart-Hook nicht
  entfernen, umbenennen oder auf einen anderen Wert setzen.
- Meldet der Hook ein **fehlendes oder abweichendes Label**, ist das ein
  Konfigurationsfehler und **keine** Nebensächlichkeit: melde ihn dem Nutzer,
  bevor du inhaltlich weiterarbeitest. Hinweise zur optionalen Gateway-Anbindung
  (Base-URL, Key) sind dagegen kein Grund, die Arbeit zu unterbrechen.
- Wird das Repository umbenannt, verschoben oder geforkt, ändert sich das
  erwartete Label. Dann `/wrs-agent-rules` erneut ausführen, statt den Wert von
  Hand zu raten.

## Geheimnisse und Konfigurationswerte

Diese Regel gilt für jeden Wert, der nicht im Repository stehen darf: Zugangsschlüssel,
Client-Geheimnisse, Verbindungszeichenfolgen, selbst erzeugte Signaturschlüssel — etwa API-Keys
von Fremdsystemen (Shop, ERP, Kasse), Service-Account-Schlüssel oder Zugangsdaten zu
Produktivdatenbanken.

### Welche `.env`-Datei wofür

Jede Umgebung hat genau eine eigene Datei. Andere Namen und Mischformen gibt es nicht.

| Datei | Zweck | Versioniert? |
|---|---|---|
| `.env.example` | Vorlage: jeder Name mit leerem Wert und Herkunftskommentar | ja |
| `.env.local` (oder `.env`, wenn das Framework nur diese lädt — pro Projekt eine von beiden) | **lokaler Betrieb** auf dem eigenen Rechner | **nein, gitignored** |
| `.env.<umgebung>`, also `.env.production`, `.env.stage` usw. | **Spiegel eines Deployment-Ziels**: genau die Werte, die auf der Plattform für diese Umgebung hinterlegt sind | **nein, gitignored** |

- Lokal läuft die Anwendung **immer** mit `.env.local` bzw. `.env` — nie mit `.env.production`
  oder einer anderen Deployment-Datei. Wer lokal gegen ein Produktivsystem arbeiten muss, trägt
  die nötigen Werte bewusst in `.env.local` ein.
- `.env.<umgebung>` wird von keinem lokalen Startbefehl geladen. Sie dokumentiert den Stand der
  jeweiligen Umgebung, damit sich deren Verhalten nachvollziehen und die Plattform neu befüllen
  lässt.
- Der Name der Umgebung entspricht dem Deployment-Ziel (`production`, `stage`, …). Für jedes
  Ziel, das es gibt, existiert genau eine Datei; für Ziele, die es nicht gibt, keine.
- `.gitignore` nimmt alle `.env*`-Dateien aus — mit Ausnahme von `.env.example`.

### Die Stellen eines Konfigurationswerts

Ein neuer Konfigurationswert wird an allen folgenden Stellen eingetragen, sonst an keiner:

| Stelle | Was dort steht | Versioniert? |
|---|---|---|
| Env-Schema der Komponente (die zentrale Konfigurationsdatei, etwa `config.py` oder `env.ts`) | Name, Typ, Pflicht oder optional, Vorgabewert | ja |
| `.env.example` | Name mit leerem Wert, plus Kommentar woher der Wert kommt | ja |
| `.env.local` bzw. `.env` | der Wert für den lokalen Betrieb | **nein** |
| `.env.<umgebung>` je Deployment-Ziel | der Wert, der in dieser Umgebung gilt | **nein** |
| Deployment-Plattform (Variable bzw. Secret, etwa in Coolify) + Durchreichung in der Compose- bzw. Deployment-Datei | eine Hülle mit Platzhalter, die ein Mensch später befüllt | die Compose-Datei ja, der Wert nein |

Fehlt eine davon, ist die Aufgabe **nicht** erledigt. Ein Wert, der nur in einer `.env`-Datei
auftaucht, ist für den nächsten Menschen unsichtbar; einer, der nur im Schema steht, lässt die
Anwendung beim Start abbrechen. Kennt der Wert noch keinen Inhalt (etwa weil ein Mensch ihn
liefern muss), steht der Name trotzdem in jeder Datei — mit leerem Wert.

`.env.example` ist zugleich das **Interface für jeden, der das Projekt neu aufsetzt**: Jeder
Eintrag trägt einen Kommentar, woher der Wert kommt und ob er zwingend ist. Eine Variable, die nur
der Erstautor erraten kann, ist ein Fehler.

Wird deployt und dabei eine neue Umgebungsvariable oder ein neues Secret angelegt, gehört derselbe
Wert **im selben Arbeitsschritt** in die `.env.<umgebung>` dieses Ziels — sonst lässt sich das
Verhalten der Umgebung nicht mehr nachstellen.

### Wer den Wert liefert — und was das für dich heißt

Für jeden Wert ist festzuhalten, woher er stammt. Es gibt genau drei Herkünfte:

1. **Vom Menschen** — etwa ein API-Key, den ein Dienstleister ausstellt. Du erzeugst ihn nicht,
   du forderst ihn an und trägst ihn nirgends selbst ein.
2. **Von der Infrastruktur** — etwa Keys, die eine Plattform beim Anlegen eines Projekts oder
   einer Datenbank erzeugt. Der Wert entsteht erst beim Bereitstellen.
3. **Selbst erzeugt** — etwa ein Client-Token oder ein Signaturschlüssel. **Das ist der Fall, der
   besondere Sorgfalt verlangt.**

Wenn du einen Wert selbst erzeugst, gilt zusätzlich:

- Trage ihn **unmittelbar** in jede `.env`-Datei ein, in der er gilt (`.env.local` bzw. `.env`
  und/oder `.env.<umgebung>`) — nicht „später", nicht im Bericht.
- Nenne im Bericht nur den Namen, niemals den Wert, auch nicht gekürzt.
- Halte in `feature-documentation/secrets-register.md` fest: Name, Herkunft, Zweck, wo er im
  Betrieb herkommt, und wie er sich neu erzeugen lässt.
- Ein selbst erzeugter Wert, der nur im Kopf eines Agenten existierte und nie in einer
  `.env`-Datei landete, ist verloren — die Anwendung lässt sich dann lokal nicht mehr
  starten, ohne dass jemand versteht warum.

### Was niemals passiert

- Ein echter Wert in `.env.example`, in einer Migration, in einer Compose- oder Dockerfile-Vorlage,
  in einem Test, in einem Commit oder in einer Protokollausgabe.
- Ein Wert in einem Subagenten-Bericht — auch nicht maskiert. Berichte nennen Namen, keine Werte.
- Eine Fehlermeldung, die den Wert eines fehlenden oder ungültigen Eintrags ausgibt.
  Fehlermeldungen nennen den **Namen** der Variablen, nie ihren Inhalt.
- Ein Zugangstoken, das die Anwendung selbst an Clients ausgibt, im Klartext irgendwo außer in
  der einmaligen Anzeige bei der Ausgabe; gespeichert wird nur der Hash.

### Lokale Entwicklungszugangsdaten sind keine Geheimnisse

Die Zugangsdaten lokaler Docker-Dienste (etwa einer lokalen Datenbank) dürfen bewusst mit echten
Werten in `.env.example` stehen. Sie gehören zu Wegwerf-Containern und sind kein Geheimnis im
Sinne dieser Regel. Die Unterscheidung ist: **Betrifft der Wert ein System außerhalb dieses
Rechners?** Dann ist er ein Geheimnis.

## OpenSpec — Spec-Driven Development

Dieses Projekt nutzt [OpenSpec](https://github.com/Fission-AI/OpenSpec), um
Änderungen vor der Umsetzung als Spezifikation festzuhalten. Die gültigen Specs
liegen unter `openspec/specs/`, laufende Änderungen unter `openspec/changes/`.

### Setup (einmalig pro Repo)

Wenn `openspec/` nicht existiert:

1. Prüfe, ob `openspec` als CLI verfügbar ist (`openspec --version`).
   Falls nicht: `npm install -g @fission-ai/openspec`
2. Initialisiere das Repo: `openspec init --tools claude`
   Das legt `openspec/` sowie die Skills `.claude/skills/openspec-*` und die
   Kommandos `.claude/commands/opsx/` an — alles wird mit eingecheckt.
3. Trage Tech-Stack, Konventionen und Fachbegriffe als `context` in
   `openspec/config.yaml` ein, damit neue Artefakte darauf aufbauen.

### Nutzung

- Für neue Funktionen und Verhaltensänderungen, die mehr als eine Datei
  betreffen: zuerst einen Change anlegen (`/opsx:propose`), dann umsetzen
  (`/opsx:apply`), nach Abschluss archivieren (`/opsx:archive`).
- Bei unklaren Anforderungen erst `/opsx:explore` nutzen, statt direkt einen
  Change zu schreiben.
- Kleine Bugfixes, Tippfehler und reine Refactorings ohne Verhaltensänderung
  brauchen keinen Change.
- Lies vor Änderungen an einem Bereich die passende Spec unter `openspec/specs/`.
  Weicht der Code von der Spec ab, sprich den Widerspruch an, statt ihn still
  in eine Richtung aufzulösen.
- Prüfe Changes mit `openspec validate`, bevor du sie zur Umsetzung freigibst.

### Aktualisierung

- Nach einem Update der CLI: `openspec update`, damit die Skills und Kommandos
  im Repo zur installierten Version passen.

## Impeccable — Frontend-Design

Dieses Projekt nutzt [Impeccable](https://github.com/pbakaus/impeccable) für
Gestaltung und Qualitätsprüfung der Oberfläche. Produktwissen steht in
`PRODUCT.md`, die visuelle Sprache in `DESIGN.md`.

### Setup (einmalig pro Repo)

1. Prüfe, ob der Impeccable-Skill verfügbar ist (`~/.claude/skills/impeccable/`
   oder `.claude/skills/impeccable/`). Falls nicht:
   `npx skills add pbakaus/impeccable`
2. Fehlt `PRODUCT.md`: `/impeccable init` — erfasst Zielgruppe, Zweck und
   feste Vorgaben des Produkts.
3. Fehlt `DESIGN.md` und gibt es bereits eine Oberfläche:
   `/impeccable document` — leitet die vorhandene visuelle Sprache aus dem Code ab.
   Gilt für das Projekt ein Marken-Design-System der WRS-Gruppe (JAC, WEIN & CO,
   WRS), ist dieses die Vorgabe für `DESIGN.md`.
4. **Nur nach expliziter Freigabe durch den Benutzer:**
   Schlage `/impeccable hooks on` vor (Design-Prüfung nach jeder Änderung an
   UI-Dateien). Der Hook wird maschinenlokal in `.claude/settings.local.json`
   eingetragen. Erkläre kurz, was er tut, und warte auf Bestätigung.

### Nutzung

- Bei Arbeit an der Oberfläche (Seiten, Komponenten, Formulare, Styles) den
  Impeccable-Skill verwenden, statt ohne Designgrundlage zu gestalten.
- Vor dem Bau einer neuen Oberfläche: `/impeccable shape` für UX und Aufbau.
- Vor Abschluss einer UI-Änderung: `/impeccable audit` (Barrierefreiheit,
  Performance, Responsive) und bei Bedarf `/impeccable polish`.
- Für Review-Fragen zur Gestaltung: `/impeccable critique`.
- `PRODUCT.md` und `DESIGN.md` sind verbindlich. Widerspricht eine Anforderung
  ihnen, sprich es an, statt eine der Dateien still zu umgehen.

### Aktualisierung

- Ändert sich die visuelle Sprache grundlegend: `DESIGN.md` mit
  `/impeccable document` neu erzeugen, statt sie von Hand auseinanderlaufen zu lassen.

## Subagents proaktiv nutzen

- Prüfe bei jeder nicht-trivialen Aufgabe, ob sie sich für die Delegation an einen Subagent (Agent/Task-Tool) eignet – insbesondere bei:
  - breiter Codebase-Recherche (mehr als ~3 Suchanfragen)
  - unabhängigen, parallelisierbaren Teilaufgaben
  - Aufgaben, die viel Kontext (Logs, große Dateien) erzeugen würden
- Wenn eine Delegation sinnvoll ist, schlage sie **aktiv vor**, bevor du selbst loslegst: nenne kurz den Subagent-Typ und warum.
- Bei mehreren unabhängigen Teilaufgaben: schlage vor, sie parallel über mehrere Subagents laufen zu lassen.

### Beispielhafte Subagent-Rollen

Die folgenden Rollen sind **nur Beispiele** zur Orientierung, keine abschließende Liste. Leite passende Subagents jeweils aus der konkreten Aufgabe und aus dem ab, was dieses Projekt tatsächlich braucht:

- **Dokumentations-Experte** – Erstellt/aktualisiert Doku (z.B. `feature-documentation/`, README, Changelog). Vorschlagen, wenn neue Funktionen ergänzt oder bestehende geändert wurden und die Doku nachgezogen werden muss.
- **Code-Reviewer** – Prüft Diffs auf Bugs, Sicherheitslücken (OWASP), Performance und Stil. Vorschlagen nach größeren Änderungen oder vor einem Commit/PR. **Prüfe aber zuerst, ob bereits Hooks, Review-Gates oder Review-Skills (z.B. pre-commit-Hooks, CI-Checks, ein `/code-review`-Skill oder ein konfiguriertes Stop-Review-Gate) vorhanden sind** – wenn ja, nutze bzw. verweise auf diese, statt einen zusätzlichen Review-Subagent doppelt einzusetzen.
- **Recherche-/Explore-Experte** – Durchsucht die Codebase oder externe Quellen und liefert eine verdichtete Zusammenfassung. Vorschlagen bei "Wo ist X?", "Wie hängt Y zusammen?" oder breiter Architektur-Recherche.
- **Test-/Verifikations-Experte** – Führt Tests, Builds oder Linting aus und meldet nur das Ergebnis zurück. Vorschlagen, bevor eine Änderung als fertig gemeldet wird.
- **Refactoring-Experte** – Nimmt mechanische Umbenennungen/Umstrukturierungen über viele Dateien vor. Vorschlagen bei wiederkehrenden Änderungen an vielen Stellen.
- **Datenbank-/Migrations-Experte** – Prüft Schema-Änderungen und Migrationen auf Sicherheit. Vorschlagen bei Eingriffen in DB-Struktur oder Migrationen.

Passt eine dieser Rollen nicht zum Projekt, ist eine **projektspezifische Rolle die bessere Wahl** – etwa ein Experte für die eingesetzte Kassen-, Shop- oder ERP-Schnittstelle, für ein bestimmtes Framework oder für einen wiederkehrenden Datenimport. Solche Rollen aus dem Projekt ableiten und benennen, statt eine der Beispielrollen zu verbiegen.

Diese Rollen kannst du entweder ad-hoc über das Agent/Task-Tool ansprechen oder als feste Subagents unter `~/.claude/agents/` bzw. `.claude/agents/` definieren (mit `use proactively` in der `description`).
