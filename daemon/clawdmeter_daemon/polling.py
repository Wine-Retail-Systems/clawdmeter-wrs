"""Daemon main loop.

For each connected BLE session, we maintain a list of (provider, next_poll_at)
tuples. The loop wakes every TICK seconds, polls any provider whose deadline
has passed, and dispatches a single multi-provider cycle to the firmware. A
refresh request from the device forces an immediate full cycle of every
enabled provider regardless of its individual cadence.
"""

from __future__ import annotations

import asyncio
import signal
import sys
import time
from typing import Optional

from bleak import BleakClient
from bleak.exc import BleakError

from . import ble, paths, secrets
from .config import Config, load_config
from .providers import Provider, Snapshot, create

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
                f"expected one of {sorted(['anthropic', 'codex', 'langdock', 'opencode', 'bedrock'])}",
                file=sys.stderr,
            )
            continue
        states.append(ProviderState(provider))
    return states


def correlate_backend_quota(states: list[ProviderState]) -> None:
    """For OpenCode entries with include_backend_quota=true, copy m1 (utilization
    %) from the matching backend provider into m2 of the OpenCode snapshot."""
    by_kind = {s.provider.id: s for s in states}
    for s in states:
        snap = s.last_snapshot
        if not snap or snap.kind != "tokens_abs":
            continue
        if not snap.extra.get("include_backend_quota"):
            continue
        backend_id = snap.extra.get("active_provider") or ""
        # OpenCode uses "amazon-bedrock", "anthropic", "openai", "openrouter",
        # "ollama". We map "amazon-bedrock" → "bedrock" for our adapter id.
        clawd_id = "bedrock" if backend_id == "amazon-bedrock" else backend_id
        backend = by_kind.get(clawd_id)
        if backend and backend.last_snapshot:
            # Take whichever metric the backend exposes as "primary load".
            snap.m2 = float(backend.last_snapshot.m1)


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

    correlate_backend_quota(states)
    payloads = [s.last_snapshot.to_payload() for s in states if s.last_snapshot]
    if not payloads:
        return True
    return await session.send_cycle(payloads)


async def connect_and_run(address: str, cfg: Config, states: list[ProviderState],
                          stop_event: asyncio.Event) -> bool:
    ble.log(f"Connecting to {address}...")
    client = BleakClient(address)
    try:
        await client.connect()
    except (BleakError, asyncio.TimeoutError) as e:
        ble.log(f"Connection failed: {e}")
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
            if await run_cycle(session, states, force_all=force):
                used_successfully = True
            force = False
            if session.refresh_requested.is_set():
                session.refresh_requested.clear()
                force = True
                continue
            try:
                await asyncio.wait_for(session.refresh_requested.wait(), timeout=TICK)
            except asyncio.TimeoutError:
                pass
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
    loop = asyncio.get_running_loop()

    def _stop(*_args: object) -> None:
        ble.log("Daemon stopping")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            signal.signal(sig, _stop)

    backoff = 1
    while not stop_event.is_set():
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

        ok = await connect_and_run(address, cfg, states, stop_event)
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


def run() -> None:
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        sys.exit(0)
