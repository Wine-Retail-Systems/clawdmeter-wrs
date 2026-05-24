# Clawdmeter — Entwicklungsfortschritt

Stand: 2026-05-24. Lebende Datei — pro Meilenstein hier aktualisieren.

## Aktueller Meilenstein: Multi-Provider 2.0

Vom reinen Anthropic-Claude-Monitor zum generischen LLM-Provider-Dashboard.
Ziel: mehrere Provider-Familien (Anthropic, Codex, Langdock, OpenCode —
plus AWS Bedrock als pausierter Adapter) parallel auf einem Gerät, opt-in
pro Provider, mit pace + currency + regen als optionalen Metadaten.

> **AWS Bedrock pausiert (Stand 2026-05-24)**: Adapter-Code ist im Repo,
> wird aber vom Setup-Wizard nicht angeboten und vom Daemon nicht gepollt.
> Grund: CloudWatch + Service Quotas brauchen IAM-Credentials, die ein
> Bedrock-API-Key nicht abdeckt. Reaktivierung = IAM-Profil anlegen,
> `pip install boto3`, `enabled = true` in der config setzen. Details:
> [feature-documentation/providers/bedrock.md](feature-documentation/providers/bedrock.md).

### Erledigt ✅

- **Discovery-Phase** für Langdock, OpenCode, Bedrock + Referenz-Analyse von
  CodexBar — vollständig in [feature-documentation/providers/](feature-documentation/providers/)
  und [feature-documentation/research/](feature-documentation/research/).
- **Daemon-Refactor** zum Plugin-System:
  - Neues Package `daemon/clawdmeter_daemon/` mit `providers/` (anthropic,
    codex, langdock, opencode, bedrock), `config.py` (TOML), `ble.py`
    (Multi-Send + EOC-Marker), `polling.py` (Per-Provider TTL + Backend-
    Quota-Korrelation), `setup_wizard.py` (Auto-Detect + interaktiv),
    `cli.py` (`run`/`setup`/`doctor`/`config`).
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

- Feature-Dokumentation der neuen Architektur unter
  `feature-documentation/multi-provider/`.
- README komplett neu schreiben — Clawdmeter ist nun ein eigenständiges
  Projekt, nicht mehr „a Claude usage monitor".

### Offen 📋

- **Provider-Adapter-Live-Tests** — die neuen aktiven Adapter (Codex,
  Langdock, OpenCode) haben noch keinen Roundtrip gegen echte APIs gesehen.
  Erwartete Nacharbeit:
  - Codex-`wham/usage`-Schema mit echtem Plus/Pro-Account verifizieren
    (`limit_window_seconds`-Konstanten, Plan-Typ-Strings).
  - Langdock-CSV-Spaltennamen via `_log_unknown_columns_once`-Output gegen
    den jacques.de-Workspace nachziehen (Adapter ist auf `/export/users`
    umgestellt, Request-Body + Response-Wrapper sind doc-konform, drei
    Workspace-Modi BYOK/hybrid/managed werden unterschieden).
  - OpenCode-DB-Schema bei nächstem Migrations-Drop neu prüfen.
- **Bedrock-Reaktivierung (deferred)** — sobald ein Read-Only-IAM-User
  eingerichtet ist: `enabled = true`, `pip install boto3`, Quota-Namen-
  Lookup am echten Account verifizieren.
- **Geräte-Foto + Screenshots** mit echtem Multi-Provider-Dashboard für die
  README — sobald die Hardware läuft.
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

Der Clawdmeter 2.0 ist „MVP-ready", wenn:

- [x] Daemon kann ohne Config gestartet werden und schreibt Default-TOML.
- [x] `clawdmeter-daemon setup` führt durch die aktiven Provider (Anthropic,
      Codex, Langdock, OpenCode).
- [x] Firmware compiliert für alle drei Envs (`wine-216`, `standard-216`,
      `standard-180`).
- [x] Empty-State auf dem Gerät zeigt klare Anweisung wenn nichts konfiguriert.
- [x] README + feature-docs weisen klar auf den pausierten Bedrock-Adapter hin.
- [x] feature-documentation hat einen multi-provider/ Block mit Datenfluss
      und Kind-Layouts.
- [ ] Anthropic-Adapter spielt 1:1 die alten Werte aus (Regression-Test
      gegen einen Live-Account).
- [ ] Mindestens ein zweiter aktiver Provider live verifiziert (OpenCode-
      DB-Lesepfad ist am ehesten testbar — keine externen Credentials nötig).
