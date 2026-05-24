"""OpenAI Codex / ChatGPT adapter — polls chatgpt.com/backend-api/wham/usage.

Reuses the OAuth access_token written by the `codex` CLI to `~/.codex/auth.json`
(or `$CODEX_HOME/auth.json`). The `codex` CLI auto-refreshes that token when
it runs, so we don't implement refresh ourselves — if the API returns 401 we
just log and let the user run `codex` again.

Backend response (verbatim field names, abridged):

    {
      "plan_type": "plus" | "pro" | "free" | ...,
      "rate_limit": {
        "primary_window":   { "used_percent": int, "reset_at": <unix-s>, "limit_window_seconds": 18000 },
        "secondary_window": { "used_percent": int, "reset_at": <unix-s>, "limit_window_seconds": 604800 }
      },
      "credits": { "has_credits": bool, "unlimited": bool, "balance": number|string|null }
    }

We map this to KIND_PCT_WINDOW analogous to the Anthropic adapter:
  m1 = primary (5h session) %, r1 = seconds to reset
  m2 = secondary (7d weekly) %, r2 = seconds to reset
  note = plan_type (capitalized) when display_note is empty

Endpoint can be overridden via `chatgpt_base_url` in `~/.codex/config.toml`
(matching the `codex` CLI's own override key) or via the env var
`CLAWDMETER_CODEX_BASE_URL`.
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional

import httpx

from .. import paths
from ..config import ProviderConfig
from . import register
from .base import KIND_PCT_WINDOW, ProviderBase, Snapshot


DEFAULT_BASE_URL = "https://chatgpt.com/backend-api"
CHATGPT_USAGE_PATH = "/wham/usage"
CODEX_USAGE_PATH = "/api/codex/usage"

# Window classification by limit_window_seconds. CodexBar uses strict equality;
# we mirror that to stay in sync with the ChatGPT backend's current contract.
SESSION_WINDOW_SECONDS = 5 * 3600          # 18000 — "5h session"
WEEKLY_WINDOW_SECONDS = 7 * 24 * 3600      # 604800 — "7d weekly"


def _read_auth_file() -> Optional[dict]:
    """Return parsed auth.json or None. We do not refresh tokens ourselves —
    the `codex` CLI rewrites this file on every login/refresh."""
    path = paths.codex_auth_file()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _extract_credentials(blob: dict) -> tuple[Optional[str], Optional[str]]:
    """Return (access_token, account_id). Either may be None.

    Two shapes are observed in the wild:
      (a) `OPENAI_API_KEY = "sk-..."` at top level — direct API-key auth.
      (b) `tokens.access_token` + optional `tokens.account_id` — ChatGPT-OAuth.
    """
    api_key = blob.get("OPENAI_API_KEY")
    if isinstance(api_key, str) and api_key.strip():
        return api_key.strip(), None

    tokens = blob.get("tokens")
    if not isinstance(tokens, dict):
        return None, None

    def pick(*keys: str) -> Optional[str]:
        for k in keys:
            v = tokens.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return None

    return pick("access_token", "accessToken"), pick("account_id", "accountId")


def _parse_base_url_from_codex_config() -> Optional[str]:
    """Honor `chatgpt_base_url = "..."` in ~/.codex/config.toml so users who
    point the `codex` CLI at a proxy/enterprise endpoint don't have to
    duplicate it in our config."""
    try:
        contents = paths.codex_config_file().read_text(encoding="utf-8")
    except OSError:
        return None
    for raw_line in contents.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() != "chatgpt_base_url":
            continue
        v = value.strip().strip('"').strip("'").strip()
        return v or None
    return None


def _normalize_base_url(raw: str) -> str:
    v = raw.strip().rstrip("/")
    if not v:
        return DEFAULT_BASE_URL
    if (v.startswith("https://chatgpt.com") or v.startswith("https://chat.openai.com")) \
       and "/backend-api" not in v:
        v += "/backend-api"
    return v


def _resolve_usage_url(cfg: ProviderConfig) -> str:
    override = (cfg.get("base_url") or os.environ.get("CLAWDMETER_CODEX_BASE_URL") or
                _parse_base_url_from_codex_config() or DEFAULT_BASE_URL)
    base = _normalize_base_url(override)
    path = CHATGPT_USAGE_PATH if "/backend-api" in base else CODEX_USAGE_PATH
    return base + path


def _seconds_until(reset_at_unix: int) -> int:
    if reset_at_unix <= 0:
        return 0
    delta = reset_at_unix - int(time.time())
    return max(0, delta)


def _classify_windows(rate_limit: dict) -> tuple[Optional[dict], Optional[dict]]:
    """Map (primary_window, secondary_window) → (session, weekly).

    The backend usually returns them in (session, weekly) order, but the field
    is named `primary`/`secondary` — so we re-sort by `limit_window_seconds`
    to be safe, the same way CodexBar's normalizer does.
    """
    p = rate_limit.get("primary_window") if isinstance(rate_limit, dict) else None
    s = rate_limit.get("secondary_window") if isinstance(rate_limit, dict) else None

    def role(w):
        if not isinstance(w, dict):
            return "unknown"
        lws = w.get("limit_window_seconds")
        if lws == SESSION_WINDOW_SECONDS:
            return "session"
        if lws == WEEKLY_WINDOW_SECONDS:
            return "weekly"
        return "unknown"

    rp, rs = role(p), role(s)
    if rp == "weekly" and rs in ("session", "unknown"):
        return s, p
    if rp == "unknown" and rs == "weekly":
        return p, s
    return p, s


PLAN_LABELS = {
    "free": "Free",
    "free_workspace": "Free WS",
    "go": "Go",
    "plus": "Plus",
    "pro": "Pro",
    "team": "Team",
    "business": "Business",
    "enterprise": "Enterprise",
    "education": "Edu",
    "edu": "Edu",
    "k12": "K-12",
    "guest": "Guest",
    "quorum": "Quorum",
}


def _plan_label(plan_type: Optional[str]) -> str:
    if not plan_type:
        return ""
    return PLAN_LABELS.get(plan_type.lower(), plan_type[:12])


class CodexProvider(ProviderBase):
    id = "codex"

    def __init__(self, cfg: ProviderConfig):
        super().__init__(cfg)
        self._last_session_pct: Optional[float] = None
        self._last_session_seen_at: Optional[float] = None
        self._session_window_seconds: int = SESSION_WINDOW_SECONDS

    async def poll(self) -> Optional[Snapshot]:
        blob = _read_auth_file()
        if blob is None:
            self.log("Kein ~/.codex/auth.json (codex CLI nicht eingeloggt) — skipping")
            return None

        access_token, account_id = _extract_credentials(blob)
        if not access_token:
            self.log("auth.json enthält weder OPENAI_API_KEY noch tokens.access_token")
            return None

        url = _resolve_usage_url(self.cfg)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "User-Agent": "clawdmeter-daemon/0.1",
        }
        if account_id:
            headers["ChatGPT-Account-Id"] = account_id

        try:
            async with httpx.AsyncClient(timeout=20.0) as http:
                resp = await http.get(url, headers=headers)
        except httpx.HTTPError as e:
            self.log(f"Usage-API HTTP-Fehler: {e}")
            return None

        if resp.status_code in (401, 403):
            self.log("401/403 — Codex-Token abgelaufen. Bitte `codex` ausführen, um zu refreshen.")
            return None
        if resp.status_code >= 400:
            self.log(f"Usage-API HTTP {resp.status_code}: {resp.text[:200]}")
            return None

        try:
            data = resp.json()
        except ValueError:
            self.log("Antwort war kein JSON")
            return None

        rate_limit = data.get("rate_limit") if isinstance(data, dict) else None
        if not isinstance(rate_limit, dict):
            self.log("Antwort enthielt kein rate_limit-Objekt — Plan unterstützt evtl. keine Quota")
            return None

        session_w, weekly_w = _classify_windows(rate_limit)

        def pct(w):
            if not isinstance(w, dict):
                return 0.0
            try:
                return float(w.get("used_percent", 0))
            except (TypeError, ValueError):
                return 0.0

        def reset_s(w):
            if not isinstance(w, dict):
                return 0
            try:
                return _seconds_until(int(w.get("reset_at", 0) or 0))
            except (TypeError, ValueError):
                return 0

        session_pct = pct(session_w)
        weekly_pct = pct(weekly_w)
        session_reset_s = reset_s(session_w)
        weekly_reset_s = reset_s(weekly_w)

        # Track session window length so pace doesn't drift if OpenAI changes it.
        if isinstance(session_w, dict):
            lws = session_w.get("limit_window_seconds")
            if isinstance(lws, int) and lws > 0:
                self._session_window_seconds = lws

        pace = self._estimate_pace(session_pct, session_reset_s)
        regen = self._estimate_regen(session_pct)

        note = self.cfg.display_note or _plan_label(data.get("plan_type") if isinstance(data, dict) else None)

        return Snapshot(
            slot_id=self.slot_id,
            display_name=self.cfg.display_name or "Codex",
            note=note,
            kind=KIND_PCT_WINDOW,
            m1=session_pct,
            m2=weekly_pct,
            r1=session_reset_s,
            r2=weekly_reset_s,
            status="ok",
            pace=pace,
            regen=regen,
            ok=True,
        )

    def _estimate_pace(self, session_pct: float, reset_s: int) -> Optional[int]:
        if reset_s <= 0:
            return None
        window = self._session_window_seconds
        elapsed = window - reset_s
        if elapsed <= 0:
            return 0
        expected_pct = (elapsed / window) * 100.0
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
        now = time.time()
        prev_pct = self._last_session_pct
        prev_t = self._last_session_seen_at
        self._last_session_pct = session_pct
        self._last_session_seen_at = now
        if prev_pct is None or prev_t is None:
            return None
        dt_min = (now - prev_t) / 60.0
        if dt_min < 0.5:
            return None
        drop_pct_per_min = (prev_pct - session_pct) / dt_min
        if drop_pct_per_min <= 0:
            return 0.0
        return drop_pct_per_min


register("codex", CodexProvider)
