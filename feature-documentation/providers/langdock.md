# Provider: Langdock

Adapter: [`daemon/clawdmeter_daemon/providers/langdock.py`](../../daemon/clawdmeter_daemon/providers/langdock.py).
Registrierungs-ID: `langdock`. Default-Slot: `langdock`. Kind: dynamisch — `cost_budget` für BYOK/Hybrid, `tokens_abs` (Aktivität + Donut-Breakdown) für pure-managed.

> **Wire-Format-Hinweis (2026-05-28):** Langdocks Validator akzeptiert ausschließlich ISO-8601-Datums mit `Z`-Suffix; `+00:00` wird mit HTTP 400 abgelehnt. Python's `datetime.isoformat()` produziert defaultmäßig `+00:00`, daher emittieren wir explizit `%Y-%m-%dT%H:%M:%S.000Z`. Vor dem Fix lief der Adapter still ins Leere und zeigte permanent 0,00 €.

## Worum es geht

Langdock liefert **keinen** Realtime-Quota-Endpoint. Die einzige offizielle Quelle ist die **Usage-Export-API**: man POSTet ein Datums-Intervall an `/export/users`, bekommt einen Signed-URL zurück und holt sich dahinter ein CSV ab. Polling-Default: 10 Minuten (Export-Latenz allein ~30 s, zwei HTTPS-Roundtrips pro Zyklus).

## API-Basis & Auth

- **Base-URL**: `https://api.langdock.com` (Cloud) bzw. `https://<dein-host>/api/public` (Dedicated)
- **Auth**: `Authorization: Bearer <LANGDOCK_API_KEY>`. Workspace-scoped (Admin-Rolle nötig, erstellt unter `Settings → API Keys` von `app.langdock.com`).
- **Secret-Quelle**: Env-Var, Name via `api_key_env` konfigurierbar (Default `LANGDOCK_API_KEY`). Bewusst **nicht** im TOML.

## Endpoints

Wir benutzen ausschließlich `POST /export/users`. Begründung: deckt mit einem Call alle drei Workspace-Modi ab (siehe unten). Das alternative `/export/models` würde zwar pro-Modell-Aufschlüsselung erlauben, hat aber für Nicht-BYOK-Setups keinen verwertbaren Inhalt.

Andere `/export/*`-Endpoints sind im Code nicht referenziert, könnten aber später hinzugenommen werden:

| Endpoint              | Inhalt (laut Doku)                                  |
| --------------------- | --------------------------------------------------- |
| `/export/users`       | Pro User: Messages, Activity, Tokens, Cost (BYOK)   |
| `/export/models`      | Pro Modell × User × Tag: Requests, Tokens, Cost (BYOK) |
| `/export/agents`      | Pro Agent: Messages, Active Users, Trends           |
| `/export/projects`    | Pro Projekt: Activity, beteiligte User, Verbrauch   |
| `/export/workflows`   | Pro Workflow: Runs, Tokens                          |
| `/export/assistants`  | (Legacy) Assistant-Stats                            |

Limits laut [Usage-Export-Intro](https://docs.langdock.com/api-endpoints/usage-export/intro-to-usage-export-api): **500 RPM / 60.000 TPM workspace-weit**, **max 1.000.000 Zeilen** pro CSV (HTTP 400 wenn überschritten — Zeitraum verkürzen).

## Request- und Response-Schema

**Request** (identisch für alle `/export/*`-Endpoints, [verifiziert gegen die Doku am 2026-05-24](https://docs.langdock.com/api-endpoints/usage-export/export-users)):

```json
POST /export/users
Authorization: Bearer <LANGDOCK_API_KEY>
Content-Type: application/json

{
  "from": { "date": "2026-05-01T00:00:00.000Z", "timezone": "UTC" },
  "to":   { "date": "2026-05-24T23:45:12.000Z", "timezone": "UTC" }
}
```

**Response** (200):

```json
{
  "success": true,
  "data": {
    "filePath":    "users-usage/<workspace-id>/users-usage-2026-05-01-2026-05-24-abc12345.csv",
    "downloadUrl": "https://storage.example.com/signed-url",
    "dataType":    "users",
    "recordCount": 1250,
    "dateRange":   { "from": "...", "to": "..." }
  }
}
```

Der Adapter extrahiert die URL über [`_extract_download_url`](../../daemon/clawdmeter_daemon/providers/langdock.py) — primär aus `payload.data.downloadUrl`, mit defensivem Fallback auf eine flache `downloadUrl`-Form, falls Langdock das Wrapper-Schema mal ändert.

## Workspace-Modi und Kind-Mapping

Langdock erlaubt inzwischen **Standard-Modelle (managed) und BYOK in einem Workspace gemischt** ([Doku](https://docs.langdock.com/settings/models/adding-models)). Der Adapter unterscheidet drei Fälle anhand der gelieferten CSV-Zeilen:

| Modus | Erkennung | Emittiertes Kind | m1 | m2 | Donut-Shares | note |
| --- | --- | --- | --- | --- | --- | --- |
| **BYOK** | alle gefilterten Zeilen haben Pricing/Cost-Spalten | `cost_budget` | Spend in `currency` | `monthly_budget_eur` | — | `"BYOK"` |
| **Hybrid** | manche Zeilen mit Pricing, manche ohne | `cost_budget` | Spend (nur BYOK-Anteil) | `monthly_budget_eur` | — | `"hybrid"` |
| **Pure managed** | keine einzige Zeile mit Pricing | `tokens_abs` | `messages_total + action_messages` | 0 | Workflows / Chat / Projekt / Assistant | `"Aktivität"` |

Der Mode steckt in `Snapshot.extra["mode"]` (nur Logging-relevant, geht nicht über BLE).

Im Managed-Modus liefert Langdock für jacques.de-typische Workspaces folgende Aktivitätssäulen pro User pro Monat:

- `messages_total` = `messages_chat` + `messages_assistants` + `messages_projects`
- `action_messages` = Workflow-/MCP-Tool-Aufrufe (z. B. „Jira_Search for issues": 627). Disjunkt von `messages_total`, daher additiv.

Wir summieren beide zu einer **Gesamtaktivität** und schicken die Aufschlüsselung als BLE-`shares`-Liste mit (LVGL-Donut + Legende auf dem Slot, siehe [`ui.cpp:646`](../../firmware/src/ui.cpp#L646)).

Pace wird im `cost_budget`-Modus aus `(spent / budget)` vs. `(Tag des Monats / Tage im Monat)` berechnet — gleiche 7-Stufen-Logik wie Anthropic/Codex. Im `tokens_abs`-Modus bleibt Pace `None`.

## CSV-Parser

Die Langdock-Doku enumeriert keine CSV-Spaltennamen. Die hier dokumentierten Namen stammen aus einem Live-Diagnose-Lauf gegen jacques.de am 2026-05-28 (Tool: [`tools/diag_langdock.py`](../../tools/diag_langdock.py)). Der Parser matched case-insensitiv über eine Aliasliste, damit forward-kompatibel bleibt, falls Langdock umbenennt.

Aktuell gepflegte Kandidaten ([providers/langdock.py](../../daemon/clawdmeter_daemon/providers/langdock.py)):

| Logischer Wert | Akzeptierte Spaltennamen | Quelle (Endpoint) |
| --- | --- | --- |
| Messages-Total | `messages_total` *(real)*, `message_count`, `messages`, … | `/export/users` |
| Messages-Chat | `messages_chat` | `/export/users` |
| Messages-Assistants | `messages_assistants` | `/export/users` |
| Messages-Projects | `messages_projects` | `/export/users` |
| Action-Messages (Workflows) | `action_messages`, `messages_actions` | `/export/users` |
| Email (für User-Filter) | `email`, `user_email` | `/export/users` |
| Tokens-In | `tokens_in`, `input_tokens`, `prompt_tokens`, `tokens_input` | BYOK-Workspace (unverifiziert) |
| Tokens-Out | `tokens_out`, `output_tokens`, `completion_tokens`, `tokens_output` | BYOK-Workspace (unverifiziert) |
| Input/Output-Pricing (USD/1M) | siehe Code | BYOK-Workspace (unverifiziert) |
| Cost direkt (USD/EUR) | `cost_usd`, `cost_eur`, … | BYOK-Workspace (unverifiziert) |

Beim ersten erfolgreichen Poll loggt der Adapter über `_log_unknown_columns_once` ausschließlich Spalten mit Pricing-/Token-/Cost-/Spend-/Billed-Hinweisen, die wir nicht kennen — Rank- und Aggregat-Spalten (`*_rank`, `*_to_messages`, `model_to_*`) werden als bekannte Metadaten ignoriert.

### Reale `/export/users`-Spalten (24 Stück, Live-Beobachtung)

```
period_start, period_end, org_id, user_id, name, email, role, joined_at,
messages_total, messages_total_rank,
messages_chat, messages_chat_rank,
messages_assistants, messages_assistants_rank, assistants_messaged, assistants_to_messages,
messages_projects, messages_projects_rank, projects_messaged, projects_to_messages,
model_to_messages_total,
action_messages, action_messaged, action_to_messages
```

`action_to_messages` ist ein JSON-Dict mit der Verteilung pro Workflow/Tool (z. B. `{"Jira_Search for issues":627,"Confluence_Search":6}`). Aktuell wird nur die Summe `action_messages` ausgewertet — Detail-Aufschlüsselung wäre eine künftige Erweiterung.

Kostenrechnung pro Zeile:

1. Wenn beide Pricing-Spalten gesetzt: `(tokens_in/1e6) × in_price + (tokens_out/1e6) × out_price` (USD)
2. Sonst: erstes nicht-leeres `cost_usd` direkt nutzen
3. Sonst: erstes nicht-leeres `cost_eur` → durch `usd_to_eur` teilen, um in USD zu konvertieren, dann einheitlich am Ende einmal × `usd_to_eur` zurück nach EUR. Das vermeidet, EUR und USD im Akkumulator zu mischen.

`spent_eur = spent_usd × usd_to_eur`. Live-FX wurde bewusst weggelassen (statischer Kurs).

## Config-Block

```toml
[[provider]]
id = "langdock"
enabled = false
poll_seconds = 600
slot_id = "langdock"
display_name = "Langdock"
display_note = ""              # leer = Modus-Label (BYOK/hybrid/managed) wird automatisch eingesetzt
api_key_env = "LANGDOCK_API_KEY"
monthly_budget_eur = 0         # 0 = ohne Budget; ansonsten manueller Wert aus app.langdock.com/settings/workspace/usage
currency = "EUR"
usd_to_eur = 0.92              # statischer Kurs für USD-Pricing → EUR-Spend
# user_email = "you@example.com"  # optional — filtert /export/users auf eine Person.
                                  # Ohne diesen Wert summiert der Adapter alle Org-Mitglieder.
```

`monthly_budget_eur` ist **nicht** per API abrufbar — Langdock bietet keinen Endpoint dafür. Der User trägt seinen workspace-weiten Extra-Usage-Limit (Default 1.000 EUR/Monat) manuell ein.

## Setup-Wizard

`clawdmeter-daemon setup` ruft `wizard_langdock` zwischen Codex und OpenCode auf. Fragt:

- **Aktivieren?** Default = bestehender Block.
- **Monatsbudget in EUR** (0 = ohne).
- **Display-Untertitel** (z. B. `BYOK`/`managed` — bei leerem Wert wird im Snapshot automatisch der erkannte Modus eingesetzt).

Vorher: schneller Env-Var-Check für `LANGDOCK_API_KEY` (warnt, wenn nicht gesetzt).

## Fehler-Verhalten

| Situation | Adapter-Reaktion |
| --- | --- |
| `LANGDOCK_API_KEY` fehlt | Skip-Log, `None`-Snapshot (Slot behält letzten Wert) |
| POST /export/users → HTTP ≥ 400 | `_stale_snapshot` mit `m1 = _last_spent`, `status="stale"`, `ok=False` |
| Response ohne `downloadUrl` | gleicher Stale-Pfad, Log enthält die Top-Level-Keys des Payloads für Debug |
| Signed-URL liefert HTTP ≥ 400 | gleicher Stale-Pfad |
| JSON/CSV malformed | gleicher Stale-Pfad |
| Empty CSV (recordCount=0) | normale Emittierung mit `m1=0`, `mode="empty"`, `note="managed"` |

Stale-Snapshots werden trotzdem mitgesendet — der ESP zeigt den letzten bekannten Wert, kein leerer Screen.

## Offene Punkte

- **BYOK-Code-Pfad gegen echten BYOK-Workspace prüfen.** Die Pricing-Spaltennamen sind weiterhin geraten — auf jacques.de (pure managed) konnten wir sie nicht verifizieren. Sobald ein BYOK-Workspace verfügbar ist, mit `tools/diag_langdock.py` Spaltennamen ablesen und die Aliaslisten ergänzen.
- **Provider-Spalte für Multi-Provider-BYOK** (Anthropic + OpenAI über Langdock): wenn der User später per-Provider-Slots will, kann der Adapter dupliziert werden mit unterschiedlichen `slot_id`s und einer optionalen Filterspalte in `_parse_csv` (`if row.get("provider") != "anthropic": continue`). `/export/models` hat dafür die Spalten `provider`, `raw_model`, `bring_your_keys` — wäre die saubere Quelle.
- **Workflow-Detail-Donut.** `action_to_messages` enthält bereits die Per-Workflow-Verteilung als JSON-Dict. Eine künftige Erweiterung könnte die Top-3-Workflows statt der Chat/Projekt/Assist-Kategorien als Shares schicken.
- **Rate-Limit-Header durchgeschleift?** Langdock proxied OpenAI/Anthropic — ob `x-ratelimit-*`-Header der Backend-Provider auf Chat-Calls durchgereicht werden, ist undokumentiert. Wäre eine elegantere Quelle als CSV-Export, müsste mit `curl -D -` empirisch geprüft werden.

## Diagnose-Tool

`tools/diag_langdock.py` schießt einen Roh-Aufruf gegen alle vier `/export/*`-Endpoints und dumpt Spalten + erste Datenzeilen. Lifecycle: lokal benutzen wenn der Provider 0,00 € zeigt, **nicht** als Daemon-Komponente einsetzen.

```bash
daemon/.venv/bin/python3 tools/diag_langdock.py
```

## Quellen

- [Usage Export API Intro](https://docs.langdock.com/api-endpoints/usage-export/intro-to-usage-export-api)
- [Export Users](https://docs.langdock.com/api-endpoints/usage-export/export-users)
- [Export Models](https://docs.langdock.com/api-endpoints/usage-export/export-models)
- [Adding Models / BYOK + Standard hybrid](https://docs.langdock.com/settings/models/adding-models)
- [Extra Usage / Budgets](https://docs.langdock.com/administration/extra-usage)
- [API Key Best Practices](https://docs.langdock.com/administration/api-key-best-practices)
- [OpenAPI Spec (5589 Zeilen YAML)](https://docs.langdock.com/openapi.yaml)
