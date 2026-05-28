# App- und Tray-Icons

In dieses Verzeichnis kommen die finalen PNG/ICNS/ICO-Dateien, die Tauri
beim Bundle-Build referenziert. Erwartete Dateinamen:

- `32x32.png`, `128x128.png`, `128x128@2x.png` — App-Icons
- `icon.icns` — macOS
- `icon.ico` — Windows
- `tray-ok.png`, `tray-warn.png`, `tray-error.png` — Menubar-States (Template-PNGs, monochrom)

Bis Phase 6 reicht ein einzelnes Platzhalter-Icon. Aktuell wird das Weinglas-
Logo der Wine Edition als App-Icon verwendet — Quelle ist dasselbe 20×20
Pixel-Art-Grid wie `firmware/src/logo_wine.h`, damit Gerät und Companion-App
identisch aussehen. Regenerieren:

```bash
# vom Repo-Root aus: PNG aus dem Wine-Logo-Grid + alle Tauri-Größen
python3 tools/build_wine_logo.py --png /tmp/wine_icon_src.png --png-size 1024
npx @tauri-apps/cli icon /tmp/wine_icon_src.png \
    -o companion/src-tauri/icons
```

`tauri icon` rendert daraus alle benötigten Größen plus ICNS/ICO sowie die
iOS- und Android-Mipmaps. Die Tray-Icons (`tray-ok.png`, `tray-warn.png`,
`tray-error.png`) bleiben monochrome Template-PNGs und werden von diesem
Workflow nicht überschrieben.
