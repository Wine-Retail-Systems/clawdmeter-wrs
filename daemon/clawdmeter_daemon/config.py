"""Config loading + default-config generation.

The daemon's behaviour is fully driven by a TOML file at the platform-specific
config path (see paths.config_file). Each [[provider]] block opts a provider
in; missing or `enabled = false` blocks are skipped entirely. Secrets live in
env vars, not in this file.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import paths

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        tomllib = None  # type: ignore


DEFAULT_CONFIG = """# Clawdmeter daemon configuration
#
# Each provider you want to monitor needs its own [[provider]] block with
# `enabled = true`. The defaults below have everything disabled — run
# `clawdmeter-daemon setup` for an interactive walk-through, or edit this
# file by hand.

[device]
# BLE peripheral name advertised by the firmware. Override only if you
# customized the device name in the firmware build.
name = "Clawdmeter"
scan_timeout_seconds = 8.0

# ---- Anthropic Claude (claude.ai / Claude Code subscription) ----
[[provider]]
id = "anthropic"
enabled = false
poll_seconds = 60
slot_id = "anthropic"
display_name = "Claude"
display_note = ""
# Token source: keychain on macOS (service "Claude Code-credentials"),
# else ~/.claude/.credentials.json. No config needed.

# ---- OpenAI Codex / ChatGPT (codex CLI subscription) ----
[[provider]]
id = "codex"
enabled = false
poll_seconds = 60
slot_id = "codex"
display_name = "Codex"
display_note = ""
# Token source: ~/.codex/auth.json (or $CODEX_HOME/auth.json), populated by
# `codex login`. The codex CLI auto-refreshes — on 401 just run `codex` again.
# Optionally override the backend base URL (otherwise read from
# ~/.codex/config.toml's chatgpt_base_url, falling back to
# https://chatgpt.com/backend-api).
# base_url = ""

# ---- Langdock (Workspace-based, EUR-Budget) ----
[[provider]]
id = "langdock"
enabled = false
poll_seconds = 600
slot_id = "langdock"
display_name = "Langdock"
display_note = ""
# Name of the env var the daemon reads. The actual value is stored in
# ~/.config/clawdmeter/secrets.env (chmod 600), written by the setup wizard.
# A shell-exported value with the same name still wins if present.
api_key_env = "LANGDOCK_API_KEY"
# Workspace monthly budget in EUR. 0 = no budget configured — display
# shows raw EUR spend without an utilization bar.
monthly_budget_eur = 0
# Currency the user is billed in. Langdock invoices in EUR; the API
# returns pricing in USD per 1M tokens which we convert at usd_to_eur.
currency = "EUR"
usd_to_eur = 0.92
# Optional email filter. /export/users returns one row per workspace member;
# without this filter the daemon sums the whole org. Set this to your login
# email to scope the slot to your personal usage.
# user_email = "you@example.com"

# ---- OpenCode (sst/opencode local CLI) ----
[[provider]]
id = "opencode"
enabled = false
poll_seconds = 15
slot_id = "opencode"
display_name = "OpenCode"
display_note = ""
# Empty = auto-detect from XDG_DATA_HOME / platform default.
db_path = ""
# When true, the OpenCode screen also shows the backend provider's quota
# as a secondary metric (m2). Requires the backend provider to be enabled
# as a separate [[provider]] entry.
include_backend_quota = true

# ---- AWS Bedrock — AKTUELL DEAKTIVIERT ----
# Der Bedrock-Adapter pollt CloudWatch (`GetMetricStatistics`) + Service Quotas
# (`ListServiceQuotas`). Diese Calls sind NICHT von einem Bedrock-API-Key
# (`AWS_BEARER_TOKEN_BEDROCK`) abgedeckt — der Key authentifiziert nur die
# Bedrock-Runtime (`InvokeModel`/`Converse`). Für den Adapter braucht es daher
# echte IAM-Credentials mit Read-Only-Berechtigungen auf CloudWatch + Service
# Quotas. Der Setup-Wizard fragt Bedrock deshalb derzeit nicht ab; der
# Adapter-Code bleibt aber im Repo und kann von Hand reaktiviert werden,
# sobald ein IAM-Profil vorhanden ist. Beispielblock zum Auskommentieren:
#
# [[provider]]
# id = "bedrock"
# enabled = true
# poll_seconds = 60
# slot_id = "bedrock-s45"
# display_name = "Bedrock"
# display_note = "Sonnet 4.5"
# region = "eu-central-1"
# model_id = "anthropic.claude-sonnet-4-5-20250929-v1:0"
# aws_profile = "clawdmeter"
# currency = "USD"
"""


@dataclass
class DeviceConfig:
    name: str = "Clawdmeter"
    scan_timeout_seconds: float = 8.0


@dataclass
class ProviderConfig:
    """One [[provider]] block — raw dict access + a few typed accessors."""

    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return str(self.raw.get("id", ""))

    @property
    def enabled(self) -> bool:
        return bool(self.raw.get("enabled", False))

    @property
    def poll_seconds(self) -> int:
        return int(self.raw.get("poll_seconds", 60))

    @property
    def slot_id(self) -> str:
        return str(self.raw.get("slot_id") or self.id)

    @property
    def display_name(self) -> str:
        return str(self.raw.get("display_name") or self.id.title())

    @property
    def display_note(self) -> str:
        return str(self.raw.get("display_note", ""))

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)


@dataclass
class Config:
    device: DeviceConfig
    providers: list[ProviderConfig]
    source_path: Path | None

    @property
    def enabled_providers(self) -> list[ProviderConfig]:
        return [p for p in self.providers if p.enabled]


def ensure_default_config_exists() -> Path:
    """Write the default config if none exists yet. Returns the path."""
    cfg_path = paths.config_file()
    if cfg_path.exists():
        return cfg_path
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    return cfg_path


def load_config() -> Config:
    if tomllib is None:
        print(
            "Error: this Python lacks tomllib (need 3.11+) and tomli isn't "
            "installed. Run: pip install tomli",
            file=sys.stderr,
        )
        sys.exit(1)

    cfg_path = ensure_default_config_exists()
    with open(cfg_path, "rb") as fh:
        data = tomllib.load(fh)

    dev_raw = data.get("device") or {}
    device = DeviceConfig(
        name=str(dev_raw.get("name", "Clawdmeter")),
        scan_timeout_seconds=float(dev_raw.get("scan_timeout_seconds", 8.0)),
    )

    providers = [ProviderConfig(raw=block) for block in (data.get("provider") or [])]

    return Config(device=device, providers=providers, source_path=cfg_path)


def write_config_dict(data: dict[str, Any]) -> Path:
    """Serialize a dict back to TOML at the canonical path.

    Pure-Python TOML emitter — no external dep. Handles the subset we use:
    nested tables, arrays of tables, strings, ints, floats, bools.
    """
    cfg_path = paths.config_file()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(_emit_toml(data), encoding="utf-8")
    return cfg_path


def _emit_toml(data: dict[str, Any]) -> str:
    out: list[str] = []
    out.append("# Clawdmeter daemon configuration — generated by setup wizard\n")

    if "device" in data and isinstance(data["device"], dict):
        out.append("[device]")
        for k, v in data["device"].items():
            out.append(f"{k} = {_emit_value(v)}")
        out.append("")

    for block in data.get("provider", []):
        out.append("[[provider]]")
        for k, v in block.items():
            out.append(f"{k} = {_emit_value(v)}")
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def _emit_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, list):
        return "[" + ", ".join(_emit_value(x) for x in v) + "]"
    raise TypeError(f"Cannot emit TOML for {type(v).__name__}: {v!r}")
