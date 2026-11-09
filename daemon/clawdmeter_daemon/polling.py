"""Daemon main loop.

For each connected BLE session, we maintain a list of (provider, next_poll_at)
tuples. The loop wakes every TICK seconds, polls any provider whose deadline
has passed, and dispatches a single multi-provider cycle to the firmware. A
refresh request from the device forces an immediate full cycle of every
enabled provider regardless of its individual cadence.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import threading
import time
from typing import Optional

from bleak import BleakClient
from bleak.exc import BleakError

from . import ble, ipc_server, paths, secrets
from .config import Config, load_config
from .providers import Provider, Snapshot, create, known_provider_ids

TICK = 5.0


class ProviderState:
    def __init__(self, provider: Provider) -> None:
        self.provider = provider
        self.next_poll_at = 0.0
        self.last_snapshot: Optional[Snapshot] = None

    def is_due(self, now: float) -> bool:
        return now >= self.next_poll_at

    def schedule(self, ok: bool) -> None:
        # On failure we still wait one full poll cycle — failing every TICK
        # would hammer rate-limited APIs.
        self.next_poll_at = time.time() + self.provider.poll_seconds


def build_provider_states(cfg: Config) -> list[ProviderState]:
    states: list[ProviderState] = []
    for pcfg in cfg.enabled_providers:
        provider = create(pcfg)
        if provider is None:
            print(
                f"[startup] Unknown provider id: {pcfg.id!r} — "
                f"expected one of {known_provider_ids()}",
                file=sys.stderr,
            )
            continue
        states.append(ProviderState(provider))
    return states


async def run_cycle(session: ble.Session, states: list[ProviderState], force_all: bool) -> bool:
    now = time.time()
    polled_any = False
    for s in states:
        if not (force_all or s.is_due(now)):
            continue
        try:
            snap = await s.provider.poll()
        except Exception as e:  # noqa: BLE001
            print(f"[poll] {s.provider.slot_id} crashed: {e}", file=sys.stderr)
            snap = None
        if snap is not None:
            s.last_snapshot = snap
        s.schedule(ok=snap is not None)
        polled_any = True

    if not polled_any:
        return True  # no work to do this tick

    payloads = [s.last_snapshot.to_payload() for s in states if s.last_snapshot]
    if not payloads:
        return True
    return await session.send_cycle(payloads)


async def _wait_any_event(events: list[asyncio.Event], timeout: float) -> None:
    """Wartet, bis irgendein Event feuert oder ``timeout`` abläuft.

    Anders als ``asyncio.wait_for(event.wait(), ...)`` lässt sich hier auf
    mehrere Events parallel warten, ohne dass sie nacheinander gepollt werden
    müssten. Wir verzichten bewusst auf einen Rückgabewert: der Aufrufer
    inspiziert ``event.is_set()`` selbst, weil mehrere Events gleichzeitig
    feuern können.
    """

    tasks = [asyncio.create_task(e.wait()) for e in events]
    try:
        await asyncio.wait(
            tasks, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


# Obergrenze für einen BLE-Verbindungsaufbau. CoreBluetooth kann nach dem
# Ruhezustand ``connect()`` unbegrenzt hängen lassen, trotz bleak-Timeout.
CONNECT_TIMEOUT = 30.0
# Nach einem Stop-Signal bleibt so viel Zeit für ein sauberes Ende; danach
# beendet sich der Prozess hart. Liegt unter dem launchd-ExitTimeOut (20 s).
SHUTDOWN_GRACE = 10.0
PARENT_CHECK_INTERVAL = 5.0


async def _connect_or_stop(client, stop_event: asyncio.Event, timeout: float) -> bool:
    """``client.connect()`` mit hartem Timeout, abbrechbar über ``stop_event``.

    True: verbunden. False: ``stop_event`` kam dazwischen.
    Wirft ``asyncio.TimeoutError`` nach ``timeout`` und reicht Fehler von
    ``connect()`` (z. B. ``BleakError``) durch.
    """
    connect_task = asyncio.ensure_future(client.connect())
    stop_task = asyncio.ensure_future(stop_event.wait())
    try:
        done, _ = await asyncio.wait(
            {connect_task, stop_task},
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        stop_task.cancel()
    if connect_task in done:
        connect_task.result()
        return True
    connect_task.cancel()
    # Nicht unbegrenzt auf das Abbrechen warten — genau das hängt ja.
    await asyncio.wait({connect_task}, timeout=1.0)
    if stop_event.is_set():
        return False
    raise asyncio.TimeoutError(f"BLE connect nach {timeout:.0f}s ohne Antwort")


async def _watch_parent(
    stop_event: asyncio.Event,
    initial_ppid: int,
    getppid=os.getppid,
    interval: float = PARENT_CHECK_INTERVAL,
) -> None:
    """Setzt ``stop_event``, sobald der Elternprozess wechselt.

    Im PyInstaller-onefile-Build ist der Elternprozess der Bootloader. Stirbt
    er (z. B. SIGKILL durch launchd), würde dieser Prozess als Waise weiterlaufen
    und den IPC-Socket blockieren.
    """
    while not stop_event.is_set():
        if getppid() != initial_ppid:
            ble.log("Elternprozess beendet — Daemon stoppt")
            stop_event.set()
            return
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


def _start_shutdown_deadline(seconds: float, exit_fn=os._exit) -> threading.Timer:
    """Beendet den Prozess hart, falls der saubere Stop nicht rechtzeitig
    fertig wird. Läuft in einem eigenen Thread, damit ein hängender
    Event-Loop ihn nicht aufhalten kann."""
    timer = threading.Timer(seconds, exit_fn, args=(1,))
    timer.daemon = True
    timer.start()
    return timer


def _is_stale_pairing_error(exc: BaseException) -> bool:
    """CoreBluetooth Code 14 ("Peer removed pairing information") tritt auf,
    wenn das Gerät via Re-Flash sein NVS verloren hat, der Mac aber den
    alten Bond-Eintrag noch in Erinnerung hat. Wir matchen tolerant gegen
    den Nachrichtentext, weil bleak die Error-Codes nicht typed exposed."""
    msg = str(exc).lower()
    return (
        "code=14" in msg
        or "peer removed pairing" in msg
        or "pairing information" in msg
    )


async def connect_and_run(
    address: str,
    cfg: Config,
    states: list[ProviderState],
    stop_event: asyncio.Event,
    refresh_event: asyncio.Event,
    reload_event: asyncio.Event,
    ipc_state: "ipc_server.ServerState | None" = None,
) -> bool:
    ble.log(f"Connecting to {address}...")
    client = BleakClient(address)
    try:
        if not await _connect_or_stop(client, stop_event, CONNECT_TIMEOUT):
            return True  # Stop während des Verbindungsaufbaus — kein Fehler
    except (BleakError, asyncio.TimeoutError) as e:
        ble.log(f"Connection failed: {e}")
        if _is_stale_pairing_error(e):
            ble.log(
                "Hinweis: macOS hält einen veralteten Bond für dieses Gerät. "
                "Bluetooth-Modul zurücksetzen (Option+Shift+Klick auf das "
                "BT-Symbol → 'Bluetooth-Modul zurücksetzen') oder das Gerät "
                "in Systemeinstellungen → Bluetooth vergessen. Danach baut "
                "der Daemon das Bonding neu auf."
            )
            if ipc_state is not None:
                await ipc_server.emit_event(
                    ipc_state,
                    "device-pairing-stale",
                    {"address": address, "error": str(e)},
                )
        return False
    if not client.is_connected:
        ble.log("Connection failed (no error but not connected)")
        return False

    ble.log("Connected")
    session = ble.Session(client)
    await session.setup_refresh_subscription()

    used_successfully = False
    try:
        # Force a full cycle on connect so the firmware leaves the empty state.
        force = True
        while client.is_connected and not stop_event.is_set():
            # IPC-``reload-config`` / ``provider-save`` während aktiver BLE-Session:
            # main_loop besitzt den Reload-Pfad — wir trennen die Session, lassen
            # uns vom äußeren Loop reconnecten, und behalten den Address-Cache.
            if reload_event.is_set():
                ble.log("Reload requested — disconnecting to apply new config")
                used_successfully = True
                break
            if await run_cycle(session, states, force_all=force):
                used_successfully = True
            force = False
            if session.refresh_requested.is_set():
                session.refresh_requested.clear()
                force = True
                continue
            # IPC-``trigger-poll`` während aktiver BLE-Session: sofortiger Vollpoll.
            if refresh_event.is_set():
                refresh_event.clear()
                force = True
                continue
            await _wait_any_event(
                [
                    session.refresh_requested,
                    refresh_event,
                    reload_event,
                    stop_event,
                ],
                timeout=TICK,
            )
    finally:
        try:
            await client.disconnect()
        except BleakError:
            pass

    ble.log("Device disconnected" if not stop_event.is_set() else "Stopping")
    return used_successfully


async def main_loop() -> None:
    loaded = secrets.load_into_env()
    if loaded:
        ble.log(f"Loaded {loaded} secret(s) from {paths.secrets_file()}")

    cfg = load_config()

    enabled = cfg.enabled_providers
    if not enabled:
        ble.log(
            f"No providers enabled in {cfg.source_path}. "
            "Run `clawdmeter-daemon setup` to configure."
        )

    states = build_provider_states(cfg)

    ble.log(
        f"=== Clawdmeter daemon === {len(states)} provider(s): "
        + ", ".join(s.provider.slot_id for s in states)
    )
    ble.log(f"Config: {cfg.source_path}")
    ble.log(f"Address cache: {paths.address_cache_file()}")

    stop_event = asyncio.Event()
    refresh_event = asyncio.Event()
    reload_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _stop(*_args: object) -> None:
        ble.log("Daemon stopping")
        if not stop_event.is_set():
            _start_shutdown_deadline(SHUTDOWN_GRACE)
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            signal.signal(sig, _stop)

    ipc_state = ipc_server.ServerState(
        stop_event=stop_event,
        refresh_event=refresh_event,
        reload_event=reload_event,
        provider_states_ref=states,
    )
    ipc_srv = await ipc_server.start(ipc_state)

    # Nur überwachen, wenn ein echter Elternprozess existiert (onefile-
    # Bootloader). Direkt von launchd gestartet ist die PPID ohnehin 1.
    parent_watch: Optional[asyncio.Task] = None
    initial_ppid = os.getppid()
    if sys.platform != "win32" and initial_ppid != 1:
        parent_watch = asyncio.create_task(_watch_parent(stop_event, initial_ppid))

    backoff = 1
    while not stop_event.is_set():
        if reload_event.is_set():
            reload_event.clear()
            try:
                cfg = load_config()
                new_states = build_provider_states(cfg)
                states.clear()
                states.extend(new_states)
                ipc_state.provider_states_ref = states
                ble.log(f"Config neu geladen — {len(states)} Provider aktiv")
                await ipc_server.emit_event(
                    ipc_state, "config-changed", {"providers": len(states)}
                )
            except Exception as exc:  # noqa: BLE001
                ble.log(f"Reload-Fehler: {exc}")
        address = ble.load_cached_address()
        if not address:
            address = await ble.scan_for_device(cfg)
            if address:
                ble.save_address(address)
            else:
                ble.log(f"Device not found, retrying in {backoff}s...")
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=backoff)
                except asyncio.TimeoutError:
                    pass
                backoff = min(backoff * 2, 60)
                continue

        await ipc_server.emit_event(
            ipc_state, "device-connecting", {"address": address}
        )
        ok = await connect_and_run(
            address, cfg, states, stop_event, refresh_event, reload_event,
            ipc_state=ipc_state,
        )
        await ipc_server.emit_event(
            ipc_state, "device-disconnected", {"address": address, "clean": ok}
        )
        if not ok:
            ble.log("Invalidating cached address")
            ble.invalidate_address()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=backoff)
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, 60)
        else:
            backoff = 1

    if parent_watch is not None:
        parent_watch.cancel()
    await ipc_server.stop(ipc_srv)


def run() -> None:
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        sys.exit(0)
