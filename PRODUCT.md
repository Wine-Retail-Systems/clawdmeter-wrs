# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

Die Companion-App ist eine Tauri-2-Desktop-App (macOS, Windows) mit React-Oberfläche in der System-Webview. Daneben gibt es eine zweite, nicht-webbasierte Oberfläche: die Geräte-UI der ESP32-S3-Firmware (LVGL 9 auf AMOLED). Beide gehören zum Produkt.

## Users

Entwickler im JAC-/WRS-Team, die täglich mit LLM-Werkzeugen arbeiten (Claude Code, OpenAI Codex, Langdock, OpenCode) und ihr Kontingent im Blick behalten wollen, ohne dafür einen Browser-Tab oder ein Terminal zu öffnen. Sie sind technisch versiert, wollen das Gerät aber ohne Shell-, Python- oder PlatformIO-Setup in Betrieb nehmen.

Ihr Job: einmal einrichten (flashen, koppeln, Provider-Zugänge hinterlegen), danach nebenbei auf einen Blick sehen, wie viel vom 5-Stunden- und Wochenfenster bzw. vom Budget verbraucht ist und wann es zurückgesetzt wird.

## Product Purpose

Clawdmeter ist ein Hardware-Monitor für LLM-Nutzung auf dem Schreibtisch. Ein Host-Daemon pollt die aktivierten Provider und schickt die Werte per BLE an ein ESP32-S3-Gerät mit AMOLED-Display; pro aktivem Provider gibt es dort einen Screen.

Die Companion-App kapselt die drei Jobs, die früher Shell-Skripte erledigten: **Firmware flashen**, **Gerät koppeln und Provider einrichten**, **Daemon-Lifecycle und Status**. Erfolg heißt: Ein Entwickler kommt vom Download bis zum ersten Messwert auf dem Gerät, ohne eine Shell zu öffnen, und muss die App danach nur noch bei Problemen ansehen.

## Positioning

Ein physisches, immer sichtbares Instrument statt eines weiteren Dashboards: Die Auslastung mehrerer LLM-Provider steht dauerhaft auf einem eigenen Display neben dem Bildschirm, gespeist von einem lokalen Daemon. Zugangsdaten bleiben auf dem eigenen Rechner. Die Companion-App ist das Werkzeug dafür, nicht das Produkt selbst.

## Operating Context

- **Geräte-UI:** Status-Spinner am unteren Rand, PWR-Taste blättert durch die Provider-Screens und den Bluetooth-Screen; die Splash-Animation läuft bis zum ersten Tastendruck. Bildschirme: 480×480 (AMOLED-2.16) oder 368×448 (AMOLED-1.8).
- **Companion-App:** Sie läuft im Hintergrund (Tray-Icon mit Status ok/warn/error), ihr Fenster wird nur zum Einrichten oder bei Störungen geöffnet. Abläufe: Landing → Flash-Wizard (drei Firmware-Varianten, Default `wine-216`) → Koppeln → Setup-Wizard (Provider-Zugänge) → Status.
- **Daemon:** Python-Paket, ausgeliefert als PyInstaller-Onefile in der App; IPC zur App per Unix-Socket bzw. Named Pipe. Power-User-Pfad über `install-*.sh`/`flash-*.sh` bleibt bestehen.

## Capabilities and Constraints

- Provider: Anthropic Claude (5h- und 7d-Fenster), OpenAI Codex (5h + Weekly, Plan-Typ), Langdock (EUR-Budget), OpenCode (Tokens heute, Histogramm, Backend-Mix). AWS Bedrock ist pausiert; der Adapter existiert, wird aber nicht angeboten.
- Pro Provider ein Screen-Typ nach `kind` (`pct_window`, `cost_budget`, `tokens_abs`, `tpm_rpm`); maximal sechs Provider-Slots auf dem Gerät.
- Sprache: nur Deutsch, in App und Firmware (MVP). Glyphenbereich der Gerätefonts umfasst deutsche Umlaute.
- Plattformen der App: macOS (aarch64) und Windows. Linux ist kein Ziel im MVP.
- Offline-fähig: Firmware-Binaries und Daemon sind im App-Bundle eingebettet. Keine Cloud-Telemetrie, nur lokale Crash-Logs.
- Die App folgt Hell/Dunkel der Systemeinstellung; einen eigenen Umschalter gibt es nicht.
- Nicht im MVP: OTA-Firmware-Update über BLE, Sprachumschaltung, Linux-Build.

## Brand Commitments

- **Die Companion-App heißt neutral „Clawdmeter".** Es gibt keine separate Wine-App; die Wine Edition ist ein Firmware-Theme und nur der Default im Flash-Wizard.
- **Visuelle Identität der App ist bewusst Bordeaux mit Weinglas-Mark** (bestätigt 2026-10-07). Der Name bleibt markenneutral; Farbe und Mark sind keine Übergangslösung.
- **Firmware-Varianten:** Standard-Builds tragen das Anthropic-„Clawd"-Logo und den Terra-Cotta-Akzent. Die Wine Edition (Fork für jacques.de) tauscht Logo (Weinglas), Akzent (Bordeaux), Splash-Sprites (PixelLab, 48×48) und Spinner-Vokabular („Karaffieren…", „Dekantieren…").
- Grafiken stammen aus Drittquellen (Claudepix, PixelLab, Lucide); selbst gezeichnete Ersatzgrafiken sind nicht erwünscht, wenn ein Fremd-Asset vorgesehen ist.

## Evidence on Hand

- Geräte-Screenshots: `screenshots/` (anthropic, codex, langdock, opencode, splash, bluetooth); `screenshot.sh` erzeugt neue direkt vom Gerät.
- Logos und Fonts: `assets/` (`logo_80.png`, Tiempos, Styrene, DejaVu Sans Mono, Lucide-Icons), `firmware/src/logo_wine.h`.
- Spezifikation und Stand: `feature-documentation/companion-app/PLAN.md`, `PROGRESS.md`, `feature-documentation/providers/`.
- Es gibt keine Nutzer-Testimonials, Kennzahlen oder Fremdkunden; solche Angaben dürfen nicht erfunden werden.

## Product Principles

1. **Einrichten ohne Shell.** Jeder Schritt, der früher ein Skript brauchte, muss in der App ohne Terminal gelingen; der Shell-Pfad bleibt nur für Power-User.
2. **Das Gerät ist die Hauptoberfläche.** Die App tritt zurück, sobald alles läuft, und meldet sich nur, wenn eine Handlung nötig ist.
3. **Auf einen Blick lesbar.** Auslastung, Reset-Zeit und Zustand müssen aus Schreibtischdistanz erfassbar sein, ohne Interaktion.
4. **Zugangsdaten bleiben lokal.** Keys werden nur auf dem Rechner des Nutzers gespeichert, nie geloggt oder übertragen außer an den jeweiligen Provider.
5. **Provider sind opt-in und gleichrangig.** Jeder Provider wird einzeln aktiviert; keiner ist Voraussetzung für den anderen.
