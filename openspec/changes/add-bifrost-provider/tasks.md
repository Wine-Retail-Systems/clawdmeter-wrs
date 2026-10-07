# Tasks

## 1. Daemon: gemeinsamer Budget-Helfer

- [ ] 1.1 `daemon/clawdmeter_daemon/providers/_budget.py` anlegen: Reset-Dauer parsen, nächsten Reset berechnen (Kalendermonat/-quartal, Weiterzählen bei verpasstem Reset), Pace −3..+3, Status-Schwellen (D2). Verifikation: `python3 -m unittest daemon/tests/test_budget.py` mit Fällen für `1d`, `1w`, `1M` über einen Monatswechsel, `1Q` und einen veralteten `last_reset`
- [ ] 1.2 Langdock auf den Helfer umstellen (`_estimate_pace`, Reset bis Monatsende). Verifikation: Unit-Test, dass Pace und `r2` für ein festes Datum dieselben Werte wie vorher liefern; `python3 -m py_compile` auf alle geänderten Module

## 2. Daemon: Bifrost-Adapter

- [ ] 2.1 `providers/bifrost.py` mit `register("bifrost", ...)`: Abfrage von `/api/governance/virtual-keys/quota` per `httpx`, Bearer aus `api_key_env`, Timeout, Abbildung auf `cost_budget` (m1, m2 mit Override, r2, pace, status, `cur = USD`), Notiz aus `virtual_key_name` (D3, D5). Verifikation: Unit-Tests mit der live erhobenen Antwortstruktur als Fixture (ohne Key) für Monatsbudget, Override, mehrere Budgets, kein Budget
- [ ] 2.2 Familien-Anteile aus `per_model_usage` (D4): Teilstring-Erkennung, Summierung, 1-%-Schwelle, höchstens drei Familien plus `Rest`, Normierung auf 100. Verifikation: Unit-Tests für Gruppierung über Versionen/Regionen, Kleinstanteile, fehlende Modelldaten, Summe exakt 100
- [ ] 2.3 Fehlerpfad: 401/403, 5xx, Timeout und Strukturfehler liefern `stale`/`ok = false` mit letztem Stand; kein Key → Log mit Variablennamen, kein Screen. Verifikation: Unit-Tests mit gemocktem Transport, plus Prüfung per `grep`, dass kein Log-Aufruf den Key-Wert enthält
- [ ] 2.4 Registrierung: Import in `providers/__init__.py`, Hidden-Import in `tools/build_daemon_bundle.py`, ID-Liste in `polling.py`, Whitelist und Detect-Zweig in `ipc_server.py`. Verifikation: `python3 -c "from clawdmeter_daemon.providers import create"` findet `bifrost`

## 3. Daemon: Einrichtung

- [ ] 3.1 Default-Config-Block `bifrost` in `config.py` (deaktiviert, `api_key_env`, `base_url`, `poll_seconds = 120`, `display_name = "LLM Gateway"`). Verifikation: frisch erzeugte Default-Config parst und enthält den Block
- [ ] 3.2 Auto-Detect (`ANTHROPIC_AUTH_TOKEN` mit Präfix `sk-bf-` aus Umgebung bzw. `~/.claude/settings.json`, URL aus `ANTHROPIC_BASE_URL` ohne Pfad) und `wizard_bifrost` im CLI-Wizard; Ausgabe höchstens maskiert. Verifikation: Unit-Test mit temporärer `settings.json`; manueller Lauf von `clawdmeter setup` zeigt Quelle und maskierten Key
- [ ] 3.3 IPC `provider-save` mit `{"source": "claude-settings"}` kopiert den erkannten Key serverseitig nach `secrets.env` (D5). Verifikation: IPC-Aufruf per Socket schreibt die Variable, `config.toml` enthält keinen Key, Daemon lädt neu
- [ ] 3.4 `clawdmeter doctor` prüft für Bifrost Key-Vorhandensein und Erreichbarkeit (Statuscode). Verifikation: `clawdmeter doctor` meldet 200 mit gültigem Key und einen klaren Hinweis ohne Key

## 4. Daemon: OpenCode und Sparkline entfernen

- [ ] 4.1 `providers/opencode.py` löschen; Import, Default-Config-Block, `detect_opencode_*`, `wizard_opencode`, IPC-Zweige und Hidden-Import entfernen. Verifikation: `grep -ri opencode daemon tools` ohne Treffer; Daemon startet mit einer Config, die noch `id = "opencode"` enthält, und loggt „Unknown provider id"
- [ ] 4.2 `correlate_backend_quota` und den Aufruf in `run_cycle` entfernen; `extra["spark"]`/`sp` aus `Snapshot.to_payload()` entfernen. Verifikation: `grep -rn "spark\|correlate_backend_quota" daemon` ohne Treffer; Langdock-managed-Payload enthält weiterhin `sh`

## 5. Firmware

- [ ] 5.1 `data.h` und `main.cpp`: `spark[]`, `spark_set` und Parsing von `sp` entfernen, Kommentare zu `PK_TOKENS_ABS`/`shares` aktualisieren. Verifikation: `pio run -d firmware -e wine-216` baut ohne Warnung zu ungenutzten Symbolen
- [ ] 5.2 `tokens_abs`: Sparkline-Chart und „vs. gestern" entfernen, Donut nach oben rücken. Verifikation: Screenshot eines Langdock-managed-Screens per `./screenshot.sh` zeigt Wert, Donut und Reset ohne Lücke
- [ ] 5.3 `cost_budget`: Segmentbalken-Container statt `lv_bar`, Graustufenpalette, Legendenzeile, Prozentangabe in `pct_color`, Rückfall auf ein Segment ohne `sh`, Ausblenden bei `m2 = 0` (D6). Verifikation: Build aller drei Envs (`wine-216`, `standard-216`, `standard-180`) erfolgreich
- [ ] 5.4 Layoutwerte für groß/kompakt in `compute_layout()` festlegen. Verifikation: Screenshots auf 480×480 und 368×448 (falls Gerät verfügbar) mit vier Anteilen, ohne Anteile, bei 92 % und bei über 100 %, gelesen und ohne Überlappungen

## 6. Companion-App

- [ ] 6.1 `lib/ipc.ts` (`ProviderId` mit `bifrost`, ohne `opencode`) und `lib/strings.de.ts` (Texte für Bifrost, OpenCode entfernt). Verifikation: `npm run build` in `companion/` ohne Typfehler
- [ ] 6.2 `SetupWizard.tsx`: Bifrost-Schritt mit „Erkannten Key übernehmen" (`provider-save` mit `source: claude-settings`) und manueller Eingabe über `secret-write`; OpenCode aus `ORDER` entfernen. Verifikation: `npm run build`; im `tauri dev`-Lauf zeigt der Wizard die Erkennung und speichert, danach erscheint der Screen auf dem Gerät

## 7. Ende-zu-Ende

- [ ] 7.1 Daemon mit echtem Key gegen das Gateway laufen lassen und Gerät mit neuer Firmware verbinden. Verifikation: `./screenshot.sh` des Bifrost-Screens zeigt Betrag, Limit, segmentierten Balken mit Opus/Sonnet und Reset-Countdown passend zu `clawdmeter doctor`
- [ ] 7.2 Kompatibilität prüfen: neue Firmware mit einem Payload, der `sp` enthält (seriell oder alter Daemon), und alter Daemon-Payload ohne `sh` bei `cost_budget`. Verifikation: Gerät rendert beide ohne Fehler im seriellen Log

## 8. Dokumentation

- [ ] 8.1 `feature-documentation/providers/bifrost.md` anlegen (Endpunkt, Auth, Mapping, Familien, Grenzen, geprüfte Bifrost-Version) und `providers/opencode.md` löschen. Verifikation: Datei vorhanden, Links aus README funktionieren
- [ ] 8.2 `feature-documentation/multi-provider/*` (BLE-Beispielpayload, `config-toml.md`, `data-flow.md`, `kind-layouts.md` mit Segmentbalken) und `companion-app/*` aktualisieren. Verifikation: `grep -ri opencode feature-documentation` nur noch in `research/`
- [ ] 8.3 `README.md` (Provider-Tabelle, Screenshot), `PROGRESS.md`, `PRODUCT.md`, `CLAUDE.md`/`AGENTS.md`, `.claude/agents/ble-daemon-protocol-expert.md` anpassen; OpenCode-Screenshots aus `screenshots/` entfernen und den neuen Bifrost-Screenshot als `screenshots/bifrost.png` ablegen. Verifikation: `grep -rli opencode --exclude-dir=node_modules --exclude-dir=research --exclude-dir=openspec .` ohne Treffer außerhalb der Change-Artefakte
