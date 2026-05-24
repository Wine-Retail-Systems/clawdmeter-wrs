"""OpenCode adapter — read-only SQLite query over the local session DB.

OpenCode (sst/opencode) is a local CLI client, not a hosted service. We treat
its conversation database as the canonical source of "tokens consumed today".
SQLite is opened read-only with mode=ro + immutable=0 so we coexist with a
running OpenCode process via WAL.

The schema is a moving target (20+ Drizzle migrations YTD). Defensive reads:
we never assume a column exists, always fall back to JSON-blob parsing.

See feature-documentation/providers/opencode.md for schema notes.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..config import ProviderConfig


# Region-Codes für Bedrock Cross-Region-Inference-Profile. AWS publiziert
# Modelle als `<region>.<vendor>.<model>` (Präfix-Form) oder OpenCode
# aliased sie als `<model>-<region>` (Suffix-Form).
_REGION_CODES = {"eu": "EU", "us": "US", "apac": "APAC", "global": "GL"}
_REGION_PREFIX_RE = re.compile(r"^(eu|us|apac|global)\.", re.IGNORECASE)
_REGION_SUFFIX_RE = re.compile(r"-(eu|us|apac|global)(?:-v\d+)?$", re.IGNORECASE)
# Anthropic-Familie: claude-(sonnet|haiku|opus)-MAJOR-MINOR
_FAMILY_RE = re.compile(r"claude-(sonnet|haiku|opus)-(\d+)-(\d+)", re.IGNORECASE)
# Legacy-Anthropic: claude-3-5-sonnet etc.
_LEGACY_RE = re.compile(r"claude-(\d+)-(\d+)-(sonnet|haiku|opus)", re.IGNORECASE)


def format_opencode_note(provider_id: Optional[str], model_id: Optional[str]) -> str:
    """Compact 16-char-Note für den OpenCode-Screen.

    Beispiele:
      amazon-bedrock + eu.anthropic.claude-sonnet-4-6   → "Sonnet 4.6 EU"
      amazon-bedrock + eu.anthropic.claude-opus-4-6-v1  → "Opus 4.6 EU"
      amazon-bedrock + claude-opus-4-6-eu               → "Opus 4.6 EU"
      amazon-bedrock + global.anthropic.claude-opus-4-6-v1 → "Opus 4.6 GL"
      anthropic + claude-3-5-sonnet-20240620            → "Sonnet 3.5"
      openai + gpt-4o                                   → "openai:gpt-4o"
      (kein Modell)                                     → ""
    """
    if not provider_id:
        return ""

    region = ""
    family = ""
    if model_id:
        m_pre = _REGION_PREFIX_RE.match(model_id)
        if m_pre:
            region = _REGION_CODES[m_pre.group(1).lower()]
        else:
            m_suf = _REGION_SUFFIX_RE.search(model_id)
            if m_suf:
                region = _REGION_CODES[m_suf.group(1).lower()]

        m_fam = _FAMILY_RE.search(model_id)
        if m_fam:
            family = f"{m_fam.group(1).capitalize()} {m_fam.group(2)}.{m_fam.group(3)}"
        else:
            m_leg = _LEGACY_RE.search(model_id)
            if m_leg:
                family = f"{m_leg.group(3).capitalize()} {m_leg.group(1)}.{m_leg.group(2)}"

    if family and region:
        return f"{family} {region}"[:16]
    if family:
        return family[:16]

    # Kein Anthropic-Familien-Match — fallback auf provider:model-Kürzel
    if not model_id:
        return provider_id[:16]
    p_short = "bedrock" if provider_id == "amazon-bedrock" else provider_id[:7]
    m_short = model_id.split("/")[-1].split(":")[0]
    # Falls Region drin ist, zumindest die behalten
    region_suffix = f" {region}" if region else ""
    base = f"{p_short}:{m_short}"
    # Auf 16 Bytes inkl. Region trimmen
    budget = 16 - len(region_suffix)
    return (base[:budget] + region_suffix)[:16]
from . import register
from .base import KIND_TOKENS_ABS, ProviderBase, Snapshot


# Short, donut-legend-friendly slugs (max 7 chars — matches the firmware's
# `ProviderShare.slug` buffer). Anything not listed falls back to the first
# 7 chars of the providerID.
_PROVIDER_SLUGS = {
    "anthropic": "anthro",
    "amazon-bedrock": "bedrock",
    "amazon_bedrock": "bedrock",
    "bedrock": "bedrock",
    "openai": "openai",
    "openrouter": "openrtr",
    "openroutr": "openrtr",
    "google": "google",
    "vertex": "vertex",
    "azure": "azure",
    "groq": "groq",
    "deepseek": "deepsk",
    "xai": "xai",
    "ollama": "ollama",
    "lmstudio": "lmstud",
    "github-copilot": "copilot",
    "gitlab-duo": "gitlab",
    "cerebras": "cerebr",
    "fireworks": "firewks",
    "togetherai": "togthr",
    "nvidia": "nvidia",
    "huggingface": "hf",
    "opencode": "ocode",
}


def _short_provider_slug(provider_id: str) -> str:
    p = (provider_id or "").lower()
    if p in _PROVIDER_SLUGS:
        return _PROVIDER_SLUGS[p]
    return (provider_id or "?")[:7]


def _default_db_path() -> Optional[Path]:
    """XDG-style discovery. Returns None if no DB found."""
    override = os.environ.get("OPENCODE_DATA_DIR")
    candidates = []
    if override:
        candidates.append(Path(override))
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            candidates.append(Path(local) / "opencode")
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        if xdg:
            candidates.append(Path(xdg) / "opencode")
        candidates.append(Path.home() / ".local" / "share" / "opencode")

    for base in candidates:
        db = base / "opencode.db"
        if db.exists():
            return db
        # Channel-specific variants (issue #16885) — pick the most recently
        # modified opencode*.db in the directory if any.
        if base.is_dir():
            matches = sorted(base.glob("opencode*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
            if matches:
                return matches[0]
    return None


def _midnight_ms_local() -> int:
    now = datetime.now()
    midnight = datetime(now.year, now.month, now.day)
    return int(midnight.timestamp() * 1000)


def _seconds_to_midnight() -> int:
    now = time.time()
    today = datetime.fromtimestamp(now)
    tomorrow = datetime(today.year, today.month, today.day)
    # Add 24h
    from datetime import timedelta
    tomorrow = datetime(today.year, today.month, today.day) + timedelta(days=1)
    return int(tomorrow.timestamp() - now)


class OpenCodeProvider(ProviderBase):
    id = "opencode"

    def __init__(self, cfg: ProviderConfig):
        super().__init__(cfg)
        configured = str(cfg.get("db_path", "") or "").strip()
        self._configured_db_path: Optional[Path] = Path(configured) if configured else None
        self._last_tokens: Optional[int] = None
        self._last_seen_at: Optional[float] = None

    def _resolve_db_path(self) -> Optional[Path]:
        if self._configured_db_path:
            return self._configured_db_path if self._configured_db_path.exists() else None
        return _default_db_path()

    async def poll(self) -> Optional[Snapshot]:
        db_path = self._resolve_db_path()
        if not db_path:
            self.log("opencode.db not found (set db_path or install OpenCode)")
            return None

        try:
            (
                tokens_today,
                tokens_yesterday,
                active_provider,
                active_model,
                spark,
                shares,
            ) = self._query(db_path)
        except sqlite3.Error as e:
            self.log(f"SQLite read failed: {e}")
            return None

        note = self.cfg.display_note or format_opencode_note(active_provider, active_model)

        return Snapshot(
            slot_id=self.slot_id,
            display_name=self.cfg.display_name or "OpenCode",
            note=note[:16] if note else "",
            kind=KIND_TOKENS_ABS,
            m1=float(tokens_today),
            m2=0.0,  # Backend-quota correlation is wired in polling.py
            m3=float(tokens_yesterday) if tokens_yesterday else None,
            r1=0,
            r2=_seconds_to_midnight(),
            status="ok",
            ok=True,
            extra={
                "active_provider": active_provider,
                "active_model": active_model,
                "include_backend_quota": bool(self.cfg.get("include_backend_quota", True)),
                "spark": spark,
                "shares": shares,
            },
        )

    def _query(
        self, db_path: Path
    ) -> tuple[int, int, Optional[str], Optional[str], list[int], list[dict]]:
        """Return (today, yesterday, provider, model, spark[24], shares[≤4]).

        Opens the DB read-only via the mode=ro URI so WAL writers (a running
        OpenCode) can keep writing while we read.

        - `spark`: 24 hourly token buckets covering the trailing 24h, oldest
          → newest (index 23 = current hour).
        - `shares`: up to 4 entries `{slug, pct}` of today's tokens by
          providerID, descending, normalised to sum ≈ 100.
        """
        uri = f"file:{db_path}?mode=ro&immutable=0"
        conn = sqlite3.connect(uri, uri=True, timeout=2.0)
        conn.row_factory = sqlite3.Row
        try:
            midnight_ms = _midnight_ms_local()
            yesterday_ms = midnight_ms - 86_400_000
            now_ms = int(time.time() * 1000)
            twentyfour_ago_ms = now_ms - 86_400_000

            tokens_today = self._sum_tokens(conn, since_ms=midnight_ms, until_ms=None)
            tokens_yesterday = self._sum_tokens(
                conn, since_ms=yesterday_ms, until_ms=midnight_ms
            )
            active_provider, active_model = self._active_backend(conn)
            spark = self._hourly_buckets(
                conn, since_ms=twentyfour_ago_ms, now_ms=now_ms
            )
            shares = self._provider_shares(conn, since_ms=midnight_ms)
            return (
                tokens_today,
                tokens_yesterday,
                active_provider,
                active_model,
                spark,
                shares,
            )
        finally:
            conn.close()

    def _hourly_buckets(
        self, conn: sqlite3.Connection, since_ms: int, now_ms: int
    ) -> list[int]:
        """Return 24 hourly token counts, oldest → newest (index 23 = now).

        Bucket boundaries align to (now - 24h, now] in 1h slices. A message
        whose `time_created` falls in slice `i` adds its summed tokens to
        `buckets[i]`.
        """
        slice_ms = 3_600_000  # 1 hour
        buckets = [0] * 24
        rows = conn.execute(
            "SELECT time_created, data FROM message WHERE time_created >= ? AND time_created < ?",
            (since_ms, now_ms),
        )
        for r in rows:
            blob = r["data"]
            if not blob:
                continue
            try:
                d = json.loads(blob)
            except (TypeError, ValueError):
                continue
            tokens = d.get("tokens") or {}
            if not isinstance(tokens, dict):
                continue
            total = (
                int(tokens.get("input", 0) or 0)
                + int(tokens.get("output", 0) or 0)
                + int(tokens.get("reasoning", 0) or 0)
            )
            cache = tokens.get("cache") or {}
            if isinstance(cache, dict):
                total += int(cache.get("write", 0) or 0)
            if total <= 0:
                continue
            t = int(r["time_created"] or 0)
            idx = int((t - since_ms) // slice_ms)
            if 0 <= idx < 24:
                buckets[idx] += total
        return buckets

    def _provider_shares(
        self, conn: sqlite3.Connection, since_ms: int
    ) -> list[dict]:
        """Aggregate today's tokens by providerID, return top-4 percent shares.

        Smaller providers get folded into a virtual `"other"` bucket so the
        donut on the firmware always has at most 4 slices.
        """
        rows = conn.execute(
            "SELECT data FROM message WHERE time_created >= ?",
            (since_ms,),
        )
        by_provider: dict[str, int] = {}
        for r in rows:
            blob = r["data"]
            if not blob:
                continue
            try:
                d = json.loads(blob)
            except (TypeError, ValueError):
                continue
            tokens = d.get("tokens") or {}
            if not isinstance(tokens, dict):
                continue
            total = (
                int(tokens.get("input", 0) or 0)
                + int(tokens.get("output", 0) or 0)
                + int(tokens.get("reasoning", 0) or 0)
            )
            cache = tokens.get("cache") or {}
            if isinstance(cache, dict):
                total += int(cache.get("write", 0) or 0)
            if total <= 0:
                continue
            pid = d.get("providerID") or d.get("provider_id") or "?"
            slug = _short_provider_slug(str(pid))
            by_provider[slug] = by_provider.get(slug, 0) + total

        if not by_provider:
            return []
        ranked = sorted(by_provider.items(), key=lambda kv: kv[1], reverse=True)
        head, tail = ranked[:3], ranked[3:]
        if tail:
            head.append(("other", sum(v for _, v in tail)))
        total = sum(v for _, v in head) or 1
        out = []
        for slug, count in head:
            pct = round(count * 100.0 / total)
            out.append({"slug": slug, "pct": int(pct)})
        # Adjust rounding so the percentages sum to 100 — assign drift to the
        # largest slice; the firmware donut renders better with exact 100.
        drift = 100 - sum(e["pct"] for e in out)
        if out and drift != 0:
            out[0]["pct"] = max(0, min(100, out[0]["pct"] + drift))
        return out

    def _sum_tokens(self, conn: sqlite3.Connection, since_ms: int, until_ms: Optional[int]) -> int:
        """Sum tokens.total across messages in the time window.

        Iterates `message` rows, parses `data` JSON, sums input + output +
        reasoning (cache reads are intentionally excluded to match what the
        provider actually bills).
        """
        if until_ms is not None:
            rows = conn.execute(
                "SELECT data FROM message WHERE time_created >= ? AND time_created < ?",
                (since_ms, until_ms),
            )
        else:
            rows = conn.execute(
                "SELECT data FROM message WHERE time_created >= ?",
                (since_ms,),
            )

        total = 0
        for r in rows:
            blob = r["data"]
            if not blob:
                continue
            try:
                d = json.loads(blob)
            except (TypeError, ValueError):
                continue
            tokens = d.get("tokens") or {}
            if not isinstance(tokens, dict):
                continue
            total += int(tokens.get("input", 0) or 0)
            total += int(tokens.get("output", 0) or 0)
            total += int(tokens.get("reasoning", 0) or 0)
            cache = tokens.get("cache") or {}
            if isinstance(cache, dict):
                # cache_write is billed; cache_read is not.
                total += int(cache.get("write", 0) or 0)
        return total

    def _active_backend(self, conn: sqlite3.Connection) -> tuple[Optional[str], Optional[str]]:
        """Inspect the most recent assistant message for providerID/modelID."""
        try:
            row = conn.execute(
                "SELECT data FROM message ORDER BY time_created DESC LIMIT 50"
            ).fetchall()
        except sqlite3.Error:
            return (None, None)
        for r in row:
            try:
                d = json.loads(r["data"]) if r["data"] else {}
            except (TypeError, ValueError):
                continue
            provider = d.get("providerID") or d.get("provider_id")
            model = d.get("modelID") or d.get("model_id") or d.get("model")
            if provider:
                return (str(provider), str(model) if model else None)
        return (None, None)


register("opencode", OpenCodeProvider)
