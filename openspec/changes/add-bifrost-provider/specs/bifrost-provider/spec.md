# Spec Delta

## Purpose

Zeigt Nutzern des WRS-LLM-Gateways (Bifrost) ihren Verbrauch gegen das Budget ihres Virtual Keys auf dem Clawdmeter, abgefragt ausschließlich mit dem eigenen Key und ohne Admin-Zugang.

## ADDED Requirements

### Requirement: Kontingentabfrage mit dem eigenen Virtual Key
Der Daemon SHALL das Kontingent über `GET <Gateway-URL>/api/governance/virtual-keys/quota` abfragen und sich dabei ausschließlich mit dem Virtual Key des Nutzers als Bearer-Token authentifizieren. Er MUST NOT Admin-Zugangsdaten des Gateways verwenden oder verlangen.

#### Scenario: Erfolgreiche Abfrage
- **WHEN** der Provider `bifrost` aktiviert ist, ein Virtual Key hinterlegt ist und das Gateway mit HTTP 200 antwortet
- **THEN** sendet der Daemon im nächsten Zyklus einen Payload mit `k = cost_budget`, `cur = USD` und `ok = true` für den Bifrost-Slot

#### Scenario: Kein Key hinterlegt
- **WHEN** der Provider aktiviert ist, aber weder Umgebung noch `secrets.env` einen Virtual Key enthalten
- **THEN** loggt der Daemon den fehlenden Variablennamen (nicht den Wert) und sendet für diesen Provider keinen Screen

### Requirement: Abbildung von Verbrauch, Limit und Reset
Der Payload SHALL als `m1` den Verbrauch (`current_usage`) und als `m2` das wirksame Limit (`max_limit` plus gegebenenfalls `override_amount`) des maßgeblichen Budgets in USD tragen. `r2` SHALL die Sekunden bis zum nächsten Reset enthalten, berechnet als `last_reset` plus `reset_duration`, wobei `1M` als Kalendermonat und `1Q` als Kalenderquartal gilt. Bei mehreren Budgets SHALL das Budget mit dem geringsten verbleibenden Betrag maßgeblich sein.

#### Scenario: Monatsbudget
- **WHEN** das Gateway ein Budget mit `max_limit = 15000`, `current_usage = 3769.16`, `reset_duration = "1M"` und `last_reset = 2026-10-01T00:00:00Z` liefert und es 2026-10-07T12:00:00Z ist
- **THEN** enthält der Payload `m1 = 3769.16`, `m2 = 15000` und `r2 = 2116800` (bis 2026-11-01T00:00:00Z)

#### Scenario: Budget-Override
- **WHEN** ein Budget `max_limit = 2000` und `override_amount = 500` trägt
- **THEN** ist `m2 = 2500`

#### Scenario: Mehrere Budgets
- **WHEN** zwei Budgets vorliegen, eines mit 1800 von 2000 USD und eines mit 100 von 200 USD verbraucht
- **THEN** ist das erste Budget (Rest 200 USD) nicht maßgeblich, sondern das zweite (Rest 100 USD), also `m1 = 100`, `m2 = 200`

#### Scenario: Kein Budget gesetzt
- **WHEN** die Antwort keine Budgets enthält
- **THEN** ist `m2 = 0`, sodass das Gerät „Kein Budget gesetzt" anzeigt, und `m1` bleibt 0

### Requirement: Pace und Status
Der Payload SHALL eine Pace im Bereich −3 bis +3 tragen, die den Verbrauchsanteil am Limit mit dem verstrichenen Anteil des aktuellen Reset-Fensters vergleicht. Der Status SHALL `ok` unter 90 % Auslastung, `near-limit` ab 90 % und `over-budget` ab 100 % sein.

#### Scenario: Leicht vorauslaufender Verbrauch
- **WHEN** 25 % des Budgets nach 22,6 % des Monats verbraucht sind
- **THEN** ist die Pace positiv und der Status `ok`

#### Scenario: Budget erschöpft
- **WHEN** `current_usage` das wirksame Limit erreicht oder überschreitet
- **THEN** ist der Status `over-budget`

### Requirement: Anteile nach Modellfamilie
Der Payload SHALL im Feld `sh` die Kostenanteile des maßgeblichen Budgets nach Modellfamilie tragen, abgeleitet aus `per_model_usage`. Familien sind `Opus`, `Sonnet` und `Haiku` anhand des Modellnamens; alle übrigen Modelle zählen als `Andere`. Es SHALL höchstens vier Einträge geben: die drei kostenstärksten Familien und `Rest` für alles Übrige. Familien unter 1 % SHALL in `Rest` aufgehen. Die Anteile SHALL sich auf die Summe von `per_model_usage` beziehen; `m1` bleibt `current_usage`.

#### Scenario: Gruppierung über Versionen und Regionen
- **WHEN** `per_model_usage` die Modelle `eu.anthropic.claude-opus-5`, `eu.anthropic.claude-opus-5-5` und `eu.anthropic.claude-sonnet-5` enthält
- **THEN** werden beide Opus-Modelle zu einem Eintrag `Opus` zusammengefasst und Sonnet bildet einen eigenen Eintrag

#### Scenario: Kleinstanteile
- **WHEN** Haiku 0,2 % und GPT-Modelle 0,01 % der Kosten ausmachen
- **THEN** erscheinen beide nicht als eigene Einträge, sondern sind in `Rest` enthalten

#### Scenario: Keine Modelldaten
- **WHEN** `per_model_usage` fehlt oder alle Kosten 0 sind
- **THEN** enthält der Payload kein Feld `sh`

### Requirement: Fehlerverhalten
Bei Netzwerkfehlern, Zeitüberschreitung oder HTTP-Fehlern SHALL der Daemon den letzten bekannten Stand mit `st = stale` und `ok = false` senden. Fehlermeldungen und Logs MUST NOT den Virtual Key enthalten.

#### Scenario: Ungültiger oder abgelaufener Key
- **WHEN** das Gateway mit HTTP 401 oder 403 antwortet
- **THEN** sendet der Daemon einen Payload mit `st = stale`, `ok = false` und loggt Statuscode und Variablennamen, nicht den Key

#### Scenario: Gateway nicht erreichbar
- **WHEN** die Abfrage nach dem Timeout abbricht
- **THEN** zeigt das Gerät weiter die letzten Werte als veraltet, und der nächste Versuch erfolgt nach dem regulären Poll-Intervall

### Requirement: Einrichtung und lokale Key-Ablage
Setup-Wizard und Companion-App SHALL den Provider `bifrost` anbieten. Ist in der Claude-Code-Konfiguration oder Umgebung ein `ANTHROPIC_AUTH_TOKEN` mit dem Präfix `sk-bf-` vorhanden, SHALL er als Vorschlag erkannt werden; die Gateway-URL SHALL aus `ANTHROPIC_BASE_URL` ohne Pfad abgeleitet werden und sonst `https://llm-gw.wineretailsystems.cloud` sein. Der Key SHALL nur in `secrets.env` gespeichert werden, nie in `config.toml`, und MUST NOT im Klartext in Ausgaben der Einrichtung erscheinen.

#### Scenario: Auto-Detect
- **WHEN** `~/.claude/settings.json` einen `sk-bf-`-Token und eine Gateway-Base-URL enthält
- **THEN** meldet die Erkennung den Provider als gefunden, nennt die Quelle und zeigt den Key höchstens maskiert

#### Scenario: Speichern aus der Companion-App
- **WHEN** der Nutzer im Setup-Wizard der App einen Key eingibt und speichert
- **THEN** steht der Key in `secrets.env`, `config.toml` enthält einen aktiven `bifrost`-Block mit Verweis auf die Variable, und der Daemon lädt die Konfiguration neu

### Requirement: OpenCode wird nicht mehr unterstützt
Der Daemon SHALL keinen Provider `opencode` mehr kennen. Setup-Wizard und Companion-App MUST NOT ihn anbieten.

#### Scenario: Alte Konfiguration
- **WHEN** `config.toml` noch einen aktiven Block mit `id = "opencode"` enthält
- **THEN** loggt der Daemon einen unbekannten Provider und betreibt alle übrigen Provider unverändert weiter
