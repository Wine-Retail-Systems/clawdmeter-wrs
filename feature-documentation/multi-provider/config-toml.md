# Config-Datei `config.toml`

Stand 2026-05-24. Die TOML ist die einzige Quelle für „welcher Provider
ist aktiv, wie heißt er, wie oft wird gepollt, wo liegen Credentials".

> ⏸️ **Bedrock-Hinweis**: Die Bedrock-Beispielblöcke unten zeigen das
> Schema, falls du den Adapter manuell reaktivierst. Der Setup-Wizard
> fragt Bedrock derzeit nicht ab; ohne IAM-Profil pollt der Adapter
> nichts. Details: [providers/bedrock.md](../providers/bedrock.md).

## Pfad

| OS       | Pfad                                          |
| -------- | --------------------------------------------- |
| Linux    | `~/.config/clawdmeter/config.toml`            |
| macOS    | `~/.config/clawdmeter/config.toml`            |
| Windows  | `%APPDATA%\clawdmeter\config.toml`            |

Wird beim ersten Daemon-Start angelegt (mit allem disabled) — kein Crash
ohne Config. Genauer Pfad anzeigen mit `clawdmeter-daemon config`.

## Struktur

```toml
[device]
name = "Clawdmeter"            # Muss dem BLE-Namen der Firmware entsprechen
scan_timeout_seconds = 8.0

[[provider]]
id = "anthropic"               # Adapter-Familie (anthropic|langdock|opencode|bedrock)
enabled = true
slot_id = "anthropic"          # Eindeutige Slot-ID auf dem Gerät (≤12 chars)
display_name = "Claude"         # 16 chars max
display_note = ""               # Optional 16 chars max
poll_seconds = 60
# Anthropic-spezifisch: keine — Token kommt aus Keychain/credentials.json

[[provider]]
id = "langdock"
enabled = false
slot_id = "langdock"
display_name = "Langdock"
display_note = "BYOK"
poll_seconds = 600
api_key_env = "LANGDOCK_API_KEY"
monthly_budget_eur = 250
currency = "EUR"
usd_to_eur = 0.92

[[provider]]
id = "opencode"
enabled = false
slot_id = "opencode"
display_name = "OpenCode"
poll_seconds = 15
db_path = ""                   # Leer = XDG-Auto-Detect
include_backend_quota = true

# Bedrock: ein Block pro Modell, alle teilen Region + Profile
[[provider]]
id = "bedrock"
enabled = false
slot_id = "bedrock-s45"        # MUSS pro Block eindeutig sein!
display_name = "Bedrock"
display_note = "Sonnet 4.5"
poll_seconds = 60
region = "eu-central-1"
model_id = "anthropic.claude-sonnet-4-5-20250929-v1:0"
aws_profile = ""               # Leer = default chain
currency = "USD"

[[provider]]
id = "bedrock"
enabled = false
slot_id = "bedrock-h45"
display_name = "Bedrock"
display_note = "Haiku 4.5"
poll_seconds = 60
region = "eu-central-1"
model_id = "anthropic.claude-haiku-4-5-20251001-v1:0"
currency = "USD"
```

## Regeln

- Felder fehlen → Default greift (siehe `config.py::ProviderConfig`).
- `enabled = false` oder Block fehlt → Adapter wird nicht instantiiert.
- Mehrere Blöcke mit derselben `id` sind erlaubt (z. B. mehrere Bedrock-
  Modelle), müssen aber **unterschiedliche `slot_id`** haben — die
  Slot-ID landet im BLE-Payload und identifiziert den Screen.
- Secrets gehören **nie** ins TOML. `api_key_env` zeigt auf den Namen
  einer Env-Var; der Daemon liest sie zur Laufzeit.

## Sicherheitsmodell

Die Datei kann je nach Plattform user-readable sein. Sie enthält:
- BLE-Adresse (cache, separates File) → unkritisch.
- Workspace-Namen / Model-IDs → nicht-geheim.
- Region, Profil-Name → nicht-geheim.

Was sie **nicht** enthält:
- Anthropic-OAuth-Tokens (kommen aus Keychain / `~/.claude/.credentials.json`)
- Langdock-API-Keys (`LANGDOCK_API_KEY` Env-Var)
- AWS-Credentials (boto3 default chain → `~/.aws/credentials`, `AWS_PROFILE` etc.)

Bei Backup/Sync ist die TOML also unbedenklich; der `~/.aws/credentials`-
und Keychain-Pfad muss vom User separat abgesichert werden.

## Edit-Workflow

1. Daemon stoppen: `systemctl --user stop clawdmeter-daemon` (Linux) /
   `launchctl unload …` (macOS) / `schtasks /End …` (Windows).
2. TOML editieren.
3. `clawdmeter-daemon doctor` zeigt, wie der Daemon die Datei interpretiert.
4. Daemon wieder starten.

Alternativ: `clawdmeter-daemon setup` erneut laufen lassen — er liest die
bestehende TOML, nutzt vorhandene Werte als Defaults, schreibt sauber zurück.
