"""Langdock adapter — workspace usage via the /export/users CSV pipeline.

Langdock has no realtime usage endpoint; we POST to /export/users, follow the
signed downloadUrl in the response, and aggregate the CSV for the current
calendar month. Two distinct workspace shapes are observed in the wild:

  * Pure managed  → /export/users carries no token/cost columns at all (the
                    pricing API is BYOK-only). We surface activity counts
                    instead: messages_total + action_messages as the main
                    number, with a donut breakdown of chat / workflows /
                    assistants / projects. This is the jacques.de shape.
  * BYOK / hybrid → token + per-million pricing columns are populated. We
                    compute EUR spend as before. Untested against a live
                    BYOK workspace post-refactor — guard rails are in place
                    but the cost code path is forward-looking.

`user_email` (optional config) filters to a single workspace member's row.
Without it we sum every row in the org, which is rarely what you want — the
setup wizard should prompt for it.

Two non-obvious wire-protocol facts the validator enforces but the docs
don't spell out:
  1. ISO-8601 datetimes MUST use the `Z` suffix; `+00:00` fails validation.
  2. The request body uses nested `{date,timezone}` objects, not flat ISO
     strings (matches docs.langdock.com).

See feature-documentation/providers/langdock.md for the full schema reference.
Polling cadence default is 10 minutes — anything tighter just wastes
roundtrips since the export job itself takes ~30 s to materialize.
"""

from __future__ import annotations

import calendar
import csv
import io
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from ..config import ProviderConfig
from . import register
from .base import KIND_COST_BUDGET, KIND_TOKENS_ABS, ProviderBase, Snapshot

API_BASE = "https://api.langdock.com"
EXPORT_ENDPOINT = "/export/users"

# Per-row column aliases. Lowercased keys matched against lowercased headers.
TOKEN_IN_KEYS = ("tokens_in", "input_tokens", "prompt_tokens", "tokens_input")
TOKEN_OUT_KEYS = ("tokens_out", "output_tokens", "completion_tokens", "tokens_output")
PRICE_IN_KEYS = (
    "input_price_usd_per_1m", "cost_usd_per_1m_input",
    "pricing_input_usd_per_1m", "price_per_1m_input_tokens",
)
PRICE_OUT_KEYS = (
    "output_price_usd_per_1m", "cost_usd_per_1m_output",
    "pricing_output_usd_per_1m", "price_per_1m_output_tokens",
)
COST_USD_KEYS = ("cost_usd", "total_cost_usd", "usd_cost")
COST_EUR_KEYS = ("cost_eur", "total_cost_eur", "eur_cost")
# Real Langdock /export/users columns first; older guesses kept for forward-compat.
MESSAGE_KEYS = ("messages_total", "message_count", "messages", "messages_sent", "total_messages")
CHAT_MESSAGES_KEYS = ("messages_chat",)
ASSISTANT_MESSAGES_KEYS = ("messages_assistants",)
PROJECT_MESSAGES_KEYS = ("messages_projects",)
ACTION_MESSAGES_KEYS = ("action_messages", "messages_actions")
EMAIL_KEYS = ("email", "user_email")


def _seconds_to_month_end() -> int:
    now = datetime.now(timezone.utc)
    last_day = calendar.monthrange(now.year, now.month)[1]
    end = datetime(now.year, now.month, last_day, 23, 59, 59, tzinfo=timezone.utc)
    return int((end - now).total_seconds())


# Langdock's /export/* validator rejects `+00:00` offsets — only the `Z`
# suffix matches its ISO-8601 regex. Stick to a fixed-shape strftime.
_LANGDOCK_DT_FMT = "%Y-%m-%dT%H:%M:%S.000Z"


def _month_start_iso() -> str:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc).strftime(_LANGDOCK_DT_FMT)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime(_LANGDOCK_DT_FMT)


def _coerce_int(v: Any) -> int:
    if v is None or v == "":
        return 0
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _coerce_float(v: Any) -> float:
    if v is None or v == "":
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _first_match(row_lc: dict[str, str], keys: tuple[str, ...]) -> str:
    """Return the first non-empty value among `keys` (case-insensitive)."""
    for k in keys:
        v = row_lc.get(k)
        if v not in (None, ""):
            return v
    return ""


class LangdockParseResult:
    __slots__ = (
        "spent_eur", "tokens", "messages", "rows_with_cost", "rows_total",
        "first_row_columns", "chat", "assistants", "projects", "actions",
        "rows_matched",
    )

    def __init__(self) -> None:
        self.spent_eur: float = 0.0
        self.tokens: int = 0
        self.messages: int = 0
        self.chat: int = 0
        self.assistants: int = 0
        self.projects: int = 0
        self.actions: int = 0
        self.rows_with_cost: int = 0
        self.rows_total: int = 0
        self.rows_matched: int = 0   # rows actually counted (after email filter)
        self.first_row_columns: list[str] = []

    @property
    def mode(self) -> str:
        if self.rows_matched == 0:
            return "empty"
        if self.rows_with_cost == 0:
            return "managed"
        if self.rows_with_cost == self.rows_matched:
            return "BYOK"
        return "hybrid"

    @property
    def total_activity(self) -> int:
        """messages_total covers chat+assistants+projects; action_messages is
        a disjoint workflow/tool-call count, so they sum without overlap."""
        return self.messages + self.actions

    def shares(self) -> list[dict]:
        total = self.total_activity
        if total <= 0:
            return []
        breakdown = [
            ("Workfl.", self.actions),
            ("Chat", self.chat),
            ("Projekt", self.projects),
            ("Assist.", self.assistants),
        ]
        out = []
        for slug, count in breakdown:
            if count <= 0:
                continue
            out.append({"slug": slug, "pct": round(100 * count / total)})
        return out


class LangdockProvider(ProviderBase):
    id = "langdock"

    def __init__(self, cfg: ProviderConfig):
        super().__init__(cfg)
        self._last_spent: Optional[float] = None
        self._last_messages: Optional[int] = None
        self._last_seen_at: Optional[float] = None
        self._logged_columns_once: bool = False

    def _api_key(self) -> Optional[str]:
        env = self.cfg.get("api_key_env", "LANGDOCK_API_KEY")
        key = os.environ.get(env)
        return key if key else None

    async def poll(self) -> Optional[Snapshot]:
        api_key = self._api_key()
        if not api_key:
            self.log(f"API key env var {self.cfg.get('api_key_env')} not set — skipping")
            return None

        budget = float(self.cfg.get("monthly_budget_eur", 0))
        currency = str(self.cfg.get("currency", "EUR"))
        usd_to_eur = float(self.cfg.get("usd_to_eur", 0.92))

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        # /export/users — nested {date,timezone} request schema per docs.langdock.com.
        body = {
            "from": {"date": _month_start_iso(), "timezone": "UTC"},
            "to":   {"date": _now_iso(),         "timezone": "UTC"},
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as http:
                req = await http.post(API_BASE + EXPORT_ENDPOINT, headers=headers, json=body)
                if req.status_code >= 400:
                    self.log(f"Export request HTTP {req.status_code}: {req.text[:200]}")
                    return self._stale_snapshot(budget, currency)

                payload = req.json()
                csv_url = self._extract_download_url(payload)
                if not csv_url:
                    self.log(f"Export response missing signed URL (payload keys: {list(payload)[:6]})")
                    return self._stale_snapshot(budget, currency)

                csv_resp = await http.get(csv_url)
                csv_resp.raise_for_status()
                csv_text = csv_resp.text
        except (httpx.HTTPError, ValueError) as e:
            self.log(f"Export fetch failed: {e}")
            return self._stale_snapshot(budget, currency)

        user_email = str(self.cfg.get("user_email", "")).strip().lower()
        result = self._parse_csv(csv_text, usd_to_eur, user_email)
        self._log_unknown_columns_once(result.first_row_columns)
        if user_email and result.rows_matched == 0:
            self.log(f"user_email={user_email!r} not found in /export/users — falling back to org-wide aggregation")
            result = self._parse_csv(csv_text, usd_to_eur, "")
        self._update_burn_state(result.spent_eur, result.messages)

        return self._snapshot_from(result, budget, currency)

    @staticmethod
    def _extract_download_url(payload: dict) -> Optional[str]:
        """Doc-canonical path is payload.data.downloadUrl; we still accept a
        flat shape for forward-compat in case Langdock changes the wrapper."""
        if not isinstance(payload, dict):
            return None
        data = payload.get("data")
        if isinstance(data, dict):
            url = data.get("downloadUrl") or data.get("url")
            if isinstance(url, str) and url:
                return url
        flat = payload.get("downloadUrl") or payload.get("url")
        return flat if isinstance(flat, str) and flat else None

    def _parse_csv(self, text: str, usd_to_eur: float, user_email: str = "") -> LangdockParseResult:
        result = LangdockParseResult()
        reader = csv.DictReader(io.StringIO(text))
        spent_usd = 0.0
        for row in reader:
            # Case-insensitive view of the row for tolerant lookups.
            row_lc = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            if not result.first_row_columns:
                result.first_row_columns = list(row_lc.keys())
            result.rows_total += 1

            if user_email:
                row_email = _first_match(row_lc, EMAIL_KEYS).lower()
                if row_email != user_email:
                    continue
            result.rows_matched += 1

            t_in = _coerce_int(_first_match(row_lc, TOKEN_IN_KEYS))
            t_out = _coerce_int(_first_match(row_lc, TOKEN_OUT_KEYS))
            result.tokens += t_in + t_out
            result.messages += _coerce_int(_first_match(row_lc, MESSAGE_KEYS))
            result.chat += _coerce_int(_first_match(row_lc, CHAT_MESSAGES_KEYS))
            result.assistants += _coerce_int(_first_match(row_lc, ASSISTANT_MESSAGES_KEYS))
            result.projects += _coerce_int(_first_match(row_lc, PROJECT_MESSAGES_KEYS))
            result.actions += _coerce_int(_first_match(row_lc, ACTION_MESSAGES_KEYS))

            in_price = _coerce_float(_first_match(row_lc, PRICE_IN_KEYS))
            out_price = _coerce_float(_first_match(row_lc, PRICE_OUT_KEYS))
            row_cost_usd = (t_in / 1_000_000.0) * in_price + (t_out / 1_000_000.0) * out_price

            if row_cost_usd > 0:
                spent_usd += row_cost_usd
                result.rows_with_cost += 1
                continue

            # Direct cost columns (some BYOK exports skip per-1M pricing and
            # publish the final number — accept either, but only count the
            # row as "with cost" if it has a non-zero value).
            direct_usd = _coerce_float(_first_match(row_lc, COST_USD_KEYS))
            if direct_usd > 0:
                spent_usd += direct_usd
                result.rows_with_cost += 1
                continue

            direct_eur = _coerce_float(_first_match(row_lc, COST_EUR_KEYS))
            if direct_eur > 0:
                spent_usd += direct_eur / usd_to_eur  # unify on USD, single FX conversion at the end
                result.rows_with_cost += 1

        result.spent_eur = spent_usd * usd_to_eur
        return result

    def _snapshot_from(self, result: LangdockParseResult, budget: float, currency: str) -> Snapshot:
        # Pure-managed workspaces with zero pricing data emit tokens_abs. The
        # main number is the user's combined activity (chat+assistants+projects
        # rolled into messages_total, plus the disjoint workflow/action count);
        # shares break it down into Workflow / Chat / Projekt / Assistent so
        # the donut tells the "what kind of activity" story.
        if result.mode == "managed" and result.spent_eur == 0:
            note = self.cfg.display_note or "Aktivität"
            return Snapshot(
                slot_id=self.slot_id,
                display_name=self.cfg.display_name or "Langdock",
                note=note[:16],
                kind=KIND_TOKENS_ABS,
                m1=float(result.total_activity),
                m2=0.0,
                m3=None,
                r1=0,
                r2=_seconds_to_month_end(),
                status="ok",
                ok=True,
                extra={
                    "mode": result.mode,
                    "rows": result.rows_total,
                    "rows_matched": result.rows_matched,
                    "messages": result.messages,
                    "actions": result.actions,
                    "shares": result.shares(),
                },
            )

        note = self.cfg.display_note or {"BYOK": "BYOK", "hybrid": "hybrid", "empty": "managed"}.get(result.mode, "")
        pace = self._estimate_pace(result.spent_eur, budget)

        status = "ok"
        if budget > 0:
            if result.spent_eur >= budget:
                status = "over-budget"
            elif result.spent_eur >= 0.9 * budget:
                status = "near-limit"

        return Snapshot(
            slot_id=self.slot_id,
            display_name=self.cfg.display_name or "Langdock",
            note=note[:16],
            kind=KIND_COST_BUDGET,
            m1=result.spent_eur,
            m2=budget,
            m3=float(result.tokens) if result.tokens else None,
            r1=0,
            r2=_seconds_to_month_end(),
            status=status,
            pace=pace,
            currency=currency,
            ok=True,
            extra={"mode": result.mode, "rows": result.rows_total, "messages": result.messages},
        )

    def _stale_snapshot(self, budget: float, currency: str) -> Snapshot:
        return Snapshot(
            slot_id=self.slot_id,
            display_name=self.cfg.display_name or "Langdock",
            note=self.cfg.display_note,
            kind=KIND_COST_BUDGET,
            m1=self._last_spent or 0.0,
            m2=budget,
            r2=_seconds_to_month_end(),
            status="stale",
            currency=currency,
            ok=False,
        )

    def _estimate_pace(self, spent: float, budget: float) -> Optional[int]:
        if budget <= 0:
            return None
        now = datetime.now(timezone.utc)
        days_in_month = calendar.monthrange(now.year, now.month)[1]
        day_of_month = now.day + (now.hour / 24.0)
        expected_pct = (day_of_month / days_in_month) * 100.0
        actual_pct = (spent / budget) * 100.0
        delta = actual_pct - expected_pct
        if delta <= -25: return -3
        if delta <= -15: return -2
        if delta <= -5:  return -1
        if delta < 5:    return 0
        if delta < 15:   return 1
        if delta < 25:   return 2
        return 3

    def _update_burn_state(self, spent: float, messages: int) -> None:
        self._last_spent = spent
        self._last_messages = messages
        self._last_seen_at = time.time()

    def _log_unknown_columns_once(self, columns: list[str]) -> None:
        """One-shot forward-compat probe: warn about CSV columns that look
        usage-shaped (token/cost/message/price) but didn't match any alias
        list. Metadata columns (period_*, org_id, *_rank, ...) are expected
        and ignored. If Langdock ships a new pricing column we want to know."""
        if self._logged_columns_once or not columns:
            return
        self._logged_columns_once = True
        known: set[str] = set()
        for group in (TOKEN_IN_KEYS, TOKEN_OUT_KEYS, PRICE_IN_KEYS, PRICE_OUT_KEYS,
                      COST_USD_KEYS, COST_EUR_KEYS, MESSAGE_KEYS,
                      CHAT_MESSAGES_KEYS, ASSISTANT_MESSAGES_KEYS,
                      PROJECT_MESSAGES_KEYS, ACTION_MESSAGES_KEYS, EMAIL_KEYS):
            known.update(group)
        # Only flag truly new pricing/token signals — message-derived rank
        # and aggregate columns (messages_*_rank, *_to_messages, …) are
        # known noise we deliberately don't aggregate.
        pricing_hints = ("token", "cost", "price", "spend", "billed")
        suspicious = [
            c for c in columns
            if c not in known and any(h in c for h in pricing_hints)
        ]
        if suspicious:
            self.log(f"Unmapped usage-shaped CSV columns (may indicate new schema): {suspicious}")


register("langdock", LangdockProvider)
