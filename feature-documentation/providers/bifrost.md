# Provider: Bifrost

Adapter: [`daemon/clawdmeter_daemon/providers/bifrost.py`](../../daemon/clawdmeter_daemon/providers/bifrost.py).
Registrierungs-ID: `bifrost`. Default-Slot: `bifrost`. Kind: `cost_budget`.

## Worum es geht

Das WRS-LLM-Gateway (Bifrost) verwaltet Virtual Keys mit individuellen monatlichen Budgets. Der Clawdmeter-Adapter fragt das Gateway über einen Self-Service-Endpunkt ab — mit dem eigenen Virtual Key des Nutzers, kein Admin-Zugang nötig — und zeigt Verbrauch gegen Budget sowie die Verteilung über Modellfamilien (Opus/Sonnet/Haiku/Andere).

**Geprüfte Bifrost-Version:** v2.2.5 (live geprüft am 2026-10-07).

## API-Basis & Auth

- **Base-URL:** `https://llm-gw.wineretailsystems.cloud` (default; Daemon liest aus `ANTHROPIC_BASE_URL` wenn gesetzt).
- **Endpunkt:** `GET <base_url>/api/governance/virtual-keys/quota`
- **Auth:** `Authorization: Bearer <virtual-key>` (Virtual Key mit Präfix `sk-bf-…`).
- **Charakteristikum:** Self-Service — der Virtual Key authentifiziert nur sich selbst, nicht andere User oder den gesamten Gateway.

**Wichtig:** Der Daemon fragt den Endpunkt mit dem Virtual Key des Nutzers ab. Das ist eine Anwendungs-Credential mit etwa 15.000 € monatlichem Budget und sollte wie ein API-Key behandelt werden. Der `secrets.env`-Speicher nutzt Dateimodus 600, und der Daemon gibt den Key-Wert niemals in Logs aus.

## Request- und Response-Schema

**Request:**

```
GET /api/governance/virtual-keys/quota
Authorization: Bearer sk-bf-…
```

**Response (HTTP 200):**

```json
{
  "virtual_key_name": "user-sascha.krinke@jacques.de",
  "budgets": [
    {
      "max_limit": 15000.0,
      "current_usage": 3769.16,
      "reset_duration": "1M",
      "last_reset": "2026-10-01T00:00:00Z",
      "override_amount": 500.0,
      "per_model_usage": [
        {"model": "eu.anthropic.claude-opus-5-5", "total_cost": 2450.00},
        {"model": "eu.anthropic.claude-sonnet-5", "total_cost": 1050.00},
        {"model": "eu.anthropic.claude-haiku-4-5", "total_cost": 269.16}
      ],
      "source_name": "Primary Account"
    }
  ],
  "rate_limit": {...}
}
```

Die relevanten Felder sind `virtual_key_name` (für die Display-Notiz), `budgets` (Liste der aktivierten Budgets mit Verbrauch, Limit, Reset-Informationen und per-Modell-Aufschlüsselung) sowie `rate_limit` (siehe Non-Goals unten). Die Struktur ist defensiv gelesen — fehlende oder ungültige Felder führen zu einem `stale`-Status statt eines Crashes.

## Feld-Mapping auf den BLE-Payload

Der Adapter bildet die Gateway-Antwort auf einen `cost_budget`-Snapshot ab:

| Payload-Feld | Gateway-Quelle | Bedeutung |
| --- | --- | --- |
| `k` | — | immer `cost_budget` |
| `cur` | — | immer `USD` |
| `m1` | `current_usage` (maßgebliches Budget) | verbrauchter Betrag in USD |
| `m2` | `max_limit + override_amount` (maßgebliches Budget) | wirksames Budget in USD |
| `r2` | `reset_duration` + `last_reset` | Sekunden bis zum nächsten Reset |
| `pace` | berechnet aus m1, m2, Fensterfortschritt | Burn-Rate-Indikator (-3 bis +3) |
| `status` | berechnet aus m1/m2 | `ok` (<90%), `near-limit` (90-100%), `over-budget` (>100%) |
| `sh` | `per_model_usage` (optionale Familiengruppen) | Anteile pro Modellfamilie (siehe unten) |
| `note` | `virtual_key_name` oder `display_note` aus Config | sichtbar auf dem Screen |

## Budgetwahl — „geringster Rest gewinnt"

Wenn mehrere Budgets im Gateway konfiguriert sind, gewinnt das mit dem kleinsten **Verbleibenden Betrag**:

```
Budget 1: 2000 USD limit, 1800 USD spent → Rest 200
Budget 2:  200 USD limit,  100 USD spent → Rest 100 ← maßgeblich
```

Der maßgebliche Betrag wird als `m1` und `m2` geschickt; sind mehrere Budgets vorhanden und das Gateway liefert `source_name` im gewählten Budget, wird die Notiz mit der Quelle angereichert (z. B. `„Primary Account sascha.krinke"`).

## Reset-Berechnung

`r2` berechnet sich als Sekunden zwischen `now()` und `last_reset + reset_duration`. Die `reset_duration` nutzt Bifrost-Notation:

| Dauer | Beispiel | Bedeutung |
| --- | --- | --- |
| `1M` | Monatsbudget | Nächster Reset am 1. des nächsten Kalendermonats (00:00 UTC) |
| `1Q` | Quartalsbudget | Nächster Reset am 1. des nächsten Kalenderquartals |
| `1d`, `1w` | Tages-/Wochenbudget | `last_reset + Dauer`, ggf. mehrfach weitergezählt, bis der Reset in der Zukunft liegt |

**Beispiel:** Ist `last_reset = 2026-10-01` und `reset_duration = "1M"` und die aktuelle Zeit ist 2026-10-07 12:00 UTC, dann ist der nächste Reset am 2026-11-01 00:00 UTC, also 2.116.800 Sekunden entfernt.

## Modellfamilien und Anteile (`sh`)

Sofern `per_model_usage` mindestens ein Modell mit Kosten > 0 enthält, gruppiert der Adapter die Kosten nach Modellfamilie:

**Familie erkennen:**

| Modellfamilie | Erkennungskriterium |
| --- | --- |
| `Opus` | Modellname (lowercase) enthält `opus` |
| `Sonnet` | Modellname (lowercase) enthält `sonnet` |
| `Haiku` | Modellname (lowercase) enthält `haiku` |
| `Andere` | alles Übrige (z. B. OpenAI, lokale Modelle) |

Regionen- und Versionsmodifizierer (`eu.anthropic.`, `-5-5`, `-4-5`) werden automatisch ignoriert — es zählt der Substring-Match.

**Anteile berechnen:**

1. Kosten pro Familie summieren: `{Opus: 2450, Sonnet: 1050, Haiku: 269}`
2. Prozentanteile berechnen: `Gesamtsumme = 3769 → [Opus: 65%, Sonnet: 28%, Haiku: 7%]`
3. Familien unter 1 % ausfiltern (hier: alle über 1 %)
4. Maximal 3 Familien + 1 `Rest`-Eintrag, absteigend nach Anteil
5. Prozentanteile auf ganze Zahlen runden und auf 100 normieren (Rundungsfehler auf die größte Familie verteilen)

**Beispiel:**

```python
per_model_usage = [
  {"model": "claude-opus-5-5", "total_cost": 100},    # Opus
  {"model": "claude-opus-5", "total_cost": 50},       # Opus
  {"model": "gpt-4", "total_cost": 30},               # Andere
  {"model": "claude-sonnet-5", "total_cost": 20},     # Sonnet
]
→ Kosten: Opus=150, Andere=30, Sonnet=20, gesamt=200
→ Prozent: Opus=75%, Andere=15%, Sonnet=10%
→ sh = [{"slug": "Opus", "pct": 75}, {"slug": "Andere", "pct": 15}, {"slug": "Sonnet", "pct": 10}]
```

**Fehlerfall:** Falls `per_model_usage` fehlt oder leer ist, sendet der Adapter `sh` gar nicht — der Screen zeigt dann einen einfarbigen Budget-Balken ohne Legende.

**Wichtiger Hinweis:** Die Summe von `per_model_usage` kann von `current_usage` abweichen (Rounding, Aggregations-Zeitpunkte im Gateway). Der Adapter nutzt nur die `per_model_usage`-Kosten für die Anteile, bleibt aber bei `current_usage` als `m1` — damit bleibt der gezeigte Betrag korrekt, die Segmentierung ist nur eine Visualisierungshilfe.

## Pace und Status

**Pace** ist ein Indikator der Burn-Rate, berechnet als `(verbraucht % / Budgetfenster) - (verstrichene Zeit % / Budgetfenster)`. Die Schwellen sind feiner als bei anderen Providern:

| Pace | Bedingung | Bedeutung |
| --- | --- | --- |
| -3 | `delta ≤ -20 PP` | deutlich unter Soll |
| -2 | `-20 < delta ≤ -10` | spürbar unter Soll |
| -1 | `-10 < delta ≤ -2` | leicht unter Soll |
| 0 | `-2 < delta < +2` | on-track |
| +1 | `+2 ≤ delta < +10` | leicht über Soll |
| +2 | `+10 ≤ delta < +20` | spürbar über Soll |
| +3 | `delta ≥ +20` | deutlich über Soll |

**Beispiel:** Es ist der 7. Oktober, also ~22,6 % des Monats verstri­chen. Der User hat 25 % seines Budgets ausgegeben → `delta = 25 - 22.6 = +2.4`, also `pace = +1`.

**Status:**

- `ok` wenn `m1 / m2 < 0.90` (unter 90 % Auslastung)
- `near-limit` wenn `0.90 ≤ m1 / m2 < 1.0` (90–99 %)
- `over-budget` wenn `m1 / m2 ≥ 1.0` (100 % oder mehr)

## Fehlerverhalten

| Situation | Daemon-Reaktion |
| --- | --- |
| `BIFROST_VIRTUAL_KEY` nicht gesetzt | Skip-Log mit Variablennamen, `None`-Snapshot (Slot zeigt letzten Wert) |
| HTTP 401/403 (ungültiger/abgelaufener Key) | `stale`-Status, `ok=false`, Log mit Statuscode + Variablennamen (nicht den Key) |
| HTTP 5xx oder andere Fehler | `stale`-Status, `ok=false` |
| Timeout (>15 Sekunden) | `stale`-Status, `ok=false` |
| Struktur-Fehler (JSON invalid, fehlende Felder) | `stale`-Status, `ok=false` — defensives Parsing |

**Stale-Snapshots:** Wenn der Adapter fehlschlägt, sendet er den letzten bekannten Stand mit `ok=false`, damit das Gerät den Wert nicht auf Null zurückfährt. Der Reset-Countdown (`r2`) wird mit der aktuellen Zeit nachgerechnet, bleibt also korrekt.

## Einrichtung

### Setup-Wizard & CLI

`clawdmeter-daemon setup` bietet Bifrost an und fragt:

1. **Aktivieren?** Default = aktueller Block-Status
2. **Gateway-URL** (Auto-Vorschlag aus Umgebung/Claude-Konfiguration oder Default `https://llm-gw.wineretailsystems.cloud`)
3. **Virtual-Key-Eingabe** — wird maskiert angezeigt (z. B. `sk-bf-…abc`), nie in Klartext

Der Wizard prüft vorher auf einen `sk-bf-`-Token in:
- Umgebungsvariable `ANTHROPIC_AUTH_TOKEN`
- `env`-Block der `~/.claude/settings.json` (Claude-Code-Konfiguration)

Falls erkannt, zeigt der Wizard „Virtual Key aus Claude-Code-Konfiguration erkannt" und schlägt vor, diesen zu übernehmen.

### Speicherort

Der Virtual Key wird **nicht** in `config.toml` geschrieben, sondern in `~/.config/clawdmeter/secrets.env` (Modus 600). Die TOML enthält nur:

```toml
[[provider]]
id = "bifrost"
enabled = true
slot_id = "bifrost"
display_name = "LLM Gateway"
display_note = ""
api_key_env = "BIFROST_VIRTUAL_KEY"
poll_seconds = 120
```

Der Daemon liest den Key zur Laufzeit aus `BIFROST_VIRTUAL_KEY` (oder aus einer Shell-exportierten Variablen mit demselben Namen, falls vorhanden).

### Companion-App

`SetupWizard.tsx` bietet einen Bifrost-Schritt mit:
- Auto-Detect-Bericht (Quelle, maskierter Key)
- „Erkannten Key übernehmen" — speichert per IPC-Befehl `provider-save` mit `source: "claude-settings"`, der Daemon kopiert den Key selbst nach `secrets.env`
- Manuelle Eingabe via `secret-write` (IPC-Befehl für Companion-App)

### Diagnostik

`clawdmeter doctor` prüft für Bifrost:

- Ist `BIFROST_VIRTUAL_KEY` gesetzt?
- Ist der Gateway erreichbar? (Test-Request mit dem Key)
- HTTP-Statuscode und Fehlertyp bei Problemen

## Grenzen und Non-Goals

- **Rate-Limits:** Der Adapter ignoriert das `rate_limit`-Feld aus der Gateway-Antwort. Rate-Limits werden vom Gateway durchgesetzt; das Gerät zeigt sie nicht an.
- **Admin-API:** Der Adapter nutzt **nicht** die Admin-API des Gateways (z. B. zur Verwaltung anderer User oder Global-Limits). Nur der Self-Service-Endpunkt mit dem Virtual Key.
- **Historische Daten:** Das Gateway speichert keine Verbrauchshistorie im Quota-Endpunkt. Der Adapter zeigt nur den aktuellen Stand, keine Trendkurve.
- **Ein Virtual Key pro Block:** Getestet ist ein `bifrost`-Block pro `config.toml`.

## Quellen

- [Bifrost API: Get Virtual Key Quota](https://docs.getbifrost.ai/api-reference/governance/get-virtual-key-quota)
- [Bifrost: Budget and Limits](https://docs.getbifrost.ai/features/governance/budget-and-limits)
- Geprüfte Version: v2.2.5 (2026-10-07)
- Live-Test gegen Gateway-Instanz durchgeführt
