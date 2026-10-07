# Proposal

## Why

Das Team arbeitet mit Claude Code zunehmend über das WRS-LLM-Gateway (Bifrost), dessen Kosten pro Virtual Key gegen ein Monatsbudget laufen. Dieses Budget ist heute nur im Gateway-Admin sichtbar; auf dem Clawdmeter fehlt genau die Zahl, die für Gateway-Nutzer zählt. OpenCode wird im Team dagegen nicht mehr genutzt und trägt Sonderlogik (Sparkline, Backend-Quota-Korrelation), die sonst niemand braucht.

## What Changes

- **Neuer Provider `bifrost`**: Der Daemon fragt den Self-Service-Endpunkt `GET /api/governance/virtual-keys/quota` des Gateways mit dem Virtual Key des Nutzers ab (kein Admin-Zugang) und zeigt Verbrauch gegen Budget in USD mit Reset-Countdown und Pace als `cost_budget`-Screen.
- **Modell-Mix im Budgetbalken**: Der Balken des `cost_budget`-Screens wird nach Modellfamilie (Opus, Sonnet, Haiku, Andere) segmentiert eingefärbt, darunter steht eine Legendenzeile mit Anteilen. Ohne Anteile im Payload bleibt der bisherige einfarbige Balken.
- **Einrichtung**: Setup-Wizard (CLI) und Companion-App bieten Bifrost an, erkennen einen vorhandenen Gateway-Key aus der Claude-Code-Konfiguration und speichern ihn nur lokal in `secrets.env`.
- **BREAKING – OpenCode entfernt**: Adapter, Default-Config-Block, Wizard-Schritt, IPC-Zweige, Companion-Eintrag, Build-Hidden-Import, Doku und Screenshots entfallen. Eine bestehende `config.toml` mit `id = "opencode"` führt zu einem geloggten „unbekannter Provider" statt eines Screens.
- **BREAKING (Protokoll, rückwärtsverträglich lesend) – Sparkline entfernt**: Das Payload-Feld `sp`, die 24-Stunden-Sparkline und der Vergleich „vs. gestern" im `tokens_abs`-Screen sowie die Backend-Quota-Korrelation entfallen. Der `tokens_abs`-Screen mit Donut bleibt für Langdock („managed") bestehen.

## Capabilities

### New Capabilities
- `bifrost-provider`: Abfrage des Gateway-Kontingents per Virtual Key, Abbildung auf den `cost_budget`-Payload (Budgetwahl, Reset, Pace, Status, Modellfamilien-Anteile), Fehlerverhalten und Einrichtung inkl. Auto-Detect und lokaler Key-Ablage.
- `budget-screen-model-mix`: Darstellung des `cost_budget`-Screens auf dem Gerät mit nach Anteilen segmentiertem Budgetbalken und Legende, inklusive Rückfall auf den einfarbigen Balken.

### Modified Capabilities
<!-- Keine: Es gibt noch keine Haupt-Specs im Projekt. Die Entfernung von OpenCode und der Sparkline ist in What Changes und design.md beschrieben. -->

## Impact

- **Daemon** (`daemon/clawdmeter_daemon/`): neuer Adapter `providers/bifrost.py`; `providers/opencode.py` entfällt; Anpassungen in `providers/__init__.py`, `providers/base.py` (`sp` entfällt), `config.py` (Default-Config), `setup_wizard.py`, `polling.py` (Korrelation entfällt), `ipc_server.py` (Detect/Whitelist), `cli.py` (`doctor`).
- **Firmware** (`firmware/src/`): `ui.cpp` (`cost_budget` mit Segmentbalken und Legende; Sparkline aus `tokens_abs` entfernt), `data.h` (`spark[]` entfällt), `main.cpp` (Parsing von `sp` entfällt). Alle drei Envs (`wine-216`, `standard-216`, `standard-180`) müssen neu gebaut und geflasht werden; die neue Firmware versteht ältere Daemons weiterhin.
- **Companion-App** (`companion/src/`): `SetupWizard.tsx`, `lib/ipc.ts`, `lib/strings.de.ts`. Das Rust-Backend ist nicht betroffen.
- **Build**: `tools/build_daemon_bundle.py` (Hidden-Import).
- **Externe Abhängigkeit**: Bifrost-Endpunkt `/api/governance/virtual-keys/quota` (vorhanden seit v1.6.0, Gateway läuft auf v2.2.5, live geprüft am 2026-10-07). Keine Änderung am Gateway-Repo.
- **Doku**: `README.md`, `PROGRESS.md`, `PRODUCT.md`, `CLAUDE.md`/`AGENTS.md`, `.claude/agents/ble-daemon-protocol-expert.md`, `feature-documentation/providers/` (neu `bifrost.md`, `opencode.md` entfällt), `feature-documentation/multi-provider/*`, `feature-documentation/companion-app/*`, `screenshots/`.
