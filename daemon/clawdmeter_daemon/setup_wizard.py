"""Interactive setup wizard — `clawdmeter-daemon setup`.

Walks through each known provider, auto-detects credentials/data sources
where possible, and writes a fresh config.toml. Re-runnable; reads the
existing config and uses found values as defaults.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import paths, secrets
from .config import load_config, write_config_dict


# ---------- yes/no + prompt helpers ----------


def prompt(question: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        out = input(f"  {question}{suffix}: ").strip()
    except EOFError:
        return default
    return out or default


def confirm(question: str, default: bool = True) -> bool:
    hint = "[J/n]" if default else "[j/N]"
    try:
        ans = input(f"  {question} {hint} ").strip().lower()
    except EOFError:
        return default
    if not ans:
        return default
    return ans in ("j", "y", "ja", "yes")


# ---------- auto-detect probes ----------


def detect_claude_token() -> str:
    """Return a short human-readable string describing where the token is, or
    an empty string if none was found."""
    if sys.platform == "darwin":
        try:
            r = subprocess.run(
                ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0 and r.stdout.strip():
                return "macOS Keychain"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    cred = paths.claude_credentials_file()
    if cred.exists():
        return str(cred)
    return ""


def detect_codex_token() -> str:
    """Return a short human-readable hint about where the Codex auth lives,
    or empty string. We deliberately never *read* the token here — just check
    that the file exists and contains either tokens.access_token or
    OPENAI_API_KEY."""
    path = paths.codex_auth_file()
    if not path.exists():
        return ""
    try:
        raw = path.read_text(encoding="utf-8")
        import json as _json
        blob = _json.loads(raw)
    except (OSError, ValueError):
        return f"{path} (unlesbar)"
    if not isinstance(blob, dict):
        return f"{path} (unerwartetes Format)"
    if isinstance(blob.get("OPENAI_API_KEY"), str) and blob["OPENAI_API_KEY"].strip():
        return f"{path} (OPENAI_API_KEY)"
    tokens = blob.get("tokens") if isinstance(blob.get("tokens"), dict) else None
    if tokens and isinstance(tokens.get("access_token") or tokens.get("accessToken"), str):
        return f"{path} (OAuth)"
    return f"{path} (kein Token gefunden)"


def detect_aws() -> tuple[bool, str]:
    """Return (creds_available, profile_or_source)."""
    cred = Path.home() / ".aws" / "credentials"
    if cred.exists():
        return True, str(cred)
    if os.environ.get("AWS_ACCESS_KEY_ID"):
        return True, "env"
    return False, ""


BIFROST_KEY_ENV = "BIFROST_VIRTUAL_KEY"
BIFROST_DEFAULT_URL = "https://llm-gw.wineretailsystems.cloud"
BIFROST_PREFIX = "sk-bf-"


def mask_bifrost_key(value: str) -> str:
    """``sk-bf-…abcd`` — prefix plus last four characters only."""
    if len(value) < 14:
        return secrets.mask(value)
    return f"{value[:6]}…{value[-4:]}"


def _gateway_root(url: str) -> str:
    """Strip any path from a base URL; invalid input -> default gateway."""
    from urllib.parse import urlparse

    try:
        u = urlparse((url or "").strip())
    except ValueError:
        return BIFROST_DEFAULT_URL
    if u.scheme not in ("http", "https") or not u.netloc:
        return BIFROST_DEFAULT_URL
    return f"{u.scheme}://{u.netloc}"


def find_claude_bifrost_key() -> dict | None:
    """Look for a Bifrost virtual key in the Claude Code setup.

    Returns ``{"token", "base_url", "source"}`` (token in clear text — callers
    must never print or return it) or None. Sources, in order: process env,
    then the ``env`` block of ``<claude config dir>/settings.json``.
    """
    token = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    if token.startswith(BIFROST_PREFIX):
        return {"token": token,
                "base_url": _gateway_root(os.environ.get("ANTHROPIC_BASE_URL", "")),
                "source": "env:ANTHROPIC_AUTH_TOKEN"}
    settings = paths.claude_credentials_dir() / "settings.json"
    try:
        import json as _json
        blob = _json.loads(settings.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    env = blob.get("env") if isinstance(blob, dict) else None
    if not isinstance(env, dict):
        return None
    token = env.get("ANTHROPIC_AUTH_TOKEN")
    if isinstance(token, str) and token.startswith(BIFROST_PREFIX):
        base = env.get("ANTHROPIC_BASE_URL")
        return {"token": token,
                "base_url": _gateway_root(base if isinstance(base, str) else ""),
                "source": f"{settings}"}
    return None


def detect_bifrost(env_name: str = BIFROST_KEY_ENV) -> dict:
    """Clear-text-free detection result for CLI wizard and IPC.

    Keys: detected, source, notes, masked, base_url.
    """
    found = find_claude_bifrost_key()
    if found:
        return {"detected": True, "source": found["source"],
                "notes": "Virtual Key aus Claude-Code-Konfiguration",
                "masked": mask_bifrost_key(found["token"]),
                "base_url": found["base_url"]}
    stored = os.environ.get(env_name) or secrets.read_all().get(env_name) or ""
    if stored:
        return {"detected": True, "source": secrets.describe_source(env_name) or "secrets.env",
                "notes": f"{env_name} bereits hinterlegt",
                "masked": mask_bifrost_key(stored), "base_url": BIFROST_DEFAULT_URL}
    return {"detected": False, "source": None,
            "notes": "Kein sk-bf-Token in Umgebung oder ~/.claude/settings.json",
            "masked": None, "base_url": BIFROST_DEFAULT_URL}


def detect_langdock_key(env_name: str = "LANGDOCK_API_KEY") -> str:
    """Return a short human-readable source for the Langdock key, or empty."""
    return secrets.describe_source(env_name)


# ---------- per-provider wizards ----------


def existing_block(existing: dict, provider_id: str, slot_id: str | None = None) -> dict:
    for b in existing.get("provider") or []:
        if b.get("id") == provider_id and (slot_id is None or b.get("slot_id") == slot_id):
            return dict(b)
    return {"id": provider_id, "enabled": False}


def wizard_anthropic(existing: dict, out: list[dict]) -> None:
    print("\nAnthropic Claude")
    src = detect_claude_token()
    if src:
        print(f"  ✓ OAuth-Token gefunden: {src}")
    else:
        print("  ✗ Kein OAuth-Token gefunden (Keychain leer und ~/.claude/.credentials.json fehlt)")
        print("    Logge dich erst mit Claude Code ein, dann re-run dieses Wizards.")

    cur = existing_block(existing, "anthropic")
    enable = confirm("Anthropic aktivieren?", default=bool(src) or bool(cur.get("enabled")))
    out.append({
        "id": "anthropic",
        "enabled": enable,
        "poll_seconds": int(cur.get("poll_seconds", 60)),
        "slot_id": cur.get("slot_id", "anthropic"),
        "display_name": cur.get("display_name", "Claude"),
        "display_note": cur.get("display_note", ""),
    })


def wizard_codex(existing: dict, out: list[dict]) -> None:
    print("\nOpenAI Codex / ChatGPT")
    src = detect_codex_token()
    if src:
        print(f"  ✓ Codex-Auth gefunden: {src}")
    else:
        print("  ✗ Kein ~/.codex/auth.json — bitte zuerst `codex` einloggen, dann Wizard erneut starten.")

    cur = existing_block(existing, "codex")
    enable = confirm("Codex aktivieren?", default=bool(src) or bool(cur.get("enabled")))
    out.append({
        "id": "codex",
        "enabled": enable,
        "poll_seconds": int(cur.get("poll_seconds", 60)),
        "slot_id": cur.get("slot_id", "codex"),
        "display_name": cur.get("display_name", "Codex"),
        "display_note": cur.get("display_note", ""),
    })


def wizard_langdock(existing: dict, out: list[dict]) -> None:
    print("\nLangdock")
    cur = existing_block(existing, "langdock")
    env_name = cur.get("api_key_env", "LANGDOCK_API_KEY")

    source = detect_langdock_key(env_name)
    if source:
        print(f"  ✓ {env_name} gefunden in: {source}")
    else:
        print(f"  ✗ {env_name} noch nicht hinterlegt")

    enable = confirm("Langdock aktivieren?", default=bool(cur.get("enabled")) or bool(source))
    if not enable:
        out.append({"id": "langdock", "enabled": False,
                    "slot_id": cur.get("slot_id", "langdock"),
                    "display_name": cur.get("display_name", "Langdock"),
                    "api_key_env": env_name,
                    "monthly_budget_eur": int(cur.get("monthly_budget_eur", 0))})
        return

    # API-Key abfragen. Wenn schon einer hinterlegt ist, Enter behält ihn.
    if source:
        new_key = prompt(
            f"API-Key (Enter = vorhandenen Wert aus {source} behalten)",
            default="",
        )
    else:
        new_key = prompt(
            "API-Key (wird nach ~/.config/clawdmeter/secrets.env geschrieben, chmod 600)",
            default="",
        )
    if new_key:
        if os.environ.get(env_name) and os.environ[env_name] != new_key:
            print(f"  Hinweis: Shell-Env {env_name} ist gesetzt und überschreibt den gespeicherten Wert.")
        path = secrets.write(env_name, new_key)
        os.environ[env_name] = new_key  # damit folgende doctor-/poll-Calls in derselben Session ihn sehen
        print(f"  ✓ Key gespeichert in {path} ({secrets.mask(new_key)})")
    elif not source:
        print("  ! Kein Key hinterlegt — Daemon wird beim Polling skippen.")

    budget_raw = prompt(
        "Monatsbudget in EUR (0 = ohne Budget, nur Verbrauch zeigen)",
        default=str(cur.get("monthly_budget_eur", 0)),
    )
    try:
        budget = float(budget_raw)
    except ValueError:
        budget = 0.0
    note = prompt("Display-Untertitel (optional, z. B. 'BYOK', 'managed')",
                  default=str(cur.get("display_note", "")))

    out.append({
        "id": "langdock",
        "enabled": True,
        "poll_seconds": int(cur.get("poll_seconds", 600)),
        "slot_id": cur.get("slot_id", "langdock"),
        "display_name": cur.get("display_name", "Langdock"),
        "display_note": note,
        "api_key_env": cur.get("api_key_env", "LANGDOCK_API_KEY"),
        "monthly_budget_eur": budget,
        "currency": cur.get("currency", "EUR"),
        "usd_to_eur": float(cur.get("usd_to_eur", 0.92)),
    })


def wizard_bifrost(existing: dict, out: list[dict]) -> None:
    import getpass

    print("\nBifrost (LLM Gateway)")
    cur = existing_block(existing, "bifrost")
    env_name = cur.get("api_key_env", BIFROST_KEY_ENV)
    found = find_claude_bifrost_key()
    det = detect_bifrost(env_name)
    base_url = cur.get("base_url") or (found["base_url"] if found else BIFROST_DEFAULT_URL)

    if det["detected"]:
        print(f"  ✓ Virtual Key gefunden: {det['source']} ({det['masked']})")
    else:
        print("  ✗ Kein sk-bf-Virtual-Key gefunden")

    enable = confirm("Bifrost aktivieren?", default=bool(cur.get("enabled")) or det["detected"])
    if not enable:
        out.append({"id": "bifrost", "enabled": False,
                    "slot_id": cur.get("slot_id", "bifrost"),
                    "api_key_env": env_name, "base_url": base_url})
        return

    if found and confirm(f"Erkannten Key aus {found['source']} übernehmen?", default=True):
        path = secrets.write(env_name, found["token"])
        os.environ[env_name] = found["token"]
        print(f"  ✓ Key gespeichert in {path} ({mask_bifrost_key(found['token'])})")
    else:
        try:
            new_key = getpass.getpass("  Virtual Key (Eingabe verdeckt, Enter = vorhandenen behalten): ").strip()
        except EOFError:
            new_key = ""
        if new_key:
            path = secrets.write(env_name, new_key)
            os.environ[env_name] = new_key
            print(f"  ✓ Key gespeichert in {path} ({mask_bifrost_key(new_key)})")
        elif not det["detected"]:
            print("  ! Kein Key hinterlegt — Daemon wird beim Polling skippen.")

    base_url = prompt("Gateway-URL", default=base_url)
    note = prompt("Display-Untertitel (leer = Name aus dem Key)",
                  default=str(cur.get("display_note", "")))
    out.append({
        "id": "bifrost",
        "enabled": True,
        "poll_seconds": int(cur.get("poll_seconds", 120)),
        "slot_id": cur.get("slot_id", "bifrost"),
        "display_name": cur.get("display_name", "LLM Gateway"),
        "display_note": note,
        "api_key_env": env_name,
        "base_url": base_url,
    })


def _preserve_existing_bedrock_blocks(existing: dict, out: list[dict]) -> None:
    """Re-Run-Safety: trägt bestehende Bedrock-Blöcke 1:1 in die neue Config ein.

    Wir fragen Bedrock im Wizard nicht mehr ab (siehe Kommentar in run()),
    aber wenn jemand schon konfiguriert hat, soll ein Wizard-Re-Run die
    Blöcke nicht löschen — sonst muss er die Modell-IDs erneut von Hand
    eintragen.
    """
    for block in existing.get("provider") or []:
        if block.get("id") == "bedrock":
            out.append(dict(block))


def wizard_bedrock(existing: dict, out: list[dict]) -> None:
    """Bedrock-Wizard — aktuell **nicht** im Standardablauf von run().

    Funktion bleibt erhalten als Vorlage für einen späteren Re-Enable,
    sobald wir einen sauberen IAM- oder Bedrock-API-Key-Pfad haben.
    """
    print("\nAWS Bedrock")
    ok, src = detect_aws()
    if ok:
        print(f"  ✓ AWS-Credentials gefunden: {src}")
    else:
        print("  ✗ Keine AWS-Credentials gefunden (~/.aws/credentials fehlt, kein AWS_ACCESS_KEY_ID)")

    cur_blocks = [b for b in (existing.get("provider") or []) if b.get("id") == "bedrock"]
    enable = confirm("Bedrock aktivieren?", default=bool(cur_blocks) or ok)
    if not enable:
        return

    region = prompt(
        "Region",
        default=cur_blocks[0].get("region", "eu-central-1") if cur_blocks else "eu-central-1",
    )
    profile = prompt(
        "AWS-Profile (leer = default chain)",
        default=cur_blocks[0].get("aws_profile", "") if cur_blocks else "",
    )

    print("  Modelle (eines pro Zeile, leere Zeile beendet)")
    seen_ids = []
    if cur_blocks:
        print("  Aktuell konfiguriert:")
        for b in cur_blocks:
            print(f"    - {b.get('slot_id')} ({b.get('model_id')})")
            seen_ids.append((b.get("slot_id"), b.get("model_id"), b.get("display_note", "")))
        keep = confirm("Vorhandene Bedrock-Modelle übernehmen?", default=True)
        if keep:
            for slot_id, model_id, note in seen_ids:
                out.append({
                    "id": "bedrock",
                    "enabled": True,
                    "poll_seconds": 60,
                    "slot_id": slot_id,
                    "display_name": "Bedrock",
                    "display_note": note,
                    "region": region,
                    "model_id": model_id,
                    "aws_profile": profile,
                    "currency": "USD",
                })

    print("  Neue Modelle hinzufügen — format: <slot_id>=<model_id>")
    print("  Beispiel: bedrock-s45=anthropic.claude-sonnet-4-5-20250929-v1:0")
    while True:
        line = prompt("Modell", default="")
        if not line:
            break
        if "=" not in line:
            print("    Format ist <slot_id>=<model_id>, übersprungen")
            continue
        slot_id, model_id = line.split("=", 1)
        out.append({
            "id": "bedrock",
            "enabled": True,
            "poll_seconds": 60,
            "slot_id": slot_id.strip(),
            "display_name": "Bedrock",
            "display_note": "",
            "region": region,
            "model_id": model_id.strip(),
            "aws_profile": profile,
            "currency": "USD",
        })


# ---------- top-level entry ----------


def run() -> None:
    print("=== Clawdmeter Setup-Wizard ===\n")
    print(f"Config-Datei: {paths.config_file()}")
    print(f"Secrets-Datei: {paths.secrets_file()}")
    print(f"Adress-Cache: {paths.address_cache_file()}\n")
    secrets.load_into_env()

    # Re-runnable: load existing TOML if present so we keep settings.
    existing: dict[str, Any] = {}
    if paths.config_file().exists():
        try:
            cfg = load_config()
            existing = {
                "device": {
                    "name": cfg.device.name,
                    "scan_timeout_seconds": cfg.device.scan_timeout_seconds,
                },
                "provider": [p.raw for p in cfg.providers],
            }
        except SystemExit:
            existing = {}

    device_name = prompt(
        "Name des BLE-Geräts",
        default=(existing.get("device") or {}).get("name") or "Clawdmeter",
    )

    out: list[dict] = []
    wizard_anthropic(existing, out)
    wizard_codex(existing, out)
    wizard_langdock(existing, out)
    wizard_bifrost(existing, out)
    # AWS Bedrock ist aktuell nicht im interaktiven Wizard — der Adapter
    # braucht IAM-Credentials für CloudWatch + Service Quotas, die ein
    # Bedrock-API-Key alleine nicht abdeckt. Bestehende Bedrock-Blöcke aus
    # der vorhandenen Config werden trotzdem übernommen, damit Re-Runs nicht
    # versehentlich Konfiguration verlieren.
    _preserve_existing_bedrock_blocks(existing, out)

    data = {
        "device": {
            "name": device_name,
            "scan_timeout_seconds": float(
                (existing.get("device") or {}).get("scan_timeout_seconds") or 8.0
            ),
        },
        "provider": out,
    }
    path = write_config_dict(data)
    print(f"\nConfig geschrieben nach {path}.")
    print("Daemon starten mit: clawdmeter-daemon run   (oder via systemd/launchd)\n")
