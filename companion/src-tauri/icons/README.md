# App- und Tray-Icons

In dieses Verzeichnis kommen die finalen PNG/ICNS/ICO-Dateien, die Tauri
beim Bundle-Build referenziert. Erwartete Dateinamen:

- `32x32.png`, `128x128.png`, `128x128@2x.png` — App-Icons
- `icon.icns` — macOS
- `icon.ico` — Windows
- `tray-ok.png`, `tray-warn.png`, `tray-error.png` — Menubar-States (Template-PNGs, monochrom)

Bis Phase 6 reicht ein einzelnes Platzhalter-Icon. Empfehlung:

```bash
# vom Repo-Root aus
cp ../assets/logo-512.png companion/src-tauri/icons/icon.png
npx @tauri-apps/cli icon companion/src-tauri/icons/icon.png \
    -o companion/src-tauri/icons
```

`tauri icon` rendert daraus alle benötigten Größen plus ICNS/ICO.
