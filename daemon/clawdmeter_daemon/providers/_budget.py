"""Shared budget helpers for cost-style providers (Bifrost, Langdock).

Pure functions, no I/O. All datetimes are timezone-aware UTC.

* Reset durations use Bifrost's notation: ``<n><unit>`` with unit
  ``s m h d w M Q Y`` (``M`` = calendar month, ``Q`` = calendar quarter,
  ``Y`` = calendar year, all anchored on the day/time of ``last_reset``).
* A missed reset (gateway reset late, or ``last_reset`` is stale) is handled by
  stepping forward whole periods until the boundary lies in the future.
"""

from __future__ import annotations

import calendar
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

_DURATION_RE = re.compile(r"^\s*(\d+)\s*([smhdwMQY])\s*$")

_FIXED_UNITS = {
    "s": timedelta(seconds=1),
    "m": timedelta(minutes=1),
    "h": timedelta(hours=1),
    "d": timedelta(days=1),
    "w": timedelta(weeks=1),
}
_MONTH_UNITS = {"M": 1, "Q": 3, "Y": 12}

# Pace thresholds (percentage points of delta between used share and elapsed
# share) for steps +-1 / +-2 / +-3.
LEGACY_PACE_STEPS = (5.0, 15.0, 25.0)   # Langdock (unchanged behaviour)
FINE_PACE_STEPS = (2.0, 10.0, 20.0)     # Bifrost: small overshoot already shows


def parse_duration(text: object) -> Optional[tuple[int, str]]:
    """``"1M"`` -> ``(1, "M")``; invalid/zero -> None."""
    if not isinstance(text, str):
        return None
    m = _DURATION_RE.match(text)
    if not m:
        return None
    n = int(m.group(1))
    if n <= 0:
        return None
    return n, m.group(2)


def parse_iso(text: object) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp (``Z`` or offset) to aware UTC."""
    if not isinstance(text, str) or not text:
        return None
    s = text.strip()
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    # fromisoformat (<3.11) rejects >6 fractional digits; trim them.
    s = re.sub(r"(\.\d{6})\d+", r"\1", s)
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def add_months(dt: datetime, months: int) -> datetime:
    """Add calendar months, clamping the day (31 Jan + 1M = 28/29 Feb)."""
    idx = dt.year * 12 + (dt.month - 1) + months
    year, month0 = divmod(idx, 12)
    month = month0 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def _boundary(anchor: datetime, n: int, unit: str, k: int) -> datetime:
    """The k-th reset boundary after ``anchor`` (k=0 -> anchor itself)."""
    if unit in _FIXED_UNITS:
        return anchor + _FIXED_UNITS[unit] * (n * k)
    return add_months(anchor, _MONTH_UNITS[unit] * n * k)


def current_window(
    last_reset: datetime, duration: tuple[int, str], now: datetime
) -> tuple[datetime, datetime]:
    """Return ``(window_start, next_reset)`` with ``next_reset > now``.

    If ``now`` is before ``last_reset`` (clock skew) the first window is used.
    """
    n, unit = duration
    if unit in _FIXED_UNITS:
        period = _FIXED_UNITS[unit] * n
        elapsed = (now - last_reset) / period
        k = max(0, int(elapsed)) + 1
    else:
        step = _MONTH_UNITS[unit] * n
        months = (now.year - last_reset.year) * 12 + (now.month - last_reset.month)
        k = max(1, months // step)
    # Adjust for calendar clamping / estimate error.
    while k > 1 and _boundary(last_reset, n, unit, k - 1) > now:
        k -= 1
    while _boundary(last_reset, n, unit, k) <= now:
        k += 1
    return _boundary(last_reset, n, unit, k - 1), _boundary(last_reset, n, unit, k)


def next_reset(last_reset: datetime, duration: tuple[int, str], now: datetime) -> datetime:
    return current_window(last_reset, duration, now)[1]


def seconds_until(target: datetime, now: datetime) -> int:
    return max(0, int((target - now).total_seconds()))


def pace_from_delta(delta: float, steps: tuple[float, float, float] = LEGACY_PACE_STEPS) -> int:
    """Map ``used% - elapsed%`` to -3..+3. Edges: negative inclusive,
    positive exclusive (kept identical to the original Langdock rule)."""
    s1, s2, s3 = steps
    if delta <= -s3: return -3
    if delta <= -s2: return -2
    if delta <= -s1: return -1
    if delta < s1:   return 0
    if delta < s2:   return 1
    if delta < s3:   return 2
    return 3


def pace(
    used: float,
    limit: float,
    window_start: datetime,
    window_end: datetime,
    now: datetime,
    steps: tuple[float, float, float] = FINE_PACE_STEPS,
) -> Optional[int]:
    """Pace of ``used/limit`` against the elapsed share of the reset window."""
    if limit <= 0:
        return None
    total = (window_end - window_start).total_seconds()
    if total <= 0:
        return None
    elapsed = min(max((now - window_start).total_seconds() / total, 0.0), 1.0)
    return pace_from_delta((used / limit) * 100.0 - elapsed * 100.0, steps)


def month_pace(spent: float, budget: float, now: datetime) -> Optional[int]:
    """Langdock rule: calendar month, expected share = (day + hour/24) / days."""
    if budget <= 0:
        return None
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    day_of_month = now.day + (now.hour / 24.0)
    expected_pct = (day_of_month / days_in_month) * 100.0
    return pace_from_delta((spent / budget) * 100.0 - expected_pct, LEGACY_PACE_STEPS)


def seconds_to_month_end(now: datetime) -> int:
    """Seconds until 23:59:59 on the last day of ``now``'s month (Langdock)."""
    last_day = calendar.monthrange(now.year, now.month)[1]
    end = datetime(now.year, now.month, last_day, 23, 59, 59, tzinfo=timezone.utc)
    return int((end - now).total_seconds())


def status_for(used: float, limit: float) -> str:
    """``ok`` < 90 %, ``near-limit`` >= 90 %, ``over-budget`` >= 100 %."""
    if limit > 0:
        if used >= limit:
            return "over-budget"
        if used >= 0.9 * limit:
            return "near-limit"
    return "ok"
