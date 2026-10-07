"""Bifrost adapter — budget usage of a virtual key at the WRS LLM gateway.

Endpoint: ``GET <base_url>/api/governance/virtual-keys/quota`` with
``Authorization: Bearer <virtual key>`` (self-service, no admin access).
Checked against Bifrost v2.2.5. Maps to a ``cost_budget`` snapshot (USD).

Never log the key: only the env var *name* and HTTP status codes appear in
log lines.
"""

from __future__ import annotations

import dataclasses
import math
import os
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from ..config import ProviderConfig
from . import _budget, register
from .base import KIND_COST_BUDGET, ProviderBase, Snapshot

DEFAULT_BASE_URL = "https://llm-gw.wineretailsystems.cloud"
DEFAULT_KEY_ENV = "BIFROST_VIRTUAL_KEY"
QUOTA_PATH = "/api/governance/virtual-keys/quota"
TIMEOUT_S = 15.0
FAMILIES = (("opus", "Opus"), ("sonnet", "Sonnet"), ("haiku", "Haiku"))


class StructureError(ValueError):
    pass


def quota_url(base_url: str) -> str:
    return (base_url or DEFAULT_BASE_URL).rstrip("/") + QUOTA_PATH


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    return f if math.isfinite(f) else None


def family_of(model: str) -> str:
    low = model.lower()
    for needle, label in FAMILIES:
        if needle in low:
            return label
    return "Andere"


def compute_shares(per_model_usage: Any) -> list[dict]:
    """Cost shares by model family: max 3 families + ``Rest``, sum = 100."""
    if not isinstance(per_model_usage, list):
        return []
    costs: dict[str, float] = {}
    for e in per_model_usage:
        if not isinstance(e, dict):
            continue
        cost = _num(e.get("total_cost"))
        if cost is None or cost <= 0:
            continue
        fam = family_of(str(e.get("model") or ""))
        costs[fam] = costs.get(fam, 0.0) + cost
    total = sum(costs.values())
    if total <= 0:
        return []
    pcts = sorted(((f, 100.0 * c / total) for f, c in costs.items()),
                  key=lambda x: -x[1])
    kept = [(f, p) for f, p in pcts if p >= 1.0][:3]
    rest = 100.0 - sum(p for _, p in kept)
    entries = [[f, int(math.floor(p + 0.5))] for f, p in kept]
    if int(math.floor(rest + 0.5)) > 0:
        entries.append(["Rest", int(math.floor(rest + 0.5))])
    entries = [e for e in entries if e[1] > 0]
    if not entries:
        return []
    diff = 100 - sum(e[1] for e in entries)
    if diff:
        max(entries, key=lambda e: e[1])[1] += diff
    return [{"slug": f, "pct": p} for f, p in entries]


def _key_note(name: Any) -> str:
    """``user-sascha.krinke@jacques.de`` -> ``sascha.krinke``."""
    if not isinstance(name, str):
        return ""
    s = name.strip()
    if s.startswith("user-"):
        s = s[5:]
    return s.split("@", 1)[0]


def pick_budget(budgets: list) -> Optional[dict]:
    """Budget with the smallest remaining amount (limit incl. override)."""
    best: Optional[tuple[float, dict, float, float]] = None
    for b in budgets:
        if not isinstance(b, dict):
            continue
        limit = _num(b.get("max_limit"))
        if limit is None:
            continue
        limit += _num(b.get("override_amount")) or 0.0
        used = _num(b.get("current_usage")) or 0.0
        rest = limit - used
        if best is None or rest < best[0]:
            best = (rest, b, used, limit)
    if best is None:
        return None
    return {"budget": best[1], "used": best[2], "limit": best[3]}


class BifrostProvider(ProviderBase):
    id = "bifrost"

    def __init__(self, cfg: ProviderConfig):
        super().__init__(cfg)
        self._last: Optional[Snapshot] = None
        self._last_reset_at: Optional[datetime] = None
        self._transport: Optional[httpx.AsyncBaseTransport] = None  # tests

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    @property
    def _key_env(self) -> str:
        return str(self.cfg.get("api_key_env", DEFAULT_KEY_ENV))

    async def poll(self) -> Optional[Snapshot]:
        key = os.environ.get(self._key_env)
        if not key:
            self.log(f"Virtual key env var {self._key_env} not set — skipping")
            return None
        url = quota_url(str(self.cfg.get("base_url", DEFAULT_BASE_URL)))
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_S, transport=self._transport) as http:
                resp = await http.get(url, headers={"Authorization": f"Bearer {key}"})
            if resp.status_code != 200:
                self.log(f"Quota request HTTP {resp.status_code} (key env {self._key_env})")
                return self._stale()
            snap = self._snapshot_from(resp.json(), self._now())
        except httpx.HTTPError as e:
            self.log(f"Quota request failed: {type(e).__name__}")
            return self._stale()
        except (ValueError, TypeError, AttributeError) as e:
            self.log(f"Unexpected quota response: {type(e).__name__}")
            return self._stale()
        self._last = snap
        return snap

    def _snapshot_from(self, data: Any, now: datetime) -> Snapshot:
        if not isinstance(data, dict):
            raise StructureError("root is not an object")
        budgets = data.get("budgets")
        if budgets is None:
            budgets = []
        if not isinstance(budgets, list):
            raise StructureError("budgets is not a list")

        note = _key_note(data.get("virtual_key_name"))
        m1 = m2 = 0.0
        r2 = 0
        pace = None
        status = "ok"
        shares: list[dict] = []
        reset_at: Optional[datetime] = None

        picked = pick_budget(budgets)
        if picked:
            b = picked["budget"]
            m1, m2 = picked["used"], picked["limit"]
            status = _budget.status_for(m1, m2)
            dur = _budget.parse_duration(b.get("reset_duration"))
            last = _budget.parse_iso(b.get("last_reset"))
            if dur and last:
                start, reset_at = _budget.current_window(last, dur, now)
                r2 = _budget.seconds_until(reset_at, now)
                pace = _budget.pace(m1, m2, start, reset_at, now)
            shares = compute_shares(b.get("per_model_usage"))
            src = b.get("source_name")
            if len(budgets) > 1 and isinstance(src, str) and src:
                note = f"{src} {note}".strip()
        note = (self.cfg.display_note or note)[:16]

        self._last_reset_at = reset_at
        return Snapshot(
            slot_id=self.slot_id,
            display_name=(self.cfg.get("display_name") or "LLM Gateway"),
            note=note,
            kind=KIND_COST_BUDGET,
            m1=m1, m2=m2, r1=0, r2=r2,
            status=status, pace=pace, currency="USD", ok=True,
            extra={"shares": shares} if shares else {},
        )

    def _stale(self) -> Snapshot:
        now = self._now()
        if self._last is not None:
            r2 = _budget.seconds_until(self._last_reset_at, now) if self._last_reset_at else self._last.r2
            return dataclasses.replace(self._last, status="stale", ok=False, r2=r2)
        return Snapshot(
            slot_id=self.slot_id,
            display_name=(self.cfg.get("display_name") or "LLM Gateway"),
            note=self.cfg.display_note[:16],
            kind=KIND_COST_BUDGET,
            status="stale", currency="USD", ok=False,
        )


def check_quota_sync(base_url: str, key: str) -> tuple[Optional[int], str]:
    """Used by `doctor`: returns (http_status or None, error class name)."""
    try:
        r = httpx.get(quota_url(base_url), headers={"Authorization": f"Bearer {key}"},
                      timeout=10.0)
        return r.status_code, ""
    except httpx.HTTPError as e:
        return None, type(e).__name__


register("bifrost", BifrostProvider)
