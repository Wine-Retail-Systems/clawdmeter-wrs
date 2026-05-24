"""Provider Protocol + normalized Snapshot model.

Snapshot maps 1:1 to the BLE payload (see firmware/src/main.cpp::parse_json).
A provider's poll() coroutine must produce one Snapshot per cycle (or None
when the source is temporarily unavailable — the firmware then shows the
last known value with a staleness hint).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

KIND_PCT_WINDOW = "pct_window"
KIND_COST_BUDGET = "cost_budget"
KIND_TOKENS_ABS = "tokens_abs"
KIND_TPM_RPM = "tpm_rpm"

ALL_KINDS = {KIND_PCT_WINDOW, KIND_COST_BUDGET, KIND_TOKENS_ABS, KIND_TPM_RPM}


@dataclass
class Snapshot:
    """One provider's poll result.

    The meaning of m1/m2/m3 and r1/r2 depends on `kind`:
      pct_window  → m1=short %, m2=long %, r1/r2=resets (s)
      cost_budget → m1=spent (currency), m2=budget (0=no budget), r2=sec to month end
      tokens_abs  → m1=tokens today, m2=optional backend quota %, m3=yesterday compare, r2=sec to midnight
      tpm_rpm     → m1=TPM %, m2=RPM %, m3=month tokens, r2=sec to month end
    """

    slot_id: str
    display_name: str
    kind: str
    m1: float = 0.0
    m2: float = 0.0
    m3: Optional[float] = None
    r1: int = 0
    r2: int = 0
    note: str = ""
    status: str = "ok"
    pace: Optional[int] = None       # -3..+3 (slower..faster than expected)
    regen: Optional[float] = None    # %/min rolling regen, for rolling-window providers
    currency: Optional[str] = None   # "EUR" / "USD" — needed for cost_budget
    ok: bool = True
    extra: dict = field(default_factory=dict)  # debug-only, not sent over BLE

    def to_payload(self) -> dict:
        p: dict = {
            "p": self.slot_id,
            "n": self.display_name,
            "k": self.kind,
            "m1": round(self.m1, 2),
            "m2": round(self.m2, 2),
            "r1": int(self.r1),
            "r2": int(self.r2),
            "st": self.status,
            "ok": self.ok,
        }
        if self.note:
            p["note"] = self.note
        if self.m3 is not None:
            p["m3"] = round(self.m3, 2)
        if self.pace is not None:
            p["pace"] = int(self.pace)
        if self.regen is not None:
            p["regen"] = round(self.regen, 2)
        if self.currency:
            p["cur"] = self.currency

        # Optional visualisation extras (currently used by tokens_abs/OpenCode).
        # `sp` (sparkline): up to 24 integer buckets, oldest → newest.
        # `sh` (shares):   up to 4 {"s": slug, "p": percent} entries summing ≈100.
        sp = self.extra.get("spark")
        if isinstance(sp, (list, tuple)) and sp:
            p["sp"] = [int(round(v)) for v in sp[:24]]
        sh = self.extra.get("shares")
        if isinstance(sh, (list, tuple)) and sh:
            trimmed = []
            for entry in sh[:4]:
                slug = str(entry.get("slug") or entry.get("s") or "")[:7]
                pct = int(round(float(entry.get("pct") or entry.get("p") or 0)))
                if slug:
                    trimmed.append({"s": slug, "p": max(0, min(100, pct))})
            if trimmed:
                p["sh"] = trimmed
        return p


@runtime_checkable
class Provider(Protocol):
    """Adapter contract. Each adapter inherits ProviderBase below."""

    id: str
    slot_id: str
    poll_seconds: int

    async def poll(self) -> Optional[Snapshot]: ...


class ProviderBase:
    """Common state shared by all adapters."""

    id: str = ""

    def __init__(self, cfg):  # cfg: ProviderConfig — typed via duck
        self.cfg = cfg
        self.slot_id = cfg.slot_id
        self.poll_seconds = max(5, int(cfg.poll_seconds))

    def log(self, msg: str) -> None:
        import time

        print(f"[{time.strftime('%H:%M:%S')}] [{self.id}/{self.slot_id}] {msg}", flush=True)
