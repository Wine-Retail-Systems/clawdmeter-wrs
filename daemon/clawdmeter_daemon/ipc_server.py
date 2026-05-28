"""IPC-Server für die Companion-App.

Bidirektionales JSON-Lines-Protokoll über Unix-Socket (macOS / Linux) bzw.
Named-Pipe (Windows). Wird gemeinsam mit dem Polling-Loop gestartet und
beendet sich sauber beim ``stop_event``.

Protokoll-Spezifikation: ``feature-documentation/companion-app/ipc-protocol.md``.

Kurzfassung:

* Request:  ``{"id": "<uuid>", "command": "<name>", "args": {...}}\\n``
* Response: ``{"id": "<uuid>", "ok": true,  "result": {...}}\\n``
*           ``{"id": "<uuid>", "ok": false, "error": "..."}\\n``
* Event:    ``{"event": "<name>", "data": {...}}\\n`` (unsolicited)

Aktuell unterstützte Commands:

* ``status``           — Daemon-Status + zuletzt gepollte Provider
* ``reload-config``    — config.toml neu einlesen
* ``trigger-poll``     — sofortige Vollpoll-Runde erzwingen
* ``shutdown``         — Daemon stoppen
* ``provider-detect``  — Auto-Detect-Hinweise pro Provider
* ``provider-save``    — Provider-Eintrag in config.toml schreiben
* ``secret-write``     — Wert in secrets.env persistieren (für API-Keys)
* ``list-providers``   — alle aktuell konfigurierten Provider
* ``subscribe-events`` — diese Verbindung erhält künftige Events
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from . import paths


SOCKET_NAME_MAC = "daemon.sock"
PIPE_NAME_WIN = r"\\.\pipe\clawdmeter-daemon"


def socket_path() -> Path:
    """Plattformabhängiger Pfad für den IPC-Endpunkt."""
    if sys.platform == "win32":
        return Path(PIPE_NAME_WIN)
    base = (
        Path.home() / "Library/Application Support" / "clawdmeter"
        if sys.platform == "darwin"
        else paths.state_dir()
    )
    base.mkdir(parents=True, exist_ok=True)
    return base / SOCKET_NAME_MAC


# ---------- Server-State ----------


@dataclass
class ServerState:
    """Hält Referenzen, die einzelne Command-Handler brauchen."""

    stop_event: asyncio.Event
    refresh_event: asyncio.Event
    reload_event: asyncio.Event
    # Provider-States werden vom polling-Loop gepflegt — als Liste, damit
    # `reload-config` sie austauschen kann. Tuple-Wrapper, damit replace
    # atomar bleibt.
    provider_states_ref: list = field(default_factory=list)
    # Subscriber-Liste für Push-Events (StreamWriter).
    subscribers: list = field(default_factory=list)


# ---------- Command-Handler ----------


CommandHandler = Callable[[ServerState, dict[str, Any]], Awaitable[Any]]
HANDLERS: dict[str, CommandHandler] = {}


def command(name: str) -> Callable[[CommandHandler], CommandHandler]:
    def deco(fn: CommandHandler) -> CommandHandler:
        HANDLERS[name] = fn
        return fn

    return deco


@command("status")
async def _status(state: ServerState, _args: dict[str, Any]) -> dict[str, Any]:
    states = state.provider_states_ref
    enabled = [s.provider.slot_id for s in states]
    last_polls = [
        s.last_snapshot.to_payload() if s.last_snapshot else None for s in states
    ]
    return {
        "reachable": True,
        "running": not state.stop_event.is_set(),
        "device_connected": False,  # wird vom Polling-Loop via Event aktualisiert
        "last_poll_at": None,
        "active_provider": enabled[0] if enabled else None,
        "providers": enabled,
        "snapshots": last_polls,
        "message": None,
    }


@command("reload-config")
async def _reload(state: ServerState, _args: dict[str, Any]) -> dict[str, Any]:
    state.reload_event.set()
    return {"requested": True}


@command("trigger-poll")
async def _trigger(state: ServerState, _args: dict[str, Any]) -> dict[str, Any]:
    state.refresh_event.set()
    return {"requested": True}


@command("shutdown")
async def _shutdown(state: ServerState, _args: dict[str, Any]) -> dict[str, Any]:
    state.stop_event.set()
    return {"stopping": True}


@command("provider-detect")
async def _provider_detect(
    _state: ServerState, args: dict[str, Any]
) -> dict[str, Any]:
    from . import setup_wizard

    pid = args.get("id", "")
    if pid == "anthropic":
        src = setup_wizard.detect_claude_token()
        return _detect_result(pid, src)
    if pid == "codex":
        src = setup_wizard.detect_codex_token()
        return _detect_result(pid, src)
    if pid == "langdock":
        env = args.get("env", "LANGDOCK_API_KEY")
        src = setup_wizard.detect_langdock_key(env)
        return _detect_result(pid, src)
    if pid == "opencode":
        db = setup_wizard.detect_opencode_db()
        ver = setup_wizard.detect_opencode_version()
        notes = f"CLI: {ver}" if ver else None
        return _detect_result(pid, db, notes=notes)
    if pid == "bedrock":
        ok, where = setup_wizard.detect_aws()
        return _detect_result(pid, where if ok else "")
    return {
        "id": pid,
        "detected": False,
        "source": None,
        "notes": f"Unbekannte Provider-ID: {pid!r}",
    }


def _detect_result(pid: str, source: str, *, notes: str | None = None) -> dict[str, Any]:
    return {
        "id": pid,
        "detected": bool(source),
        "source": source or None,
        "notes": notes,
    }


@command("provider-save")
async def _provider_save(
    state: ServerState, args: dict[str, Any]
) -> dict[str, Any]:
    """Headless-Variante des Setup-Wizards.

    Args:
        id      — provider-Kind (anthropic/codex/langdock/opencode/bedrock)
        fields  — Flat-Dict mit den Werten, die im Provider-Block landen
                  (enabled, poll_seconds, slot_id, display_name, …).
                  Wir mergen sie in den bestehenden Block oder legen einen
                  neuen an.

    Side-effect: löst nach dem Schreiben einen `reload-config` aus, damit
    der Polling-Loop die Änderung direkt sieht.
    """
    from . import config as cfg_mod
    from . import paths as paths_mod

    pid = args.get("id", "")
    fields = args.get("fields") or {}
    if pid not in ("anthropic", "codex", "langdock", "opencode", "bedrock"):
        return {"saved": False, "reason": f"Unbekannte Provider-ID: {pid!r}"}

    # config einlesen — wir nutzen tomllib statt load_config, weil wir die
    # Roh-Tabelle brauchen (nicht den Config-Dataclass).
    try:
        import tomllib  # type: ignore[attr-defined]
    except ModuleNotFoundError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ModuleNotFoundError:
            return {"saved": False, "reason": "tomllib/tomli fehlt"}

    cfg_path = paths_mod.config_file()
    if cfg_path.exists():
        with open(cfg_path, "rb") as fh:
            data = tomllib.load(fh)
    else:
        data = {}
    if "device" not in data:
        data["device"] = {"name": "Clawdmeter", "scan_timeout_seconds": 8.0}
    blocks = list(data.get("provider") or [])

    slot_id = fields.get("slot_id") or pid
    block = next(
        (
            dict(b)
            for b in blocks
            if b.get("id") == pid and b.get("slot_id", pid) == slot_id
        ),
        {"id": pid, "slot_id": slot_id},
    )
    block.update({k: v for k, v in fields.items() if v is not None})
    block.setdefault("id", pid)
    # Provider-Save kommt aus dem Setup-Wizard — Default-Configs liefern den
    # Block mit ``enabled = false``. ``setdefault`` würde das nicht überschreiben,
    # also forcieren wir den Wert. Wer bewusst deaktivieren will, übergibt
    # ``enabled = False`` explizit in ``fields``.
    block["enabled"] = fields.get("enabled", True)

    blocks = [
        b
        for b in blocks
        if not (b.get("id") == pid and b.get("slot_id", pid) == slot_id)
    ]
    blocks.append(block)
    data["provider"] = blocks

    written = cfg_mod.write_config_dict(data)
    state.reload_event.set()
    return {"saved": True, "path": str(written)}


@command("secret-write")
async def _secret_write(
    state: ServerState, args: dict[str, Any]
) -> dict[str, Any]:
    """Persistiert einen API-Key/Secret in ``secrets.env``.

    Args:
        key   — Env-Var-Name (z. B. ``LANGDOCK_API_KEY``)
        value — Klartext-Wert; leer = Eintrag löschen.

    Side-effects:
      * Schreibt ``~/.config/clawdmeter/secrets.env`` (chmod 600).
      * Setzt zusätzlich ``os.environ[key]``, damit der laufende
        Daemon-Prozess den Wert sofort sieht (sonst greift er erst nach
        einem Neustart).
      * Triggert ``reload-config``, damit der Polling-Loop den Provider
        bei nächster Chance frisch initialisiert.
    """
    from . import secrets as secrets_mod

    key = str(args.get("key") or "").strip()
    value = str(args.get("value") or "")
    if not key:
        return {"saved": False, "reason": "key fehlt"}

    try:
        path = secrets_mod.write(key, value)
    except OSError as e:
        return {"saved": False, "reason": f"secrets.env nicht schreibbar: {e}"}

    # In-Process-Env aktualisieren, sonst sieht der Polling-Loop den neuen
    # Wert erst nach Daemon-Restart (load_into_env läuft nur beim Start).
    if value:
        os.environ[key] = value
    else:
        os.environ.pop(key, None)

    state.reload_event.set()
    return {"saved": True, "path": str(path), "masked": secrets_mod.mask(value)}


@command("list-providers")
async def _list_providers(
    state: ServerState, _args: dict[str, Any]
) -> dict[str, Any]:
    return {
        "providers": [
            {
                "slot_id": s.provider.slot_id,
                "kind": s.provider.id,
                "poll_seconds": s.provider.poll_seconds,
            }
            for s in state.provider_states_ref
        ]
    }


@command("subscribe-events")
async def _subscribe(state: ServerState, args: dict[str, Any]) -> dict[str, Any]:
    # Magic: die laufende Connection wird zum Subscriber befördert. Den
    # konkreten Writer übergibt der ``handle_connection``-Wrapper über
    # ``args['__writer__']``.
    writer = args.get("__writer__")
    if writer is not None and writer not in state.subscribers:
        state.subscribers.append(writer)
    return {"subscribed": True}


# ---------- Server-Implementation ----------


async def _broadcast(state: ServerState, event: str, data: dict[str, Any]) -> None:
    frame = (json.dumps({"event": event, "data": data}) + "\n").encode()
    dead: list[Any] = []
    for w in state.subscribers:
        try:
            w.write(frame)
            await w.drain()
        except (ConnectionError, OSError):
            dead.append(w)
    for w in dead:
        state.subscribers.remove(w)


async def emit_event(state: ServerState, event: str, data: dict[str, Any]) -> None:
    """Vom polling-Loop aufgerufen, um Subscriber zu benachrichtigen."""
    await _broadcast(state, event, data)


async def _handle_request(
    state: ServerState, writer: asyncio.StreamWriter, raw: bytes
) -> None:
    try:
        msg = json.loads(raw)
    except ValueError as e:
        out = {"id": None, "ok": False, "error": f"invalid JSON: {e}"}
        writer.write((json.dumps(out) + "\n").encode())
        await writer.drain()
        return

    req_id = msg.get("id")
    cmd = msg.get("command") or ""
    args = msg.get("args") or {}
    if cmd == "subscribe-events":
        args["__writer__"] = writer

    handler = HANDLERS.get(cmd)
    if handler is None:
        out = {"id": req_id, "ok": False, "error": f"unknown command: {cmd!r}"}
    else:
        try:
            result = await handler(state, args)
            out = {"id": req_id, "ok": True, "result": result}
        except Exception as exc:  # noqa: BLE001
            out = {"id": req_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"}

    writer.write((json.dumps(out) + "\n").encode())
    await writer.drain()


async def _connection(
    state: ServerState,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    try:
        while not state.stop_event.is_set():
            line = await reader.readline()
            if not line:
                break
            await _handle_request(state, writer, line)
    except (ConnectionError, asyncio.IncompleteReadError):
        pass
    finally:
        if writer in state.subscribers:
            state.subscribers.remove(writer)
        try:
            writer.close()
            await writer.wait_closed()
        except (ConnectionError, OSError):
            pass


async def _serve_unix(state: ServerState, path: Path) -> asyncio.AbstractServer:
    if path.exists():
        path.unlink()
    server = await asyncio.start_unix_server(
        lambda r, w: _connection(state, r, w), path=str(path)
    )
    os.chmod(path, 0o600)
    return server


async def _serve_windows_pipe(state: ServerState) -> Optional[asyncio.AbstractServer]:
    # asyncio.start_server liefert TCP — für Named-Pipes brauchen wir
    # ProactorEventLoop + create_pipe_connection. Das implementieren wir
    # in einem expliziten Folgeschritt; vorerst loggen wir den Fallback.
    # Die Rust-Seite verbindet sich gegen denselben Pipe-Namen.
    print(
        "[ipc] Windows-Named-Pipe-Server: Implementierung folgt — Fallback auf "
        "lokalen TCP-Port wäre unsicher.",
        file=sys.stderr,
    )
    _ = state
    return None


async def start(state: ServerState) -> Optional[asyncio.AbstractServer]:
    """Startet den IPC-Server. Gibt das ``Server``-Objekt zurück, damit der
    Caller es beim Shutdown sauber schließen kann."""
    path = socket_path()
    print(f"[ipc] listening on {path}", file=sys.stderr)
    if sys.platform == "win32":
        return await _serve_windows_pipe(state)
    return await _serve_unix(state, path)


async def stop(server: Optional[asyncio.AbstractServer]) -> None:
    if server is None:
        return
    server.close()
    try:
        await server.wait_closed()
    except OSError:
        pass
    path = socket_path()
    if sys.platform != "win32" and path.exists():
        try:
            path.unlink()
        except OSError:
            pass
