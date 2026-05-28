#!/usr/bin/env python3
"""Diagnostic: hit every Langdock /export/* endpoint and dump what we get.

Run it when the Langdock provider reports 0.00€ to find out which export
table actually carries the workspace's activity (users vs. models vs.
agents vs. projects). Output is meant to be pasted back into a Claude
session for analysis.

Usage:
    python3 tools/diag_langdock.py            # uses LANGDOCK_API_KEY env or secrets.env
    python3 tools/diag_langdock.py --month-to-date
    python3 tools/diag_langdock.py --from 2026-05-01 --to 2026-05-28
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

API_BASE = "https://api.langdock.com"
ENDPOINTS = ["/export/users", "/export/models", "/export/agents", "/export/projects"]


def _load_secrets_env() -> None:
    """Pull LANGDOCK_API_KEY from ~/.config/clawdmeter/secrets.env if not already set."""
    if os.environ.get("LANGDOCK_API_KEY"):
        return
    sec = Path.home() / ".config" / "clawdmeter" / "secrets.env"
    if not sec.is_file():
        return
    for line in sec.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _iso(d: datetime) -> str:
    # Langdock's validator requires `Z` suffix and rejects `+00:00`.
    return d.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="from_date", help="YYYY-MM-DD (default: 1st of current month)")
    p.add_argument("--to", dest="to_date", help="YYYY-MM-DD (default: now)")
    p.add_argument("--month-to-date", action="store_true", help="alias for default range")
    return p.parse_args()


def _range_from_args(args: argparse.Namespace) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    if args.from_date:
        start = datetime.fromisoformat(args.from_date).replace(tzinfo=timezone.utc)
    else:
        start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    if args.to_date:
        end = datetime.fromisoformat(args.to_date).replace(tzinfo=timezone.utc)
    else:
        end = now
    return _iso(start), _iso(end)


def _hit(client: httpx.Client, endpoint: str, headers: dict, body: dict) -> None:
    print(f"\n=== {endpoint} ===")
    try:
        r = client.post(API_BASE + endpoint, headers=headers, json=body, timeout=30.0)
    except httpx.HTTPError as e:
        print(f"  ERROR: request failed: {e}")
        return
    print(f"  HTTP {r.status_code}")
    if r.status_code >= 400:
        print(f"  Body: {r.text[:400]}")
        return
    try:
        payload = r.json()
    except ValueError:
        print(f"  Non-JSON response: {r.text[:200]}")
        return

    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    download_url = data.get("downloadUrl") or data.get("url")
    record_count = data.get("recordCount")
    print(f"  recordCount={record_count}  downloadUrl={'present' if download_url else 'MISSING'}")
    if not download_url:
        print(f"  Payload keys: {list(payload)[:8]}")
        return

    try:
        csv_resp = client.get(download_url, timeout=30.0)
        csv_resp.raise_for_status()
    except httpx.HTTPError as e:
        print(f"  ERROR fetching CSV: {e}")
        return

    text = csv_resp.text
    print(f"  CSV size: {len(text)} bytes")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        print("  CSV empty")
        return
    print(f"  Columns ({len(rows[0])}): {rows[0]}")
    print(f"  Data rows: {len(rows) - 1}")
    for i, row in enumerate(rows[1:4], start=1):
        print(f"  Row {i}: {row}")


def main() -> int:
    _load_secrets_env()
    api_key = os.environ.get("LANGDOCK_API_KEY")
    if not api_key:
        print("LANGDOCK_API_KEY not set (env or ~/.config/clawdmeter/secrets.env).", file=sys.stderr)
        return 1

    args = _parse_args()
    start, end = _range_from_args(args)
    print(f"Range: {start} → {end}")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {"from": {"date": start, "timezone": "UTC"}, "to": {"date": end, "timezone": "UTC"}}

    with httpx.Client() as client:
        for ep in ENDPOINTS:
            _hit(client, ep, headers, body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
