# OpenCode Provider — Discovery

## Was ist OpenCode (kurz)

OpenCode (Repo: [`sst/opencode`](https://github.com/sst/opencode)) ist ein
Open-Source-Coding-Agent, geschrieben in TypeScript (Runtime: Bun) mit einem
Go-TUI. Ähnlich zu Claude Code, aber **provider-agnostisch**: Über das
AI-SDK und Models.dev werden 75+ LLM-Backends angesprochen (Anthropic,
OpenAI, Bedrock, OpenRouter, Ollama, ...). Seit der Beta-Welle ab ~v1.1.53
liegt der gesamte Session-State in einer lokalen SQLite-Datenbank
(`opencode.db`, Drizzle ORM, WAL-Mode). Cost- und Token-Counts werden pro
Message **und** aggregiert pro Session vom Client selbst getrackt.

## Session-Log-Speicherort

OpenCode legt **Daten** (DB, Logs, Auth) und **Config** in getrennten
Verzeichnissen ab. Standard ist XDG-konform für Linux; macOS folgt
demselben XDG-Layout (kein `~/Library/Application Support`).

| OS      | Datenverzeichnis (DB + auth + logs)                                  | Config-Verzeichnis                        |
| ------- | -------------------------------------------------------------------- | ----------------------------------------- |
| Linux   | `$XDG_DATA_HOME/opencode` (Fallback: `~/.local/share/opencode`)      | `$XDG_CONFIG_HOME/opencode` (Fallback: `~/.config/opencode`) |
| macOS   | `~/.local/share/opencode` (XDG-style, **nicht** `~/Library/...`)     | `~/.config/opencode`                      |
| Windows | `%LOCALAPPDATA%\opencode` (typ. `C:\Users\<u>\AppData\Local\opencode`) | `%APPDATA%\opencode` bzw. `%USERPROFILE%\.config\opencode` |

Inhalt des Datenverzeichnisses (verifiziert auf macOS, OpenCode 1.15.10):

```text
~/.local/share/opencode/
├── opencode.db           # SQLite-Hauptdatenbank (Drizzle)
├── opencode.db-shm       # WAL Shared-Memory
├── opencode.db-wal       # Write-Ahead-Log
├── auth.json             # Provider-Credentials (chmod 600)
├── log/                  # Plaintext-Runtime-Logs (eine Datei je Start)
├── snapshot/             # Git-artige Snapshots pro Projekt
├── storage/              # Legacy-JSON-Storage + session_diff/
└── repos/
```

**Override-Env-Vars:**

- `OPENCODE_CONFIG` — Pfad zu einer alternativen Config-Datei
- `OPENCODE_CONFIG_DIR` — alternatives Config-Verzeichnis (Agents, Commands,
  Plugins)
- `OPENCODE_CONFIG_CONTENT` — Inline-Override (JSON-String)
- `OPENCODE_TUI_CONFIG` — Pfad zur TUI-Config
- `XDG_DATA_HOME`, `XDG_CONFIG_HOME` — werden respektiert
- Ein dediziertes `OPENCODE_HOME` ist **nicht** dokumentiert. Channel-Builds
  benutzen separate DB-Namen (z. B. `opencode-local.db` neben `opencode.db`).

Managed-Configs (admin-installed) liegen unter `/Library/Application
Support/opencode/` (macOS), `/etc/opencode/` (Linux), `%ProgramData%\opencode`
(Windows) — für den Poller irrelevant.

## Log-Schema

Format: **SQLite**, `drizzle-orm`-Schema. Relevant für den Poller sind drei
Tabellen.

### Tabelle `session` (aggregierte Counters — die Goldmine)

```sql
CREATE TABLE session (
  id              text PRIMARY KEY,        -- 'ses_<rand>'
  project_id      text NOT NULL,
  parent_id       text,                    -- bei Subagents gesetzt
  slug            text NOT NULL,
  directory       text NOT NULL,           -- cwd der Session
  title           text NOT NULL,
  version         text NOT NULL,           -- OpenCode-Version, die geschrieben hat
  agent           text,                    -- 'build' | 'plan' | 'general' | ...
  model           text,                    -- JSON-String, siehe unten
  cost            real DEFAULT 0,          -- USD
  tokens_input        integer DEFAULT 0,
  tokens_output       integer DEFAULT 0,
  tokens_reasoning    integer DEFAULT 0,
  tokens_cache_read   integer DEFAULT 0,
  tokens_cache_write  integer DEFAULT 0,
  time_created    integer NOT NULL,        -- Unix-MILLIS
  time_updated    integer NOT NULL,
  time_compacting integer,
  time_archived   integer,
  ...
);
```

Die fünf `tokens_*`-Spalten existieren erst seit Migration
`20260510033149_session_usage` (≈ OpenCode v1.14.x, Mai 2026). Bei älteren
Sessions sind sie 0 — die echten Counts liegen dann nur in den
Message-Blobs.

`model`-Feld ist ein eingebetteter JSON-String:

```json
{"id":"eu.anthropic.claude-opus-4-6-v1","providerID":"amazon-bedrock","variant":"default"}
```

`providerID` ist der eindeutige Provider-Slug (s. „Unterstützte Backends").

### Tabelle `message` (eine Zeile je User- oder Assistant-Message)

```sql
CREATE TABLE message (
  id            text PRIMARY KEY,           -- 'msg_<rand>'
  session_id    text NOT NULL,
  time_created  integer NOT NULL,           -- Unix-MILLIS
  time_updated  integer NOT NULL,
  data          text NOT NULL               -- JSON-Blob, siehe unten
);
CREATE INDEX message_session_time_created_id_idx ON message (session_id, time_created, id);
```

`data` (Assistant-Message, echtes Beispiel aus laufender Installation):

```json
{
  "parentID": "msg_e4f0fd067001QLUzd2OHeNnXE5",
  "role": "assistant",
  "mode": "build",
  "agent": "build",
  "path": {"cwd": "/Users/saschakrinke", "root": "/"},
  "cost": 0.0378535,
  "tokens": {
    "total": 63316,
    "input": 1,
    "output": 110,
    "reasoning": 0,
    "cache": {"write": 608, "read": 62597}
  },
  "modelID": "eu.anthropic.claude-opus-4-6-v1",
  "providerID": "amazon-bedrock",
  "time": {"created": 1779442952301, "completed": 1779442957239},
  "finish": "stop"
}
```

User-Messages tragen kein `tokens`-Feld, nur `role: "user"`, `time.created`
und das gewählte `model: {providerID, modelID}`.

### Tabelle `part` (granulare Schritt-Events innerhalb einer Message)

Enthält pro Assistant-Step ein `{"type":"step-finish","tokens":{...},"cost":...}`.
Für „Tokens heute" nicht benötigt — `message.data.tokens` ist bereits die
Aggregation aller Parts dieser Message.

### Token-Feld-Mapping (wichtig)

| Quelle               | input | output | reasoning | cache_read         | cache_write         |
| -------------------- | ----- | ------ | --------- | ------------------ | ------------------- |
| `session.tokens_*`   | `tokens_input` | `tokens_output` | `tokens_reasoning` | `tokens_cache_read` | `tokens_cache_write` |
| `message.data.tokens`| `input` | `output` | `reasoning` | `cache.read` | `cache.write` |

`total` in `message.data.tokens` ist **bereits** input+output+reasoning+
cache.read+cache.write — also nicht doppelt summieren.

## Aktiver Provider — wie ermitteln

Zwei Quellen, in dieser Priorität:

1. **Per Session/Message direkt aus der DB.** Jede Assistant-Message und
   jede Session-Zeile trägt `providerID` (z. B. `"anthropic"`,
   `"amazon-bedrock"`, `"openai"`, `"openrouter"`, `"ollama"`). Das ist der
   Ground-Truth — welcher Provider tatsächlich abgerechnet hat.
2. **Default aus der Config**, wenn man wissen will, was „als nächstes"
   benutzt wird:

   - Globale Config: `~/.config/opencode/opencode.json` (oder `.jsonc`).
   - Projekt-Override: `<projektroot>/opencode.json`.
   - Override via `OPENCODE_CONFIG` (Datei) oder `OPENCODE_CONFIG_CONTENT`
     (inline JSON).

   Relevantes Feld: das Top-Level `"model"` als `"<providerID>/<modelID>"`,
   z. B.:

   ```jsonc
   {
     "$schema": "https://opencode.ai/config.json",
     "model": "amazon-bedrock/claude-opus-4-6-eu",
     "provider": {
       "amazon-bedrock": { "options": { "region": "eu-central-1" }, "models": { ... } }
     }
   }
   ```

   Vor dem `/` steht der `providerID`-Slug, den wir für die Quota-Abfrage
   brauchen.

Credentials selbst liegen in `~/.local/share/opencode/auth.json`
(`{<providerID>: {type, key|access_token|refresh_token, ...}}`). Für den
Poller niemals lesen — der Daemon braucht nur den Provider-**Namen**, nicht
den Schlüssel.

## „Tokens heute" — Zähl-Logik

Empfohlene Strategie: **lokales Tagesfenster** (00:00 → 23:59 lokal), Read-Only
SQLite-Connection im URI-Mode mit `mode=ro&immutable=0` damit der laufende
OpenCode-Prozess nicht gestört wird.

```python
from __future__ import annotations
import json, sqlite3, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterator

def opencode_db_path() -> Path:
    import os
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "opencode" / "opencode.db"

def _connect_ro(db: Path) -> sqlite3.Connection:
    # uri=True + mode=ro: kein Lock-Konflikt mit laufendem OpenCode
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2.0)

def _day_bounds_ms(now: datetime | None = None) -> tuple[int, int]:
    now = now or datetime.now().astimezone()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)

def tokens_today(db_path: Path | None = None) -> dict:
    """
    Liefert die Token-Summen seit Mitternacht (lokal).

    Strategie: NICHT die aggregierten session.tokens_* nehmen — die zaehlen
    die GANZE Session, auch wenn sie gestern startete. Stattdessen die
    pro-Message-Counts aus message.data['tokens'] aufaddieren, gefiltert nach
    message.time_created.
    """
    db_path = db_path or opencode_db_path()
    if not db_path.exists():
        return {"input": 0, "output": 0, "reasoning": 0,
                "cache_read": 0, "cache_write": 0, "total": 0, "cost": 0.0,
                "providers": {}, "messages": 0}

    start_ms, end_ms = _day_bounds_ms()
    totals = {"input": 0, "output": 0, "reasoning": 0,
              "cache_read": 0, "cache_write": 0, "cost": 0.0}
    by_provider: dict[str, int] = {}
    n = 0

    with _connect_ro(db_path) as conn:
        cur = conn.execute(
            "SELECT data FROM message "
            "WHERE time_created >= ? AND time_created < ?",
            (start_ms, end_ms),
        )
        for (raw,) in cur:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            tok = msg.get("tokens")
            if not isinstance(tok, dict):
                continue   # User-Messages haben keine tokens
            n += 1
            totals["input"]     += int(tok.get("input")     or 0)
            totals["output"]    += int(tok.get("output")    or 0)
            totals["reasoning"] += int(tok.get("reasoning") or 0)
            cache = tok.get("cache") or {}
            totals["cache_read"]  += int(cache.get("read")  or 0)
            totals["cache_write"] += int(cache.get("write") or 0)
            totals["cost"]        += float(msg.get("cost")  or 0.0)

            pid = msg.get("providerID") or "unknown"
            by_provider[pid] = by_provider.get(pid, 0) + (
                int(tok.get("input") or 0) + int(tok.get("output") or 0)
                + int(cache.get("read") or 0) + int(cache.get("write") or 0)
                + int(tok.get("reasoning") or 0)
            )

    totals["total"] = (totals["input"] + totals["output"] + totals["reasoning"]
                       + totals["cache_read"] + totals["cache_write"])
    return {**totals, "providers": by_provider, "messages": n}

def active_provider(config_path: Path | None = None) -> tuple[str, str] | None:
    """
    Liest opencode.json und gibt (providerID, modelID) zurueck, z. B.
    ('amazon-bedrock', 'claude-opus-4-6-eu'). Fallback: meistgenutzter
    Provider in den letzten 24h aus der DB.
    """
    import os, re
    config_path = config_path or Path(
        os.environ.get("OPENCODE_CONFIG")
        or (Path(os.environ.get("XDG_CONFIG_HOME") or Path.home()/".config")
            / "opencode" / "opencode.json")
    )
    # opencode.jsonc → Kommentare entfernen, dann parsen
    if config_path.exists():
        text = config_path.read_text(encoding="utf-8")
        text = re.sub(r"//.*?$|/\*.*?\*/", "", text, flags=re.M | re.S)
        try:
            cfg = json.loads(text)
            model = cfg.get("model")
            if isinstance(model, str) and "/" in model:
                pid, _, mid = model.partition("/")
                return pid, mid
        except json.JSONDecodeError:
            pass
    return None
```

Anmerkungen:

- **Kein Doppelzählen mit `session.tokens_*`**: Diese Aggregate enthalten
  alle Messages der Session seit deren Erzeugung — eine Session, die um
  23:55 angefangen und um 00:05 weitergetippt wurde, würde sonst gestern
  und heute gezählt. Pro-Message-Filterung über `message.time_created` ist
  präzise.
- **Cache-Tokens zählen mit**: Anthropic rechnet Cache-Reads zu einem
  reduzierten Satz ab, sie sind aber Teil der „Belastung". Wir liefern
  beide Sichten (Detail + `total`); der Daemon entscheidet, was er aufs
  Display schickt.
- **Read-Only Connection** (`mode=ro` via URI) ist Pflicht. OpenCode hält
  WAL-Lock; ein normaler `connect()` würde gelegentlich locken.
- **Subagent-Sessions** (`parent_id IS NOT NULL`) sind eigene Rows mit
  eigenen Messages — wird durch den Message-Filter automatisch korrekt
  mitgezählt.

## Unterstützte Backends

OpenCode unterstützt offiziell „75+ Provider" via AI-SDK + Models.dev. Für
die Quota-Verknüpfung in unserem Daemon sind diese relevant (Slug = das,
was als `providerID` in DB und Config auftaucht):

| Slug              | Backend                | Quota-Quelle                              |
| ----------------- | ---------------------- | ----------------------------------------- |
| `anthropic`       | Anthropic API direkt   | Anthropic Usage API (OAuth-Token), wie bei Claude Code |
| `openai`          | OpenAI API             | `api.openai.com/v1/usage` (API-Key)       |
| `amazon-bedrock`  | AWS Bedrock            | CloudWatch Metrics + Service Quotas (IAM) |
| `azure`           | Azure OpenAI           | Azure Cost Mgmt API                       |
| `google`/`vertex` | Google Gemini / Vertex | GCP Billing API                           |
| `openrouter`      | OpenRouter Gateway     | `openrouter.ai/api/v1/auth/key` (Credits) |
| `groq`            | Groq                   | Header `x-ratelimit-*` aus letzter Response, kein offizielles Quota-Endpoint |
| `deepseek`        | DeepSeek               | `api.deepseek.com/user/balance`           |
| `xai`             | xAI Grok               | n/a — nur Header-Limits                   |
| `ollama`          | lokales Ollama         | **keine Quota** (lokal, unlimited)        |
| `lmstudio`        | LM Studio (lokal)      | **keine Quota**                           |
| `github-copilot`  | GitHub Copilot         | n/a (Subscription, kein Token-Counter)    |
| `gitlab-duo`      | GitLab Duo             | n/a                                       |
| `opencode`        | OpenCode Zen Gateway   | `opencode.ai`-Dashboard (kein offizielles API) |
| `cerebras`/`fireworks`/`togetherai`/`nvidia`/`huggingface` | Spezial-Inferenz | meist nur Header-Limits |

Für den MVP des Pollers reicht es, **anthropic + openrouter + amazon-bedrock
+ openai** mit echtem Quota-Lookup zu unterstützen und alle anderen als
„Quota: n/a" zu markieren. Lokale Backends (`ollama`, `lmstudio`) bekommen
fix `100 %` oder ein Strom-Symbol — sinnloser Wert für ein Limit, das es
nicht gibt.

## Schema-Stabilität

**Status:** im Fluss. Die Drizzle-Migrations-Tabelle dieser Installation
zeigt **20 Schema-Migrationen** zwischen Januar und Mai 2026 — davon sind
mehrere für unser Token-Tracking direkt relevant:

| Migration                                   | Wirkung                                                                                                |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `20260510033149_session_usage`              | Fügt `tokens_input/output/reasoning/cache_read/cache_write` + `cost` auf `session` hinzu (Mai 2026).  |
| `20260423070820_add_icon_url_override`      | Project-Icons, irrelevant.                                                                             |
| `20260323234822_events`                     | Neue `event`-Tabelle (Event-Sourcing-Vorbereitung).                                                    |
| `20260427172553_slow_nightmare`             | Diverses Aufräumen.                                                                                    |

**Bruch-Risiko für den Poller:**

- `message.data` ist ein **opaker JSON-Blob** und kann ohne SQL-Migration
  Felder umbenennen. Empfehlung: defensives `dict.get()` mit Defaults,
  keine Schema-Asserts.
- Vor `session_usage` (Mai 2026, ≈ OpenCode 1.14) existieren die
  `tokens_*`-Spalten nicht — Poller muss `PRAGMA table_info(session)` oder
  einen `try/except` um den SQL nehmen, falls wir später auf
  `session.tokens_*` umsteigen wollen (aktuell tun wir das nicht; wir
  lesen Messages).
- Channel-Builds (`opencode-local.db` etc.) sind eigene Dateien neben
  `opencode.db`. Falls relevant: alle `opencode*.db` im Datenverzeichnis
  glob'en und summieren.
- Versionen, die in dieser Installation in die DB geschrieben haben:
  1.4.9 → 1.14.39 → 1.14.41 → 1.15.5 → 1.15.10 (alle koexistieren in
  derselben DB, Schema ist abwärtskompatibel über Migrations).

**Konsultierte Version:** OpenCode CLI **1.15.10** (lokal installiert,
`/opt/homebrew/bin/opencode`), DB-Schema-Stand
`20260510033149_session_usage`.

## Empfehlung für Clawdmeter

Vorgeschlagenes Mapping in den bestehenden BLE-Payload (`m1`, `m2`, `r1`,
`r2`, `st`):

| BLE-Feld | Inhalt                                                            | Quelle                                                                                          |
| -------- | ----------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `m1`     | Tokens heute (Summe input+output+reasoning+cache_read+cache_write)| Lokale SQLite-Aggregation über `message.data.tokens` (s. Python-Skizze).                        |
| `m2`     | Backend-Quota in `%` (0–100)                                      | Pro `providerID` ein Adapter. Lokale Backends (`ollama`/`lmstudio`) → `100`. Unbekannte → `null` → Splash-Zustand. |
| `r1`     | Sekunden bis 24h-Reset                                            | Diff zu nächster lokaler Mitternacht (gleich wie bisheriges Daily-Window).                      |
| `r2`     | Sekunden bis Backend-Reset                                        | Provider-spezifisch: Anthropic = Monatsbeginn UTC, OpenAI = Monatsbeginn UTC, OpenRouter = Credits haben keinen Reset → `null`. |
| `st`     | Status-String, max. 16 Bytes                                      | `"opencode • bedrock"` o. ä. — `providerID` short-form + Quelle.                                |

Konkrete Daemon-Pipeline:

1. **Polling-Tick** (z. B. alle 30 s): `tokens_today()` aus der lokalen DB
   ziehen → liefert `m1` + Provider-Top-Liste.
2. **Aktiven Provider bestimmen**: `active_provider()` aus
   `~/.config/opencode/opencode.json`, Fallback = häufigster
   `providerID` der heutigen Messages.
3. **Quota-Adapter** für diesen Provider aufrufen (eigene Module: 
   `quota_anthropic.py`, `quota_openrouter.py`, ...). Ergebnis ist ein
   Float 0..1 + ein Reset-Timestamp oder `None`.
4. Payload bauen, signieren, über GATT-Characteristic
   `4c41555a-...0002` schicken (siehe `CLAUDE.md` Daemon-Section).

Wiederverwendung des bestehenden Claude-Code-Pollers: Die Logik
„Tagesfenster + Mitternacht-Reset" kann 1:1 übernommen werden; die
Tokens-Quelle wird gegen `tokens_today()` ausgetauscht, alles andere
bleibt gleich.

## Offene Punkte

- **Anthropic-Quota bei Bedrock**: Bedrock-Sessions konsumieren keine
  Anthropic-Quota direkt — sie laufen über AWS. Wir brauchen vom User, ob
  er für die `amazon-bedrock`-Variante AWS Service Quotas via IAM-Key
  abfragen will (aufwendig) oder ob die Backend-Quota-Anzeige für Bedrock
  ausgeblendet werden soll.
- **OpenCode Zen Gateway** hat (noch) kein dokumentiertes Quota-API. User
  muss klären, ob das im MVP egal ist.
- **Multi-Channel-DBs**: Falls der User Beta-Channels (`opencode-local.db`,
  `opencode-canary.db`) parallel nutzt, müssen wir alle `opencode*.db` im
  Datenverzeichnis aggregieren — bitte bestätigen, dass die aktuelle
  Single-DB-Annahme reicht.
- **Reasoning-Tokens** (`tokens.reasoning`) sind bei Anthropic-Extended-
  Thinking-Modellen separat ausgewiesen. Anthropics Usage-API zählt sie
  intern zu Output-Tokens. Klären: in `m1` als Output mitzählen (aktuell
  ja) oder separat reporten?
- **Sub-Sessions** (`parent_id` gesetzt, z. B. `@general`-Subagent) sind
  eigene Session-Rows mit eigener Message-Liste — werden korrekt
  mitgezählt, aber die Aufschlüsselung „Hauptsession vs. Subagents" könnte
  später als zweite Metrik interessant sein.

## Quellen

- Lokale Installation: `/opt/homebrew/bin/opencode` v1.15.10
- Lokale Daten: `/Users/saschakrinke/.local/share/opencode/opencode.db`
  (verifiziert: 16 Sessions, 193 Messages, 624 Parts; Schema-Stand
  Migration #20 `session_usage`).
- Lokale Config: `/Users/saschakrinke/.config/opencode/opencode.jsonc`
- Repo: <https://github.com/sst/opencode>
- Docs: <https://opencode.ai/docs/>, <https://opencode.ai/docs/config/>,
  <https://opencode.ai/docs/providers/>
- Hintergrund zur JSON→SQLite-Migration: GitHub Issues #13654 und #16885
  in Forks von sst/opencode (alte JSON-Sessions können beim
  inkrementellen Upgrade liegen bleiben — für eine frische Installation
  irrelevant, aber gut zu wissen, falls beim User-Setup beides existiert).
