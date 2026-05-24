# Provider: OpenAI Codex / ChatGPT

Adapter: [`daemon/clawdmeter_daemon/providers/codex.py`](../../daemon/clawdmeter_daemon/providers/codex.py).
Registrierungs-ID: `codex`. Default-Slot: `codex`. Kind: `pct_window` (identisch zu Anthropic, Firmware-UI muss nichts ändern).

## Was wird abgebildet

Der `codex`-CLI von OpenAI hinterlegt nach `codex login` ein OAuth-Token in `~/.codex/auth.json` (überschreibbar via `CODEX_HOME`). Mit diesem Token wird `GET https://chatgpt.com/backend-api/wham/usage` aufgerufen — derselbe Endpunkt, den die ChatGPT-Web-UI für die Plan-Anzeige nutzt. Die Antwort enthält zwei rollende Fenster (5h-„Session" + 7d-„Weekly") plus Plan-Typ und Credit-Status.

Mapping in unser BLE-Schema:

| BLE-Feld | Quelle |
| --- | --- |
| `k`   | `"pct_window"` |
| `m1`  | `rate_limit.primary_window.used_percent` (nach Normalisierung 5h-Session) |
| `m2`  | `rate_limit.secondary_window.used_percent` (nach Normalisierung 7d-Weekly) |
| `r1`  | `primary_window.reset_at` − jetzt (in Sekunden) |
| `r2`  | `secondary_window.reset_at` − jetzt (in Sekunden) |
| `pace` | −3..+3, abgeleitet aus `(usage − erwartet)` über die 5h-Fensterdauer (`limit_window_seconds`) |
| `regen` | %/min-Drop zwischen zwei aufeinanderfolgenden Polls (rolling) |
| `note` | `display_note` aus Config, sonst hübsch formatierter Plan-Typ (`Plus`, `Pro`, `Team`, …) |
| `st`  | `"ok"` (ChatGPT-Backend liefert keinen separaten Status) |

Pace- und Regen-Logik sind 1:1 vom Anthropic-Adapter übernommen — die Fensterlänge wird allerdings dynamisch aus `limit_window_seconds` gelesen, falls OpenAI sie irgendwann anhebt.

## Token-Quelle (`auth.json`)

CodexBar dokumentiert zwei beobachtete Formate; der Adapter unterstützt beide:

1. **OAuth (Default, von `codex login` erzeugt)**:
   ```jsonc
   {
     "tokens": {
       "access_token": "eyJhbGci…",
       "refresh_token": "…",
       "id_token": "eyJhbGci…",        // optional
       "account_id": "acc_…"            // optional → ChatGPT-Account-Id-Header
     },
     "last_refresh": "2026-05-24T11:22:33Z"
   }
   ```
2. **Direkter API-Key**: `{"OPENAI_API_KEY": "sk-..."}` — wird als Bearer-Token gesendet, funktioniert aber gegen `chatgpt.com/backend-api/wham/usage` typischerweise **nicht** (der Endpunkt erwartet ChatGPT-OAuth-Tokens). Wenn dein Setup so aussieht, lieber die OpenAI-Platform-API als eigenen Provider abbilden.

Der Adapter **refreshed Tokens nicht selbst**. Die `codex`-CLI macht das beim nächsten Start automatisch. Bei HTTP 401/403 loggt der Daemon einen Hinweis und überspringt diesen Zyklus.

## Request

```text
GET https://chatgpt.com/backend-api/wham/usage
Authorization: Bearer <tokens.access_token>
Accept: application/json
User-Agent: clawdmeter-daemon/0.1
ChatGPT-Account-Id: <tokens.account_id>   ← nur wenn vorhanden
```

Die Basis-URL ist überschreibbar in dieser Präferenz-Reihenfolge:

1. `base_url`-Feld im `[[provider]]`-Block (höchste Priorität)
2. Env-Var `CLAWDMETER_CODEX_BASE_URL`
3. `chatgpt_base_url = "..."`-Key in `~/.codex/config.toml` (derselbe Override, den die `codex`-CLI selbst respektiert)
4. Default: `https://chatgpt.com/backend-api`

Wenn die Basis-URL nicht das Segment `/backend-api` enthält (z. B. eigener Codex-Proxy), wird stattdessen `/api/codex/usage` angehängt — analog zur Logik in CodexBar.

## Response (abgekürzt)

```jsonc
{
  "plan_type": "plus",
  "rate_limit": {
    "primary_window":   { "used_percent": 42, "reset_at": 1716651600, "limit_window_seconds": 18000 },
    "secondary_window": { "used_percent": 11, "reset_at": 1716998400, "limit_window_seconds": 604800 }
  },
  "credits": { "has_credits": false, "unlimited": true, "balance": null }
}
```

- `limit_window_seconds = 18000` → 5h-Session (m1).
- `limit_window_seconds = 604800` → 7d-Weekly (m2).
- `reset_at` ist ein Unix-Timestamp (Sekunden seit Epoch).

Der Adapter sortiert `primary_window`/`secondary_window` defensiv nach `limit_window_seconds` um, damit Reihenfolgen-Drifts im Backend nicht zu vertauschten m1/m2 führen (siehe `_classify_windows`).

## Konfig-Snippet

```toml
[[provider]]
id = "codex"
enabled = true
poll_seconds = 60
slot_id = "codex"
display_name = "Codex"
display_note = ""           # leer = Plan-Typ (z. B. "Plus") wird automatisch eingesetzt
# base_url = ""              # optional, siehe oben
```

Default `poll_seconds = 60` ist analog zum Anthropic-Adapter — der `/wham/usage`-Endpunkt ist quasi kostenfrei (nur Header-Read).

## Setup-Wizard

`clawdmeter-daemon setup` ruft `wizard_codex` zwischen Anthropic und Langdock auf. Erkennt automatisch:

- Existenz und Lesbarkeit von `~/.codex/auth.json`.
- Welcher Token-Typ vorliegt (OAuth vs. `OPENAI_API_KEY`).
- Bestehende Konfig-Werte (re-runnable).

## Bekannte Stolpersteine

1. **Plan ohne Quota.** Plan-Typen `free`/`guest` liefern `rate_limit: null`. Der Adapter loggt das einmal pro Poll und überspringt den Zyklus — `last_snapshot` bleibt sichtbar.
2. **OAuth-Token altert.** `last_refresh` schreibt die CLI bei jedem Login. Wenn der Daemon dauerhaft 401 liefert: `codex` einmal manuell starten.
3. **`account_id` fehlt bei einigen älteren CLI-Versionen.** Dann fehlt der `ChatGPT-Account-Id`-Header — der Backend-Endpoint funktioniert trotzdem, aber bei Multi-Account-Setups landest du auf dem Default-Workspace.
4. **Kein Refresh-Flow.** Wir implementieren bewusst keinen eigenen Refresh; das Refresh-Token bleibt unangerührt. Sollte der `codex` CLI-Refresh-Mechanismus mal wegfallen, müssen wir hier nachziehen (Endpoint dann typischerweise `https://auth.openai.com/oauth/token` mit `grant_type=refresh_token`).
5. **`OPENAI_API_KEY`-Modus** ruft denselben Endpoint mit dem API-Key als Bearer auf — wird in der Regel mit 401 fehlschlagen, weil `wham/usage` ChatGPT-OAuth erwartet. Use case: dokumentiert, aber nicht der Hauptpfad.

## Referenz

- CodexBar-Forschungsnotiz: [feature-documentation/research/codexbar-reference.md](../research/codexbar-reference.md).
- Swift-Original (für Endpoint + Schema): `Sources/CodexBarCore/Providers/Codex/CodexOAuth/{CodexOAuthCredentials,CodexOAuthUsageFetcher}.swift` im [CodexBar-Repo](https://github.com/steipete/CodexBar).
