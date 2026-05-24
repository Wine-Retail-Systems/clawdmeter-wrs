"""Anthropic Claude adapter — polls api.anthropic.com rate-limit headers.

Migrated 1:1 from the original single-provider daemon. The minimal-cost trick
remains: one Haiku token call returns the rate-limit headers without spending
meaningful quota. Pace is derived from the actual-vs-expected ratio against
the active window; regen is computed from the difference between consecutive
polls of the 5h-utilization.
"""

from __future__ import annotations

import getpass
import json
import re
import subprocess
import sys
import time
from typing import Optional

import httpx

from .. import paths
from ..config import ProviderConfig
from . import register
from .base import KIND_PCT_WINDOW, ProviderBase, Snapshot

KEYCHAIN_SERVICE = "Claude Code-credentials"

API_URL = "https://api.anthropic.com/v1/messages"
API_HEADERS = {
    "anthropic-version": "2023-06-01",
    "anthropic-beta": "oauth-2025-04-20",
    "Content-Type": "application/json",
    "User-Agent": "claude-code/2.1.5",
}
API_BODY = {
    "model": "claude-haiku-4-5-20251001",
    "max_tokens": 1,
    "messages": [{"role": "user", "content": "hi"}],
}


def _extract_access_token(blob: str) -> Optional[str]:
    blob = blob.strip()
    if not blob:
        return None
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        if isinstance(data.get("accessToken"), str):
            return data["accessToken"]
        for v in data.values():
            if isinstance(v, dict) and isinstance(v.get("accessToken"), str):
                return v["accessToken"]
    m = re.search(r'"accessToken"\s*:\s*"([^"]+)"', blob)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_\-.~+/=]{20,}", blob):
        return blob
    return None


def _read_token_keychain() -> Optional[str]:
    try:
        out = subprocess.run(
            [
                "security", "find-generic-password",
                "-s", KEYCHAIN_SERVICE,
                "-a", getpass.getuser(),
                "-w",
            ],
            check=True, capture_output=True, text=True, timeout=10,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return _extract_access_token(out.stdout)


def _read_token_file() -> Optional[str]:
    try:
        raw = paths.claude_credentials_file().read_text(encoding="utf-8")
    except OSError:
        return None
    return _extract_access_token(raw)


def read_token() -> Optional[str]:
    if sys.platform == "darwin":
        tok = _read_token_keychain()
        if tok:
            return tok
    return _read_token_file()


class AnthropicProvider(ProviderBase):
    id = "anthropic"

    def __init__(self, cfg: ProviderConfig):
        super().__init__(cfg)
        # Rolling state for pace + regen estimation
        self._last_session_pct: Optional[float] = None
        self._last_session_seen_at: Optional[float] = None
        self._last_session_reset_at: Optional[float] = None  # absolute ts of next reset
        self._session_window_seconds: int = 5 * 3600  # 5h window

    async def poll(self) -> Optional[Snapshot]:
        token = read_token()
        if not token:
            self.log("No token (Keychain/file empty) — skipping poll")
            return None

        headers = dict(API_HEADERS)
        headers["Authorization"] = f"Bearer {token}"
        try:
            async with httpx.AsyncClient(timeout=20.0) as http:
                resp = await http.post(API_URL, headers=headers, json=API_BODY)
        except httpx.HTTPError as e:
            self.log(f"API call failed: {e}")
            return None

        if resp.status_code >= 400:
            self.log(f"API HTTP {resp.status_code}: {resp.text[:200]}")
            return None

        now = time.time()

        def hdr(name: str, default: str = "0") -> str:
            return resp.headers.get(name, default)

        def reset_seconds(ts: str) -> int:
            try:
                r = float(ts)
            except ValueError:
                return 0
            delta = r - now
            return int(round(delta)) if delta > 0 else 0

        def pct(util: str) -> float:
            try:
                return float(util) * 100.0
            except ValueError:
                return 0.0

        session_pct = pct(hdr("anthropic-ratelimit-unified-5h-utilization"))
        weekly_pct = pct(hdr("anthropic-ratelimit-unified-7d-utilization"))
        session_reset_s = reset_seconds(hdr("anthropic-ratelimit-unified-5h-reset"))
        weekly_reset_s = reset_seconds(hdr("anthropic-ratelimit-unified-7d-reset"))
        status = hdr("anthropic-ratelimit-unified-5h-status", "ok")

        pace = self._estimate_pace(session_pct, session_reset_s)
        regen = self._estimate_regen(session_pct)

        return Snapshot(
            slot_id=self.slot_id,
            display_name=self.cfg.display_name or "Claude",
            note=self.cfg.display_note,
            kind=KIND_PCT_WINDOW,
            m1=session_pct,
            m2=weekly_pct,
            r1=session_reset_s,
            r2=weekly_reset_s,
            status=status[:15],
            pace=pace,
            regen=regen,
            ok=True,
        )

    def _estimate_pace(self, session_pct: float, reset_s: int) -> Optional[int]:
        """Map (actual % consumed) vs (expected % at this point in the window) to -3..+3.

        Expected = (window_elapsed / window_total). If you're at 80% with 50%
        elapsed, you're burning much hotter than expected — pace = +3.
        """
        if reset_s <= 0:
            return None
        elapsed = self._session_window_seconds - reset_s
        if elapsed <= 0:
            return 0
        expected_pct = (elapsed / self._session_window_seconds) * 100.0
        delta = session_pct - expected_pct
        if delta <= -25:
            return -3
        if delta <= -15:
            return -2
        if delta <= -5:
            return -1
        if delta < 5:
            return 0
        if delta < 15:
            return 1
        if delta < 25:
            return 2
        return 3

    def _estimate_regen(self, session_pct: float) -> Optional[float]:
        """Rough %/min regen estimate from the delta between consecutive polls.

        Anthropic doesn't publish a regen rate header; we infer it by sampling
        the utilization across consecutive successful polls. Resets to None
        when no prior sample exists or the window just rolled over.
        """
        now = time.time()
        prev_pct = self._last_session_pct
        prev_t = self._last_session_seen_at
        self._last_session_pct = session_pct
        self._last_session_seen_at = now

        if prev_pct is None or prev_t is None:
            return None
        dt_min = (now - prev_t) / 60.0
        if dt_min < 0.5:  # too short to be meaningful
            return None
        # Regen is the rate at which utilization *decreases* (= tokens freed
        # per minute relative to the window). We only report positive numbers
        # — if the user is burning faster than regen, pace will catch it.
        drop_pct_per_min = (prev_pct - session_pct) / dt_min
        if drop_pct_per_min <= 0:
            return 0.0
        return drop_pct_per_min


register("anthropic", AnthropicProvider)
