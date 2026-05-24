"""Secret storage for provider API keys.

The daemon runs under launchd/systemd, neither of which inherits the user's
shell environment. So a `LANGDOCK_API_KEY` exported in `~/.zshrc` is invisible
to the polling loop. To keep things simple and cross-platform we store secrets
in a `KEY=value` file at `~/.config/clawdmeter/secrets.env` (0600), and load
them into `os.environ` once at startup. Shell-exported values still win — we
never overwrite an env var that's already set.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import paths


def _parse_line(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if "=" not in line:
        return None
    key, _, value = line.partition("=")
    key = key.strip()
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        value = value[1:-1]
    if not key:
        return None
    return key, value


def load_into_env() -> int:
    """Load `secrets.env` into `os.environ`. Returns count loaded.

    Does NOT overwrite vars that are already set — shell-exported values win.
    """
    path = paths.secrets_file()
    if not path.exists():
        return 0
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"[secrets] Failed to read {path}: {e}", file=sys.stderr)
        return 0
    count = 0
    for line in text.splitlines():
        parsed = _parse_line(line)
        if not parsed:
            continue
        key, value = parsed
        if key in os.environ:
            continue
        os.environ[key] = value
        count += 1
    return count


def read_all() -> dict[str, str]:
    """Return the contents of `secrets.env` as a dict (no env merging)."""
    path = paths.secrets_file()
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    out: dict[str, str] = {}
    for line in text.splitlines():
        parsed = _parse_line(line)
        if parsed:
            out[parsed[0]] = parsed[1]
    return out


def write(key: str, value: str) -> Path:
    """Persist `key=value` to `secrets.env`, preserving other entries.

    Creates the file with mode 0600 if it doesn't exist; on every write we
    re-apply the mode in case it drifted (e.g. someone edited via an editor
    that resets perms). An empty value removes the entry.
    """
    path = paths.secrets_file()
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = read_all()
    if value:
        existing[key] = value
    else:
        existing.pop(key, None)

    lines = ["# Clawdmeter secrets — KEY=value per line, loaded into env at daemon start.",
             "# Managed by the setup wizard; safe to edit by hand."]
    for k, v in existing.items():
        lines.append(f"{k}={v}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        # Windows: chmod is best-effort; the file lives under %APPDATA% which
        # is already per-user.
        pass
    return path


def describe_source(key: str) -> str:
    """Return a short human-readable description of where `key` will come from.

    Used by the wizard to tell the user whether a key is already configured,
    and from which source.
    """
    if os.environ.get(key):
        return "Shell-Env"
    stored = read_all()
    if stored.get(key):
        return f"{paths.secrets_file()}"
    return ""


def has_key(key: str) -> bool:
    if os.environ.get(key):
        return True
    return bool(read_all().get(key))


def mask(value: str) -> str:
    """Return a masked preview of a secret for logging/UI."""
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}…{value[-4:]}"
