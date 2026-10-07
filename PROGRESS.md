# Clawdmeter — Entwicklungsfortschritt

Stand: 2026-10-07. Lebende Datei — pro Meilenstein hier aktualisieren.

## Aktueller Meilenstein: Multi-Provider 2.1

Weiterentwicklung des generischen LLM-Provider-Dashboards: Bifrost-Gateway-
Integration mit Modell-Mix-Segmentierung, Sparkline-Entfernung aus
`tokens_abs`, OpenCode-Adapter-Entfernung (BREAKING). Provider-Familie:
Anthropic, Codex, Bifrost, Langdock — plus AWS Bedrock weiterhin pausiert.

> **AWS Bedrock pausiert (Stand 2026-05-24)**: Adapter-Code ist im Repo,
> wird aber vom Setup-Wizard nicht angeboten und vom Daemon nicht gepollt.
> Grund: CloudWatch + Service Quotas brauchen IAM-Credentials, die ein
> Bedrock-API-Key nicht abdeckt. Reaktivierung = IAM-Profil anlegen,
> `pip install boto3`, `enabled = true` in der config setzen. Details:
> [feature-documentation/providers/bedrock.md](feature-documentation/providers/bedrock.md).

### Erledigt ✅

- **Discovery-Phase** für Langdock, Bifrost, Bedrock + Referenz-Analyse von
  CodexBar — vollständig in [feature-documentation/providers/](feature-documentation/providers/)
  und [feature-documentation/research/](feature-documentation/research/).
  OpenCode-Discovery archiviert / entfernt.
- **Daemon-Refactor** zum Plugin-System:
  - Package `daemon/clawdmeter_daemon/` mit `providers/` (anthropic,
    codex, langdock, bifrost, bedrock), `config.py` (TOML), `ble.py`
    (Multi-Send + EOC-Marker), `polling.py` (Per-Provider TTL), `setup_wizard.py`
    (Auto-Detect + interaktiv), `cli.py` (`run`/`setup`/`doctor`/`config`).
  - OpenCode-Adapter entfernt; Sparkline-Strecke aus Daemon+Firmware gelöscht.
  - Bestehende Anthropic-Logik 1:1 als `providers/anthropic.py` migriert.
  - Config-Schema unter `~/.config/clawdmeter/config.toml` mit `[[provider]]`-
    Blöcken; jedes Provider opt-in über `enabled = true`.
- **BLE-Protokoll v2** (rückwärts-inkompatibel):
  - Pro Polling-Zyklus N Provider-JSONs + `{"end":1}` als Cycle-Marker.
  - Felder: `p / n / note / k / m1 / m2 / m3 / r1 / r2 / pace / regen / cur / st / ok`.
  - Vier `kind`-Werte: `pct_window`, `cost_budget`, `tokens_abs`, `tpm_rpm`.
- **Firmware-Refactor**:
  - `UsageData` → `UsageState { ProviderUsage[6] }` in [firmware/src/data.h](firmware/src/data.h).
  - Multi-Provider-Parser + EOC-Pruning in [firmware/src/main.cpp](firmware/src/main.cpp).
  - Komplett neuer Render-Switch in [firmware/src/ui.cpp](firmware/src/ui.cpp)
    — vier kind-spezifische Layouts, dynamische Screen-Liste, Empty-State,
    Pace-Indikator (7 Stufen, Unicode-Pfeile).
  - BLE-Gerätename auf `"Clawdmeter"` umbenannt.
- **Install-Scripts** für macOS / Linux / Windows auf neuen Daemon-Namen
  und integrierten Setup-Wizard umgestellt. boto3-Install ist auf einen
  Hinweis-Befehl reduziert (Bedrock-Adapter ist pausiert).
- **Build-Test** aller drei PlatformIO-Envs (`standard-216`, `standard-180`,
  `wine-216` — letzteres ist neuer Default für `./flash-mac.sh`) — alle erfolgreich.

### In Arbeit 🔧

- **Bifrost-Endgültige QA** mit echtem Gateway und virtuellen Keys.
- **Firmware-Screenshot** des `cost_budget` mit Segmentbalken für README
  (Layout-Werte für beide Display-Größen wird gerade noch angepasst).

### Offen 📋

- **Provider-Adapter-Live-Tests** — die aktiven Adapter (Codex, Langdock,
  Bifrost) sollten gegen echte APIs verifiziert werden.
  Erwartete Nacharbeit:
  - Codex-`wham/usage`-Schema mit echtem Plus/Pro-Account verifizieren.
  - Langdock-CSV-Spaltennamen via jacques.de-Workspace prüfen
    (drei Workspace-Modi BYOK/hybrid/managed Unterscheidung prüfen).
  - Bifrost-Quota-Endpunkt gegen Live-Gateway mit mehreren Budgets testen.
- **Bedrock-Reaktivierung (deferred)** — sobald ein Read-Only-IAM-User
  eingerichtet ist: `enabled = true`, `pip install boto3`, Quota-Namen-
  Lookup am echten Account verifizieren.
- **Sleep/Idle-Verhalten** mit mehreren Screens validieren (heute springt
  der UI-Cycler nach Wake auf den ersten Provider zurück; das ist OK, aber
  ggf. „letzter aktiver Screen" merken wäre netter).
- **Touch-Mute pro Provider** als Quality-of-Life (langer Druck auf
  Mittelknopf → Provider-Screen ausblenden bis Daemon-Restart). Nicht
  kritisch fürs MVP.

## Voriger Meilenstein: Wine Edition (2026-05-24)

Brand-Fork für jacques.de — abgeschlossen, weiter im Wartungsmodus. Splash-
Engine grid-agnostic, PixelLab-Pipeline für Wein-Sprites, deutsche
Spinner-Vokabel, Bordeaux-Akzent. Siehe Commits ab `Wine Edition`-Tag und
das obere CLAUDE.md.

## MVP-Definition (zum Abhaken)

Der Clawdmeter 2.1 (Multi-Provider mit Bifrost) ist „Release-ready", wenn:

- [x] Daemon kann ohne Config gestartet werden und schreibt Default-TOML.
- [x] `clawdmeter-daemon setup` führt durch die aktiven Provider (Anthropic,
      Codex, Bifrost, Langdock).
- [x] Firmware compiliert für alle drei Envs (`wine-216`, `standard-216`,
      `standard-180`).
- [x] Empty-State auf dem Gerät zeigt klare Anweisung wenn nichts konfiguriert.
- [x] OpenCode-Adapter entfernt, Sparkline-Strecke aus Daemon+Firmware gelöscht.
- [x] Bifrost-Provider mit Modell-Mix-Segmentierung dokumentiert + implementiert.
- [x] README + feature-docs weisen klar auf den pausierten Bedrock-Adapter hin.
- [x] feature-documentation hat einen multi-provider/ Block mit Datenfluss,
      Kind-Layouts (incl. segmentierter `cost_budget`), und BLE-Beispiel.
- [ ] Bifrost-Adapter live gegen ein Gateway mit mehreren Budgets verifiziert.
- [ ] Anthropic + ein zweiter Provider (Langdock/Bifrost/Codex) live verifiziert.
