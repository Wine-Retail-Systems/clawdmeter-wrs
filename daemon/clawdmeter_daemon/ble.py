"""BLE session — scan, connect, multi-provider send, end-of-cycle marker.

The transport is identical to the original single-provider daemon — same
service UUID, same RX/REQ characteristics. What changed:

- Each polling cycle writes N+1 JSON payloads sequentially (one per active
  provider, then `{"end":1}` as the cycle marker so the firmware knows the
  snapshot is complete and can drop stale providers).
- A small `interval_ms` delay between writes keeps NimBLE from coalescing
  notifications and dropping payloads.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Optional

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

from . import paths
from .config import Config

SERVICE_UUID = "4c41555a-4465-7669-6365-000000000001"
RX_CHAR_UUID = "4c41555a-4465-7669-6365-000000000002"
REQ_CHAR_UUID = "4c41555a-4465-7669-6365-000000000004"

# Spacing between sequential payload writes inside one cycle. NimBLE on the
# ESP32 will drop fast back-to-back writes without an ack — 80 ms is enough
# to let the firmware reset data_ready between payloads.
INTER_WRITE_DELAY_S = 0.08


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_cached_address() -> Optional[str]:
    f = paths.address_cache_file()
    if not f.exists():
        return None
    addr = f.read_text().strip()
    mac = re.fullmatch(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", addr)
    uuid_ = re.fullmatch(r"[0-9A-Fa-f]{8}-(?:[0-9A-Fa-f]{4}-){3}[0-9A-Fa-f]{12}", addr)
    if mac or uuid_:
        return addr
    log("Cached BLE address malformed, discarding")
    f.unlink(missing_ok=True)
    return None


def save_address(addr: str) -> None:
    f = paths.address_cache_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(addr)


def invalidate_address() -> None:
    paths.address_cache_file().unlink(missing_ok=True)


async def scan_for_device(cfg: Config) -> Optional[str]:
    log(f"Scanning for '{cfg.device.name}' ({cfg.device.scan_timeout_seconds}s)...")
    devices = await BleakScanner.discover(timeout=cfg.device.scan_timeout_seconds)
    for d in devices:
        if d.name == cfg.device.name:
            log(f"Found: {d.address}")
            return d.address
    return None


class Session:
    """Holds the connected BleakClient and exposes the per-cycle send API."""

    def __init__(self, client: BleakClient) -> None:
        self.client = client
        self.refresh_requested = asyncio.Event()

    def _on_refresh(self, _char, _data: bytearray) -> None:
        log("Refresh requested by device")
        self.refresh_requested.set()

    async def setup_refresh_subscription(self) -> None:
        try:
            await self.client.start_notify(REQ_CHAR_UUID, self._on_refresh)
        except (BleakError, ValueError) as e:
            log(f"Refresh subscription unavailable: {e}")

    async def write_payload(self, payload: dict) -> bool:
        data = json.dumps(payload, separators=(",", ":")).encode()
        try:
            await self.client.write_gatt_char(RX_CHAR_UUID, data, response=False)
            return True
        except BleakError as e:
            log(f"Write failed: {e}")
            return False

    async def send_cycle(self, payloads: list[dict]) -> bool:
        """Write a complete polling cycle: payloads + end-of-cycle marker."""
        for p in payloads:
            log(f"→ {json.dumps(p, separators=(',', ':'))}")
            if not await self.write_payload(p):
                return False
            await asyncio.sleep(INTER_WRITE_DELAY_S)
        return await self.write_payload({"end": 1})
