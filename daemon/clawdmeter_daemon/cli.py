"""CLI entry point — `clawdmeter-daemon <subcommand>`.

Subcommands:
  run     — start the polling daemon (default if no subcommand given)
  setup   — interactive provider configuration wizard
  config  — print the active config path
  doctor  — show which providers are configured and what would be polled
"""

from __future__ import annotations

import sys

from . import paths, secrets
from .config import load_config


def cmd_run() -> int:
    from . import polling

    polling.run()
    return 0


def cmd_setup() -> int:
    from . import setup_wizard

    setup_wizard.run()
    return 0


def cmd_config() -> int:
    print(paths.config_file())
    return 0


def cmd_doctor() -> int:
    loaded = secrets.load_into_env()
    cfg = load_config()
    print(f"Config: {cfg.source_path}")
    print(f"Secrets: {paths.secrets_file()}  ({loaded} geladen)")
    print(f"Device: {cfg.device.name}  (scan {cfg.device.scan_timeout_seconds}s)")
    print(f"Adress-Cache: {paths.address_cache_file()}")
    enabled = cfg.enabled_providers
    print(f"\nEnabled providers ({len(enabled)}):")
    if not enabled:
        print("  (none — run `clawdmeter-daemon setup`)")
    for p in enabled:
        line = (f"  - {p.slot_id:18} kind={p.id:10} poll={p.poll_seconds}s  "
                f"name={p.display_name!r} note={p.display_note!r}")
        if p.id == "langdock":
            env_name = p.get("api_key_env", "LANGDOCK_API_KEY")
            src = secrets.describe_source(env_name)
            line += f"  key={src or 'FEHLT'}"
        print(line)
    return 0


def main() -> int:
    argv = sys.argv[1:]
    cmd = argv[0] if argv else "run"
    sys.argv = [sys.argv[0]] + argv[1:]
    if cmd in ("run", ""):
        return cmd_run()
    if cmd == "setup":
        return cmd_setup()
    if cmd == "config":
        return cmd_config()
    if cmd == "doctor":
        return cmd_doctor()
    if cmd in ("-h", "--help", "help"):
        print(__doc__ or "")
        return 0
    print(f"Unknown subcommand: {cmd!r}. Try: run | setup | config | doctor", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
