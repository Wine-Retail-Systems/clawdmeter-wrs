"""AWS Bedrock adapter — Service Quotas + CloudWatch.

boto3 is imported lazily so users without AWS can still run the daemon.
TPM quota codes are not publicly listed in the AWS docs; we resolve them by
matching the quota *name* (regex: "On-demand model inference tokens per
minute for ...") via list_service_quotas, then cache the L-XXXXXXXX code in
the runtime state.

The TPM utilization metric AWS publishes (EstimatedTPMQuotaUsage) already
does the 5x output-burndown math for Claude 3.7+. We use it directly rather
than reimplementing the formula.

See feature-documentation/providers/bedrock.md for the discovery notes.
"""

from __future__ import annotations

import calendar
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from .. import paths
from ..config import ProviderConfig
from . import register
from .base import KIND_TPM_RPM, ProviderBase, Snapshot


def _quota_cache_path() -> Path:
    return paths.cache_dir() / "bedrock-quotas.json"


def _load_quota_cache() -> dict:
    p = _quota_cache_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {}


def _save_quota_cache(cache: dict) -> None:
    p = _quota_cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cache, indent=2))


def _seconds_to_month_end() -> int:
    now = datetime.now(timezone.utc)
    last_day = calendar.monthrange(now.year, now.month)[1]
    end = datetime(now.year, now.month, last_day, 23, 59, 59, tzinfo=timezone.utc)
    return int((end - now).total_seconds())


def _model_family_label(model_id: str) -> str:
    """Pretty short label: 'Sonnet 4.5', 'Haiku 4.5', 'Opus 4.1' — for the
    16-char `note` field on the BLE payload."""
    import re

    # Try the modern naming first: claude-(family)-N-N
    m = re.search(r"claude-(sonnet|haiku|opus)-(\d+)-(\d+)", model_id, re.IGNORECASE)
    if m:
        family = m.group(1).capitalize()
        return f"{family} {m.group(2)}.{m.group(3)}"
    # Legacy: claude-3-5-sonnet, claude-3-haiku
    m = re.search(r"claude-(\d+)-(\d+)?-?(sonnet|haiku|opus)", model_id, re.IGNORECASE)
    if m:
        family = m.group(3).capitalize()
        ver = m.group(1) + (("." + m.group(2)) if m.group(2) else "")
        return f"{family} {ver}"
    # Fallback: last segment of dotted ID, trimmed
    last = model_id.split(".")[-1][:14]
    return last


class BedrockProvider(ProviderBase):
    id = "bedrock"

    def __init__(self, cfg: ProviderConfig):
        super().__init__(cfg)
        self.region = str(cfg.get("region", "us-east-1"))
        self.model_id = str(cfg.get("model_id", ""))
        self._profile = cfg.get("aws_profile")
        self._tpm_quota: Optional[float] = None
        self._rpm_quota: Optional[float] = None
        self._quota_cache_key = f"{self.region}::{self.model_id}"

    def _session(self):
        try:
            import boto3  # type: ignore
        except ImportError:
            self.log("boto3 not installed (pip install boto3) — skipping")
            return None
        if self._profile:
            return boto3.Session(profile_name=self._profile, region_name=self.region)
        return boto3.Session(region_name=self.region)

    async def poll(self) -> Optional[Snapshot]:
        if not self.model_id:
            self.log("model_id not configured — skipping")
            return None

        session = self._session()
        if session is None:
            return None

        # Bedrock SDK calls aren't asyncio-native; run them in a thread to
        # avoid blocking the daemon's event loop during the polling cycle.
        import asyncio

        try:
            return await asyncio.to_thread(self._poll_sync, session)
        except Exception as e:  # noqa: BLE001 — boto3 raises a zoo of types
            self.log(f"poll failed: {e}")
            return None

    def _poll_sync(self, session) -> Optional[Snapshot]:
        if self._tpm_quota is None or self._rpm_quota is None:
            self._tpm_quota, self._rpm_quota = self._resolve_quotas(session)

        cw = session.client("cloudwatch")
        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=2)

        # TPM utilization from the AWS-computed estimate (handles the
        # 5x output burndown internally for Claude 3.7+).
        tpm_pct = self._cw_value(
            cw,
            metric_name="EstimatedTPMQuotaUsage",
            stat="Average",
            start=start,
            end=end,
            period=60,
        )
        if tpm_pct is None:
            # Fallback: derive from raw token counts.
            in_t = self._cw_value(cw, "InputTokenCount", "Sum", start, end, period=60) or 0
            out_t = self._cw_value(cw, "OutputTokenCount", "Sum", start, end, period=60) or 0
            cache_w = self._cw_value(cw, "CacheWriteInputTokens", "Sum", start, end, period=60) or 0
            burned = in_t + cache_w + 5 * out_t  # Claude 3.7+ formula
            tpm_pct = (burned / self._tpm_quota) * 100.0 if self._tpm_quota else 0.0

        rpm_pct = 0.0
        invocations = self._cw_value(cw, "Invocations", "Sum", start, end, period=60)
        if invocations is not None and self._rpm_quota:
            rpm_pct = (invocations / self._rpm_quota) * 100.0

        # Monthly token total — single GetMetricData over month-to-date.
        month_tokens = self._month_to_date_tokens(cw)

        note = self.cfg.display_note or _model_family_label(self.model_id)
        status = "ok"
        throttles = self._cw_value(
            cw,
            metric_name="UserErrorCount",
            stat="Sum",
            start=end - timedelta(minutes=5),
            end=end,
            period=300,
        )
        if throttles and throttles > 0:
            status = "throttled"
        elif tpm_pct > 90:
            status = "near-limit"

        return Snapshot(
            slot_id=self.slot_id,
            display_name=self.cfg.display_name or "Bedrock",
            note=note[:16],
            kind=KIND_TPM_RPM,
            m1=min(tpm_pct, 999.0),
            m2=min(rpm_pct, 999.0),
            m3=float(month_tokens) if month_tokens else None,
            r1=0,
            r2=_seconds_to_month_end(),
            status=status,
            currency=str(self.cfg.get("currency", "USD")),
            ok=True,
        )

    def _resolve_quotas(self, session) -> tuple[float, float]:
        """Resolve TPM and RPM quotas for self.model_id, with disk cache."""
        cache = _load_quota_cache()
        cached = cache.get(self._quota_cache_key)
        if cached and "tpm" in cached and "rpm" in cached:
            return float(cached["tpm"]), float(cached["rpm"])

        sq = session.client("service-quotas")
        tpm = self._lookup_quota(
            sq, name_contains=["tokens per minute", self._model_token_search()],
        )
        rpm = self._lookup_quota(
            sq, name_contains=["requests per minute", self._model_token_search()],
        )
        # Reasonable defaults to avoid divide-by-zero if AWS hides the quota.
        tpm = tpm or 200_000.0
        rpm = rpm or 50.0

        cache[self._quota_cache_key] = {"tpm": tpm, "rpm": rpm, "resolved_at": time.time()}
        _save_quota_cache(cache)
        return tpm, rpm

    def _model_token_search(self) -> str:
        """Return a model-name fragment that should appear in the quota name."""
        label = _model_family_label(self.model_id)  # e.g. "Sonnet 4.5"
        return label.split()[0].lower()  # "sonnet"

    def _lookup_quota(self, sq_client, name_contains: list[str]) -> Optional[float]:
        """Walk list_service_quotas pages and find a quota whose name matches
        all of the (case-insensitive) substrings."""
        paginator = sq_client.get_paginator("list_service_quotas")
        for page in paginator.paginate(ServiceCode="bedrock"):
            for q in page.get("Quotas", []):
                name = (q.get("QuotaName") or "").lower()
                if all(s.lower() in name for s in name_contains):
                    return float(q.get("Value") or 0.0)
        return None

    def _cw_value(self, cw, metric_name: str, stat: str, start, end, period: int) -> Optional[float]:
        """Return the most recent datapoint's value. Used for instantaneous metrics."""
        points = self._cw_points(cw, metric_name, stat, start, end, period)
        if not points:
            return None
        points.sort(key=lambda p: p["Timestamp"], reverse=True)
        return float(points[0].get(stat, 0.0))

    def _cw_sum(self, cw, metric_name: str, start, end, period: int) -> float:
        """Sum all datapoints in the range. Used for cumulative totals."""
        points = self._cw_points(cw, metric_name, "Sum", start, end, period)
        return sum(float(p.get("Sum", 0.0)) for p in points)

    def _cw_points(self, cw, metric_name: str, stat: str, start, end, period: int) -> list:
        try:
            resp = cw.get_metric_statistics(
                Namespace="AWS/Bedrock",
                MetricName=metric_name,
                Dimensions=[{"Name": "ModelId", "Value": self.model_id}],
                StartTime=start,
                EndTime=end,
                Period=period,
                Statistics=[stat],
            )
        except Exception as e:  # noqa: BLE001
            self.log(f"CloudWatch {metric_name} failed: {e}")
            return []
        return resp.get("Datapoints") or []

    def _month_to_date_tokens(self, cw) -> Optional[int]:
        now = datetime.now(timezone.utc)
        start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        total = 0
        for metric in ("InputTokenCount", "OutputTokenCount", "CacheWriteInputTokens"):
            total += int(self._cw_sum(cw, metric, start, now, period=86400))
        return total or None


register("bedrock", BedrockProvider)
