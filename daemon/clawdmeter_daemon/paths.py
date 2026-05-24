"""Cross-platform paths for config, state, and credentials."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def config_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "clawdmeter"
    return Path.home() / ".config" / "clawdmeter"


def state_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "clawdmeter"
    return Path.home() / ".config" / "clawdmeter"


def cache_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "clawdmeter" / "cache"
    return Path.home() / ".cache" / "clawdmeter"


def config_file() -> Path:
    return config_dir() / "config.toml"


def secrets_file() -> Path:
    return config_dir() / "secrets.env"


def address_cache_file() -> Path:
    return state_dir() / "ble-address"


def claude_credentials_dir() -> Path:
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        return Path(env)
    return Path.home() / ".claude"


def claude_credentials_file() -> Path:
    return claude_credentials_dir() / ".credentials.json"


def codex_home_dir() -> Path:
    env = os.environ.get("CODEX_HOME")
    if env:
        return Path(env)
    return Path.home() / ".codex"


def codex_auth_file() -> Path:
    return codex_home_dir() / "auth.json"


def codex_config_file() -> Path:
    return codex_home_dir() / "config.toml"
