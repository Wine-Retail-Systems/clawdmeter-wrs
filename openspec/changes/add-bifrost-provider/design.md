# Design

## Context

Motivation und Umfang: siehe `proposal.md`. Verbindliches Verhalten: `specs/bifrost-provider/spec.md` und `specs/budget-screen-model-mix/spec.md`.

Ausgangslage im Code:

- **Daemon:** Provider registrieren sich selbst (`register(...)` am Modulende) und werden in `providers/__init__.py` explizit importiert. Das ist nötig, damit PyInstaller sie findet; zusätzlich steht jedes Modul als Hidden-Import in `tools/build_daemon_bundle.py`. Ein Adapter liefert ein `Snapshot`, dessen `to_payload()` das BLE-JSON baut. `extra["shares"]` wird bereits generisch zu `sh` (höchstens 4 Einträge, Kürzel höchstens 7 Zeichen, ganzzahlige Prozent).
- **Langdock** ist das nächste Vorbild: HTTP-Abfrage mit `httpx.AsyncClient`, Key über `api_key_env` aus Umgebung bzw. `secrets.env`, `_estimate_pace` und `_stale_snapshot`.
- **Firmware:** Der Parser in `main.cpp` liest `sh` für jeden `kind`, aber nur `build_tokens_abs` zeichnet es (Donut). `build_cost_budget` nutzt ein einzelnes `lv_bar` in `pct_color`. Die Sparkline (`spark[24]`, Feld `sp`) wird nur von OpenCode gespeist.
- **Gateway:** Bifrost v2.2.5. `GET /api/governance/virtual-keys/quota` mit `Authorization: Bearer sk-bf-…` liefert `virtual_key_name`, `budgets[]` (`max_limit`, `current_usage`, `reset_duration`, `last_reset`, optional `override_amount`, `per_model_usage[]`) und `rate_limit`. Live geprüft am 2026-10-07: 200, ein Monatsbudget, zehn Modelleinträge, kein `calendar_aligned` in der Antwort.

## Goals / Non-Goals

**Goals:**
- Bifrost-Adapter, der ohne Admin-Rechte funktioniert und Fehler sauber als `stale` meldet.
- Gemeinsamer Budget-Baustein im Daemon (Reset-Berechnung, Pace, Status), damit Bifrost und Langdock dieselbe Logik nutzen können.
- Segmentierter Budgetbalken als eigenständiges Firmware-Element, das jeder `cost_budget`-Provider nutzt, sobald er `sh` sendet.
- Rückstandsfreies Entfernen von OpenCode und der Sparkline-Strecke.

**Non-Goals:**
- Rate-Limit-Anzeige (`rate_limit`): beim Gateway derzeit nicht konfiguriert. Der Adapter ignoriert es.
- Anteile für Langdock im `cost_budget`-Modus.
- Änderungen am Gateway-Repo oder an Gateway-Budgets.
- Vorschlag im Wizard, den Anthropic-Abo-Screen für Gateway-Nutzer abzuschalten. Beide Screens bleiben unabhängig.
- Automatische Migration bestehender `config.toml`-Dateien. Ein verwaister `opencode`-Block wird nur geloggt.

## Decisions

### D1 Self-Service-Endpunkt statt Admin-API
Der Adapter nutzt ausschließlich `/api/governance/virtual-keys/quota` mit dem Virtual Key.
*Alternativen:* Admin-Basic-Auth (liefert über `/api/governance/virtual-keys` die Klartext-Keys aller Nutzer, als Schreibtisch-Credential inakzeptabel); eigener `/usage`-Sidecar im Gateway-Repo (unnötig, seit der Endpunkt nachgewiesen ist).

### D2 Gemeinsamer Budget-Helfer `providers/_budget.py`
Er enthält rein funktionale Bausteine ohne I/O: Reset-Dauer parsen (`30s`, `5m`, `1h`, `1d`, `1w`, `1M`, `1Q`), nächsten Reset berechnen, Pace aus Verbrauchsanteil gegen Fensteranteil, Status-Schwellen. `1M` und `1Q` rechnen in Kalendermonaten ab `last_reset`. Liegt der errechnete Reset in der Vergangenheit (verspäteter Reset im Gateway), wird so lange um eine Periode weitergezählt, bis er in der Zukunft liegt. Langdocks `_estimate_pace` wird auf den Helfer umgestellt; sein Verhalten bleibt gleich, weil es ein `1M`-Fenster ab Monatsanfang ist.

*Nachtrag aus der Umsetzung:* Die Pace-Schwellen sind parametrisiert. Langdock behält seine bisherigen Stufen (±5/15/25 Prozentpunkte, per Äquivalenztest belegt). Bifrost nutzt feinere Stufen (±2/10/20) und misst gegen den tatsächlich verstrichenen Anteil des Reset-Fensters. Sonst ergäbe das Spec-Szenario (25 % Verbrauch nach 22,6 % des Monats) keine positive Pace.
*Alternative:* Logik in `bifrost.py` duplizieren. Verworfen, weil Pace und Status bei zwei Kostenprovidern auseinanderlaufen würden.

### D3 Maßgebliches Budget = geringster Rest
`effective_limit = max_limit + (override_amount or 0)`, `rest = effective_limit - current_usage`; das Budget mit dem kleinsten `rest` gewinnt. Die Notiz zeigt dann zusätzlich `source_name`, sofern Bifrost sie liefert und mehr als ein Budget existiert.
*Alternative:* Summe aller Budgets. Verworfen, weil Bifrost jedes Budget einzeln hart durchsetzt und das knappste zuerst greift.

### D4 Familien per Teilstring, Anteile aus `per_model_usage`
Die Familie ergibt sich aus dem kleingeschriebenen Modellnamen: enthält er `opus`, `sonnet` oder `haiku`, dann diese Familie, sonst `Andere`. Damit werden Präfixe wie `eu.anthropic.` und Versionen ignoriert. Kosten je Familie werden summiert, absteigend sortiert, Familien unter 1 % fallen in `Rest`, und ab der vierten Familie wird zusammengefasst. Die Prozentwerte werden auf ganze Zahlen gerundet und auf 100 normiert (Rundungsdifferenz auf den größten Eintrag). `m1` bleibt `current_usage`, weil die Summe von `per_model_usage` davon abweicht (live: rund 3.790 $ gegen 3.769 $).
*Alternative:* Gruppierung nach Version (`Opus5.5`). Vom Nutzer verworfen.

### D5 Key-Ablage und Auto-Detect
- Variable `BIFROST_VIRTUAL_KEY` in `secrets.env`. Der Config-Block trägt `api_key_env = "BIFROST_VIRTUAL_KEY"`, `base_url`, `poll_seconds = 120`, `display_name = "LLM Gateway"`.
- Die Erkennung liest `ANTHROPIC_AUTH_TOKEN` und `ANTHROPIC_BASE_URL` aus der Umgebung, sonst aus dem `env`-Block von `~/.claude/settings.json`. Nur ein Token mit dem Präfix `sk-bf-` zählt.
- Damit der Key nicht durch die Companion-UI wandert, bekommt `provider-save` für Bifrost die Option `{"source": "claude-settings"}`: Der Daemon kopiert den erkannten Wert selbst nach `secrets.env`. Manuelle Eingabe läuft wie bei Langdock über `secret-write`.
- Die Notiz ist `virtual_key_name` ohne `user-`-Präfix und ohne Domain (`sascha.krinke`). Ein gesetztes `display_note` in der Config hat Vorrang.

*Alternative:* Key bei jedem Poll aus `~/.claude/settings.json` lesen. Verworfen: Der Daemon läuft als Dienst, Claude-Code-Konfigurationen können wechseln, und eine eigene Ablage macht den Zustand nachvollziehbar.

### D6 Segmentbalken als eigenes LVGL-Element, Graustufenrampe
`cost_budget` ersetzt das `lv_bar` durch einen Track-Container (Hintergrund `COL_BAR_BG`, gleiche Position und Größe) mit bis zu vier Kind-Rechtecken. Die Gesamtbreite der Füllung ist `min(m1/m2, 1) × Trackbreite`, aufgeteilt nach `sh`. Ohne `sh` gibt es genau ein Segment in `pct_color` (heutiges Verhalten). Die Legende ist eine Zeile mit Punkt, Kürzel und Prozent je Eintrag, unter dem Balken. Die Prozentangabe „N % Budget" bekommt `pct_color`, damit die Warnung erhalten bleibt, wenn der Balken nicht mehr nach Status gefärbt ist. Die Zeilenpositionen kommen aus `compute_layout()` (groß/kompakt). Endgültige Pixelwerte werden per `./screenshot.sh` auf beiden Displaygrößen festgelegt.

Segmentpalette: eine Helligkeitsrampe aus `THEME_TEXT` (warmes Weiß) in abgestuften Deckkräften bzw. Grautönen, absteigend nach Anteil, sowie `THEME_DIM` und ein dunkles Grau für `Rest`.
*Alternativen:*
- `DONUT_SLICE_COLORS` wiederverwenden: Verworfen, sie enthalten Grün und Bernstein, die im Balken als Status gelesen würden.
- Akzent-basierte Rampe: Verworfen, weil im Standard-Build `THEME_ACCENT` gleich `THEME_AMBER` (`0xd97757`) ist und das stärkste Segment damit wie eine Warnung aussähe.

### D7 Sparkline-Strecke ersatzlos entfernen
`spark[]`, `spark_set`, das Parsing von `sp`, das `lv_chart` in `tokens_abs`, die Zeile „vs. gestern", `extra["spark"]` in `to_payload()` und `correlate_backend_quota` entfallen. Der `tokens_abs`-Screen rückt den Donut nach oben. Das Feld `m3` bleibt im Protokoll, weil `cost_budget` und `tpm_rpm` es nutzen.

### D8 Kopfzeile des Budget-Screens entzerren (nachträglich aufgenommen)
Bei fünfstelligen Budgets überlagert das Pace-Dreieck den Text „von $15000", und überzogene Beträge (`$16500.00`) stoßen an „von". Das Problem bestand schon vorher, tritt beim Gateway-Budget aber immer auf. Die Pace wandert in die untere Zeile neben „N % Budget". Beträge ab 10.000 werden ohne Nachkommastellen und mit Tausenderpunkt angezeigt, darunter weiter mit zwei Nachkommastellen. Vom Nutzer am 2026-10-07 freigegeben.
*Alternative:* kleinere Schrift für große Beträge. Verworfen, weil der Hauptwert aus Schreibtischdistanz lesbar bleiben soll.

### D9 BLE-Empfang als Warteschlange (nachträglich aufgenommen)
Beim Ende-zu-Ende-Test kam der Bifrost-Payload nie auf dem Gerät an, obwohl der Daemon ihn in jedem Zyklus sendete. Ursache: `ble.cpp` hält genau einen Empfangspuffer, den jedes `onWrite` überschreibt. Die Hauptschleife verarbeitet pro Durchlauf eine Nachricht. Dauert ein Durchlauf länger als der Sendeabstand von 80 ms, überschreibt der nächste Payload, meist der Zyklusende-Marker, den vorherigen. Danach verwirft die Firmware am Zyklusende alle nicht empfangenen Provider. Lösung: ein Ringpuffer mit 8 Einträgen zu je 512 Byte, gefüllt im NimBLE-Callback und in der Schleife vollständig geleert. Läuft er über, wird der älteste Eintrag verworfen und seriell geloggt. Vom Nutzer am 2026-10-07 freigegeben.
*Alternative:* Sendeabstand im Daemon auf ca. 250 ms erhöhen. Verworfen: verschiebt die Grenze nur und verlängert jeden Zyklus.

## Risks / Trade-offs

- [Bifrost ändert das Format von `quota` bei einem Update] → Der Adapter liest Felder defensiv (`.get`, Typprüfung) und fällt bei Strukturfehlern auf `stale` zurück; die Doku nennt die geprüfte Version 2.2.5.
- [`per_model_usage` bezieht sich auf ein anderes Zeitfenster als `current_usage`] → Es dient nur als Anteil, nie als Betrag; die Abweichung ist in der Feature-Doku festgehalten.
- [Der Balken trägt keine Statusfarbe mehr, sobald Anteile vorliegen] → Prozentangabe in `pct_color`, Status `near-limit`/`over-budget` im Payload; per Screenshot bei 92 % geprüft.
- [Ein Virtual Key in `secrets.env` ist ein Inferenz-Credential mit 15.000 $ Monatsbudget] → Datei mit Modus 600 (bestehendes Verhalten von `secrets.py`), keine Ausgabe in Logs, Wizard zeigt höchstens maskiert.
- [Nutzer mit altem Daemon und neuer Firmware oder umgekehrt] → Beide Richtungen sind lesend kompatibel: Alte Firmware ignoriert `sh` bei `cost_budget` (einfarbiger Balken), neue Firmware ignoriert `sp`.
- [Wegfall von OpenCode für eventuelle externe Nutzer] → Als BREAKING in Proposal, README und PROGRESS vermerkt.

## Migration Plan

1. Daemon und Companion-App mit neuem Adapter ausliefern (App-Update enthält Daemon und Firmware-Binaries).
2. Firmware über den Flash-Wizard bzw. `pio run -t upload` neu flashen; die Reihenfolge ist egal (siehe Kompatibilität oben).
3. Nutzer mit `opencode` in der `config.toml` sehen eine Log-Zeile; der Block kann per `clawdmeter config` oder von Hand entfernt werden.
4. Rückweg: vorherigen App-Release bzw. Firmware-Stand flashen. Es gibt keine Datenmigration.
