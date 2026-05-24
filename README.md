# Clawdmeter

A small ESP32 dashboard I made for my desk to keep an eye on Claude Code usage.

It runs on a [Waveshare ESP32-S3-Touch-AMOLED-2.16](https://www.waveshare.com/esp32-s3-touch-amoled-2.16.htm?&aff_id=149786) and pairs with my laptop over Bluetooth, the splash screen plays pixel-art Clawd animations that get
busier when your usage rate climbs. The two side buttons send Space and
Shift+Tab over BLE HID for Claude Code's voice mode and mode-toggle shortcuts.

|              Usage meter              |              Clawd animation screen              |
| :-----------------------------------: | :----------------------------------------------: |
| ![Usage meter](assets/demo.jpeg) | ![Clawd animation screen](assets/demo.gif) |

The Clawd animations come from [claudepix](https://claudepix.vercel.app), [@amaanbuilds](https://x.com/amaanbuilds)'s library of pixel-art Clawd sprites, check it out, it's lovely.

## Screens

The device boots into the splash and stays there until you press the middle (PWR) button, which cycles between Usage and Bluetooth. Tap the screen anywhere (except the Reset zone on the Bluetooth screen) to flip back to the splash; tap again to dismiss it.

|              Splash               |              Usage              |                Bluetooth                |
| :-------------------------------: | :-----------------------------: | :-------------------------------------: |
| ![Splash](screenshots/splash.png) | ![Usage](screenshots/usage.png) | ![Bluetooth](screenshots/bluetooth.png) |
|   Splash; touch-toggle anytime    | Session and weekly utilization  |    Connection status and bond reset     |

While the splash is up, the middle button cycles animations instead of screens. The firmware also auto-rotates every 20 s within the current usage-rate group, so a long stretch on the splash isn't just one Clawd on loop.

## Hardware

Two boards are supported out of the box:

- [Waveshare ESP32-S3-Touch-AMOLED-2.16](https://www.waveshare.com/esp32-s3-touch-amoled-2.16.htm?&aff_id=149786) — ESP32-S3R8, 2.16" 480×480 AMOLED (CO5300 QSPI), CST9220 cap touch, AXP2101 PMU + Li-Po battery, QMI8658 IMU. Three side buttons, IMU auto-rotation. Build env: `waveshare_amoled_216`.
- [Waveshare ESP32-S3-Touch-AMOLED-1.8](https://www.waveshare.com/esp32-s3-touch-amoled-1.8.htm?&aff_id=149786) — ESP32-S3R8, 1.8" 368×448 portrait AMOLED (SH8601 QSPI), FT3168 cap touch, AXP2101 PMU, QMI8658 IMU, XCA9554 IO expander, 16 MB flash. Two buttons (BOOT + PWR), fixed orientation. Build env: `waveshare_amoled_18`.

Plus per board:

- USB-C cable for flashing firmware and charging
- 3.7V Li-Po battery (MX1.25 2-pin connector, optional)

**Porting to another board:** the firmware is a thin HAL with per-board folders under `firmware/src/boards/`. Drop in a new folder and a new PlatformIO env — `main.cpp`, `ui.cpp`, and `splash.cpp` never need to change. See [`docs/porting/adding-a-board.md`](docs/porting/adding-a-board.md) for the walk-through and [`docs/porting/hal-contract.md`](docs/porting/hal-contract.md) for the interfaces a port must implement.

## Prerequisites

- Linux (tested on Ubuntu) or macOS
- [PlatformIO CLI](https://docs.platformio.org/en/latest/core/installation/index.html)
- Linux: `curl`, `bluetoothctl`, `busctl` (BlueZ Bluetooth stack)
- macOS: `python3` (the installer sets up a venv with `bleak` and `httpx`)
- Claude Code with an active subscription

## macOS installation

The macOS host pieces — Python daemon, LaunchAgent, and flash helper — were ported by [Chris Davidson (@lorddavidson)](https://github.com/lorddavidson). Thanks Chris!

### Flash the firmware

```bash
./flash-mac.sh                                 # AMOLED-2.16 (default), auto-detect port
./flash-mac.sh --board=18                      # AMOLED-1.8
./flash-mac.sh --board=216 /dev/cu.usbmodem1101  # explicit board + port
```

Pass `--board=216` or `--board=18` to pick the env explicitly. The default is the 2.16. Omitting the flag was fine when only one board existed; with two, an unselected build would flash both envs in sequence and the second upload would silently overwrite the first.

### Pair the device

After flashing, open **System Settings → Bluetooth** and click *Connect* next to "Clawdmeter". The daemon will discover it on its next scan (~30 s).

### Install the daemon

The daemon reads your Claude OAuth token from the macOS Keychain (service `Claude Code-credentials`), polls usage every 60 s, and pushes it to the display over BLE.

```bash
./install-mac.sh
```

The installer creates a Python venv in `daemon/.venv/`, installs `bleak` and `httpx`, renders a LaunchAgent into `~/Library/LaunchAgents/com.user.claude-usage-daemon.plist`, and loads it. The first run is launched interactively so macOS prompts for Bluetooth permission.

Useful commands:

```bash
launchctl list | grep claude-usage                                          # check it's running
tail -F ~/Library/Logs/claude-usage-daemon.out.log                          # live logs
launchctl unload ~/Library/LaunchAgents/com.user.claude-usage-daemon.plist  # stop
launchctl load -w ~/Library/LaunchAgents/com.user.claude-usage-daemon.plist # start
```

## Linux installation

### Flash the firmware

```bash
./flash.sh                              # AMOLED-2.16 (default), /dev/ttyACM0
./flash.sh --board=18                   # AMOLED-1.8
./flash.sh --board=216 /dev/ttyACM1     # explicit board + port
```

Or call PlatformIO directly — but you must pass `-e <env>`, otherwise `pio run` builds and flashes every defined env in sequence and the second upload silently overwrites the first:

```bash
cd firmware
pio run -e waveshare_amoled_216 -t upload --upload-port /dev/ttyACM0
```

### Pair the device

After flashing, the device advertises as "Claudemeter". Pair it once:

```bash
# Scan for the device
bluetoothctl scan le

# When "Claude Controller" appears, pair and trust it
bluetoothctl pair F4:12:FA:C0:8F:E5    # use your device's MAC
bluetoothctl trust F4:12:FA:C0:8F:E5
```

The MAC address is shown on the Bluetooth screen — press the middle (PWR) button to cycle to it.

### Install the daemon

The daemon polls your Claude usage every 60 seconds and sends it to the display over BLE.

```bash
./install.sh
systemctl --user start claude-usage-daemon
```

Check status: `systemctl --user status claude-usage-daemon`

View logs: `journalctl --user -u claude-usage-daemon -f`

## How it works

1. The daemon reads your Claude Code OAuth token from `~/.claude/.credentials.json`.
2. It makes a minimal API call to `api.anthropic.com/v1/messages` — one token of Haiku, basically free.
3. The usage numbers come straight out of the response headers (`anthropic-ratelimit-unified-5h-utilization` and friends).
4. The daemon connects to the ESP32 over BLE and writes a JSON payload to the GATT RX characteristic.
5. The firmware parses it and updates the LVGL dashboard.
6. The firmware also tracks the rate of change of session % over a 5-minute window and picks splash animations from the matching mood group.
7. The two side buttons are independent of all of this — they send Space and Shift+Tab as BLE HID keyboard input to the paired host directly.

## Physical buttons

The board has three side buttons. Left and right do the same thing on every screen; the middle button is screen-aware.

| Button           | GPIO         | Function                                                       |
| ---------------- | ------------ | -------------------------------------------------------------- |
| **Left**         | GPIO 0       | Hold to send Space (Claude Code voice-mode push-to-talk)       |
| **Middle** (PWR) | AXP2101 PKEY | Cycle screens (Usage ↔ Bluetooth); on splash, cycle animations |
| **Right**        | GPIO 18      | Press to send Shift+Tab (Claude Code mode toggle)              |

Space and Shift+Tab go out as standard BLE HID keyboard reports, so they trigger in whatever window has focus on the paired host — not just Claude Code.

## BLE protocol

The device advertises a custom GATT service alongside the standard HID keyboard service:

|                            | UUID                                   |
| -------------------------- | -------------------------------------- |
| **Data Service**           | `4c41555a-4465-7669-6365-000000000001` |
| RX Characteristic (write)  | `4c41555a-4465-7669-6365-000000000002` |
| TX Characteristic (notify) | `4c41555a-4465-7669-6365-000000000003` |
| **HID Service**            | `00001812-0000-1000-8000-00805f9b34fb` |

JSON payload format (written to RX):

```json
{ "s": 45, "sr": 120, "w": 28, "wr": 7200, "st": "allowed", "ok": true }
```

Fields: `s` = session %, `sr` = session reset (minutes), `w` = weekly %, `wr` = weekly reset (minutes), `st` = status, `ok` = success flag.

## Recompiling fonts

The `firmware/src/font_*.c` files are pre-compiled LVGL bitmap fonts. All
eleven of them (Tiempos 34/56, Styrene 12/14/16/20/24/28/48, Mono 18/32) are
regenerated in one step:

```bash
python3 tools/build_fonts.py            # all 11 fonts
python3 tools/build_fonts.py font_styrene_28.c font_mono_32.c   # just a subset
```

The script wraps `lv_font_conv` (called via `npx`, no global install needed)
and applies the LVGL 9 struct patch automatically. The glyph range covers
ASCII plus the German Latin-1 supplement (`Ä Ö Ü ß ä ö ü`, `§`, `·`) so the
UI labels render correctly under the Wine-Edition's German strings. The Mono
fonts additionally include the spinner glyphs (`·`, `…`, `✢ ✳ ✶ ✻ ✽`).

The script keeps the `#if LV_VERSION_CHECK(...)` guards that `lv_font_conv`
v1.5.3 emits — they evaluate true under LVGL 9 so the new struct fields
(`release_glyph`, `kerning`, `static_bitmap`, `fallback`, `user_data`) end
up populated and the fonts render correctly. If you bypass the script and
call `lv_font_conv` directly, replicate the same patch — without it the
fonts compile but render as invisible.

### CJK support

`firmware/src/font_cjk_16.c` covers the full CJK Unified Ideographs basic
block (U+4E00–U+9FFF, ~20k glyphs) plus ASCII, CJK punctuation, and
halfwidth/fullwidth forms. Generated from [Noto Sans CJK SC](https://github.com/notofonts/noto-cjk)
(SIL OFL 1.1) at 16px, 2bpp:

```bash
lv_font_conv --font NotoSansCJKsc-Regular.otf --size 16 --bpp 2 \
  --no-compress --format lvgl --lv-include 'lvgl.h' \
  -r '0x20-0x7E,0xB7,0x2014,0x2018-0x2019,0x201C-0x201D,0x2026,0x3000-0x303F,0x4E00-0x9FFF,0xFF00-0xFFEF' \
  -o firmware/src/font_cjk_16.c
```

Then apply the four LVGL 9 patches above. Because the font has >65k of
glyph bitmap data, the build needs `-DLV_FONT_FMT_TXT_LARGE=1` in
`platformio.ini` build flags so font descriptor offsets switch from
16-bit to 32-bit.

The CJK font is used for the Activity screen's user-prompt row and todo
content rows. The headline (28pt Styrene B) and titles stay ASCII-only
to preserve the brand font — Chinese text in those slots renders as
empty boxes. Add a `font_cjk_28.c` if full coverage is needed (~1MB
more flash).

## Converting Lucide icons

The UI uses a small set of [Lucide](https://lucide.dev) icons (bluetooth + battery states) converted to RGB565 / RGB565A8 C arrays for LVGL.

```bash
node tools/png_to_lvgl.js assets/icon_bluetooth_48.png icon_bluetooth_data ICON_BLUETOOTH_WIDTH ICON_BLUETOOTH_HEIGHT
```

Default tint is white (`0xFFFFFF`); Lucide PNGs ship as black-on-transparent and would render invisible against the dark UI without it. Pass `--no-tint` for pre-coloured artwork like the logo. Battery icons use RGB565A8 (alpha plane) so they blend cleanly over the splash; the rest are baked RGB565 over the panel colour. Paste the converter output into `firmware/src/icons.h`.

## Splash animations

The animations come from [claudepix.vercel.app](https://claudepix.vercel.app),
a library of Clawd sprites. `tools/scrape_claudepix.js` evaluates the
site's JavaScript in a Node VM to pull out frame data and palettes, then
`tools/convert_to_c.js` turns everything into RGB565 C arrays and writes
`firmware/src/splash_animations.h`.

To re-pull (e.g. when the source library updates):

```bash
node tools/scrape_claudepix.js
node tools/convert_to_c.js
pio run -d firmware -e waveshare_amoled_216 -t upload  # or -e waveshare_amoled_18
```

### Grid-agnostic engine

`splash.cpp` reads `grid` and `palette_size` from each `splash_anim_def_t` at
render time. The original Claudepix set is 20×20 with a 10-colour palette;
the Wine Edition is 48×48 with up to 32 colours per sprite. Both formats
coexist in the same build — cell pitch is computed per sprite as
`min(display_w, display_h) / sprite_grid`, so a 20×20 sprite gets 24-pixel
cells on the 2.16" panel and a 48×48 sprite gets 10-pixel cells. New sprite
sets can pick any integer grid that divides the display's smaller dimension
evenly; non-integer ratios are letterboxed.

`tools/convert_to_c.js` auto-detects the grid and palette length from each
JSON and accepts `--in <dir>` / `--out <file>` so multiple animation sets
(per brand theme) live alongside the default. See `tools/README.md` for the
schema and full pipeline.

### Wine Edition (jacques.de brand variant)

A "Wine Edition" theme is built as a separate PlatformIO env on the same
2.16" hardware. At compile time, `-DSPLASH_THEME_WINE` swaps:

- **Splash sprites** — `splash_animations_wine.h` (4 PixelLab-generated 48×48
  sprites with native multi-frame animations: bordeaux bottle with label
  shimmer, wine glass with red-wine swirl, grape cluster with leaf sway,
  natural cork still) instead of the Claudepix Clawd set.
- **Boot/UI logo** — `logo_wine.h` (80×80 pixel-art wine glass) instead of
  the Anthropic-style Clawd in `logo.h`.
- **Accent colour** — `THEME_ACCENT` switches to Bordeaux red `#7a2e36`
  (used by the bottom-of-screen spinner and brand glyphs) instead of the
  default terra-cotta.
- **Spinner vocabulary** — German wine verbs (Dekantieren, Schwenken,
  Verkosten, Karaffieren, Entkorken, …) instead of the English Claude-style
  Gerunds.

The non-splash UI strings (`Verbrauch`, `Aktuell`, `Wöchentlich`, `Gerät`,
`Adresse`, `Bluetooth zurücksetzen`, …) are German across all build envs —
the fonts include the Latin-1 umlaut range so they render without
substitution. If you want to keep the original Claude branding English,
revert the relevant strings in `firmware/src/ui.cpp`.

```bash
pio run -d firmware -e waveshare_amoled_216_wine                 # build
./flash-mac.sh --env=waveshare_amoled_216_wine                   # macOS
./flash.sh --env=waveshare_amoled_216_wine /dev/ttyACM0          # Linux
```

#### Wine asset pipeline (PixelLab Tier 2)

The wine sprites are generated end-to-end through the PixelLab MCP server
(subscription required for `animate_object`). Per sprite:

1. `create_1_direction_object(description, size=48, view='sidescroller')` —
   produces a 16-candidate review pack (costs 20 generations).
2. `select_object_frames(object_id, indices=[k])` — promotes the chosen
   candidate to its own completed sprite (free).
3. `animate_object(object_id, animation_description, frame_count=6/7)` —
   generates a multi-frame animation (~1 generation per frame).
4. Frame PNGs are downloaded into `tools/wine_data/pixellab/<sprite>_anim/`.
5. `tools/pixellab_to_claudepix.py --frames a.png,b.png,... --name "wine X"
   --out tools/wine_data/wine_X.json --grid 48 --palette 31 --hold 160`
   bbox-crops, square-pads, runs adaptive quantisation across the union of
   all frames (shared palette), and emits a claudepix-schema JSON.
6. `node tools/convert_to_c.js --in tools/wine_data
   --out firmware/src/splash_animations_wine.h` bakes everything into the
   on-device header.

The list of active wine sprites lives in `tools/wine_data/_index.json`. The
grouping into the four usage-rate buckets (idle, normal, active, heavy) is
defined inside the `#ifdef SPLASH_THEME_WINE` block in `firmware/src/splash.cpp`.

A legacy hand-pixel pipeline (`tools/legacy/build_wine_sprites.py`, 20×20
ASCII sprites) is still present for offline / no-subscription work. It
writes to a separate `tools/wine_data_handpixel/` directory so it cannot
overwrite the PixelLab-generated JSONs. See `tools/README.md` for how to
activate the hand-pixel set instead of the PixelLab one.

#### Wine logo

`tools/build_wine_logo.py` describes the 80×80 wine-glass logo as a 20×20
logical grid that's 4× nearest-neighbour scaled. Edit the `ART` string in
that file and re-run it to regenerate `firmware/src/logo_wine.h`.

### Per-build QA serial commands

`firmware/src/main.cpp` accepts these single-line commands on the USB serial
port (used by `screenshot.sh` and the iteration helpers):

| Command      | Effect                                                |
| ------------ | ----------------------------------------------------- |
| `screenshot` | dumps the LVGL framebuffer (`SCREENSHOT_START`/`_END`) |
| `next`       | advances the splash to the next sprite (`splash_next`)|
| `splash`     | switch to the splash screen                           |
| `usage`      | switch to the Usage screen                            |
| `bluetooth`  | switch to the Bluetooth screen                        |

`screenshot.sh` uses `screenshot`. Combining `next` + `screenshot` lets a CI
or iteration script walk through every sprite without physical button
presses; combining `usage` + `screenshot` (or `bluetooth`) does the same for
the non-splash screens, which is necessary because a fresh flash boots into
the splash and stays there until input.

## Credits

- Pixel-art Clawd animation by [@amaanbuilds](https://x.com/amaanbuilds), sourced from [claudepix.vercel.app](https://claudepix.vercel.app). Frame data and palettes scraped + converted by the tooling in `tools/`.
- Wine-Edition sprites generated with [PixelLab](https://pixellab.ai)'s MCP
  server (Tier 2: Pixel Artisan subscription) — see the Wine asset pipeline
  section.
- Lucide icon set ([lucide.dev](https://lucide.dev), MIT) for bluetooth and battery UI glyphs.
- Anthropic brand fonts (Tiempos Text, Styrene B) — see licensing warning below.
- Original Clawdmeter firmware by [hermannbjrgvin](https://github.com/hermannbjrgvin). The
  Bluetooth-screen credits in the Wine build read "Built by Sascha" / "Inspired
  by hermannbjrgvin" to reflect the brand-fork lineage.

## Licensing gray area warning

The software in this repository uses and adheres to the Anthropic brand guidelines and uses the same proprietary fonts that Anthropic has a license for but this software uses without permission as well as using assets from Anthropic such as the copyrighted Clawd mascot so even though the code in this repo is non-proprietary I will not license it myself under a copyleft license since this repo includes proprietary fonts and copyrighted assets. Please be aware of this if you fork or copy the code from this repo. **You have been warned!**
