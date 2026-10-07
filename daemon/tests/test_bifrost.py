import asyncio
import copy
import json
import os
import unittest
from datetime import datetime, timezone
from unittest import mock

import httpx

from clawdmeter_daemon.config import ProviderConfig
from clawdmeter_daemon.providers import bifrost, create

# Live response of GET /api/governance/virtual-keys/quota (2026-10-07,
# Bifrost v2.2.5), shortened. No key material.
FIXTURE = {
    "virtual_key_name": "user-sascha.krinke@jacques.de",
    "is_active": True,
    "budgets": [{
        "id": "5f430e78-e1fe-4aa9-a6ff-1780872c9fa6",
        "max_limit": 15000,
        "reset_duration": "1M",
        "last_reset": "2026-10-01T00:00:00Z",
        "current_usage": 3769.158020095,
        "model_config_id": "fc2e2daa-724c-48ff-9079-58eebab0bf7b",
        "config_hash": "",
        "created_at": "2026-07-16T13:34:57.793963Z",
        "updated_at": "2026-09-18T08:06:50.24957Z",
        "per_model_usage": [
            {"model": "eu.anthropic.claude-sonnet-5", "provider": "bedrock", "total_requests": 11321, "total_tokens": 2253698294, "total_cost": 968.95038196},
            {"model": "eu.anthropic.claude-opus-5", "provider": "bedrock", "total_requests": 5604, "total_tokens": 1996759880, "total_cost": 2720.98540175},
            {"model": "eu.anthropic.claude-haiku-4-5-20251001-v1:0", "provider": "bedrock", "total_requests": 361, "total_tokens": 11822443, "total_cost": 5.941558865},
            {"model": "eu.anthropic.claude-opus-5-5", "provider": "bedrock", "total_requests": 296, "total_tokens": 136159928, "total_cost": 94.44707844},
            {"model": "eu.anthropic.claude-sonnet-5-5", "provider": "bedrock", "total_requests": 3, "total_tokens": 84872, "total_cost": 0.17325451},
            {"model": "deepseek/deepseek-v4-flash-0731", "provider": "TensorX (Anthropic)", "total_requests": 1, "total_tokens": 13, "total_cost": 3.35e-06},
            {"model": "gpt-5.4-mini", "provider": "azure", "total_requests": 1, "total_tokens": 17, "total_cost": 3.05e-05},
        ],
    }],
    "rate_limit": None,
}
NOW = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)
FAKE_KEY = "sk-bf-TESTKEY-not-a-real-key"


def make(extra=None, handler=None, key=FAKE_KEY):
    raw = {"id": "bifrost", "enabled": True, "slot_id": "bifrost",
           "api_key_env": "BIFROST_TEST_KEY", "base_url": "https://gw.example"}
    raw.update(extra or {})
    prov = create(ProviderConfig(raw=raw))
    prov._now = lambda: NOW
    if handler:
        prov._transport = httpx.MockTransport(handler)
    return prov


def ok_handler(body):
    seen = []

    def h(request):
        seen.append(request)
        return httpx.Response(200, json=body)
    h.seen = seen
    return h


def poll(prov, key=FAKE_KEY):
    env = {"BIFROST_TEST_KEY": key} if key else {}
    with mock.patch.dict(os.environ, env, clear=False):
        if not key:
            os.environ.pop("BIFROST_TEST_KEY", None)
        return asyncio.run(prov.poll())


class MappingTests(unittest.TestCase):
    def test_registered(self):
        self.assertIsNotNone(make())

    def test_month_budget(self):
        h = ok_handler(FIXTURE)
        snap = poll(make(handler=h))
        self.assertEqual(str(h.seen[0].url), "https://gw.example/api/governance/virtual-keys/quota")
        self.assertEqual(h.seen[0].headers["authorization"], f"Bearer {FAKE_KEY}")
        p = snap.to_payload()
        self.assertEqual(p["k"], "cost_budget")
        self.assertEqual(p["cur"], "USD")
        self.assertTrue(p["ok"])
        self.assertEqual(p["st"], "ok")
        self.assertEqual(p["m1"], 3769.16)
        self.assertEqual(p["m2"], 15000)
        self.assertEqual(p["r2"], 2116800)
        self.assertEqual(p["note"], "sascha.krinke")
        self.assertEqual(p["n"], "LLM Gateway")
        self.assertEqual(p["sh"], [{"s": "Opus", "p": 74}, {"s": "Sonnet", "p": 26}])
        self.assertNotIn(FAKE_KEY, json.dumps(p))
        self.assertLess(len(json.dumps(p, separators=(",", ":"))), 512)  # firmware BLE_BUF_SIZE

    def test_override(self):
        d = copy.deepcopy(FIXTURE)
        d["budgets"][0].update(max_limit=2000, override_amount=500, current_usage=100)
        self.assertEqual(poll(make(handler=ok_handler(d))).m2, 2500)

    def test_multiple_budgets_smallest_rest(self):
        a = {"max_limit": 2000, "current_usage": 1800, "reset_duration": "1M", "last_reset": "2026-10-01T00:00:00Z"}
        b = {"max_limit": 200, "current_usage": 100, "reset_duration": "1d", "last_reset": "2026-10-07T00:00:00Z",
             "source_name": "team"}
        snap = poll(make(handler=ok_handler({"virtual_key_name": "user-a@x.de", "budgets": [a, b]})))
        self.assertEqual((snap.m1, snap.m2), (100, 200))
        self.assertEqual(snap.r2, 12 * 3600)
        self.assertEqual(snap.note, "team a")

    def test_no_budget(self):
        snap = poll(make(handler=ok_handler({"virtual_key_name": "user-a@x.de", "budgets": []})))
        p = snap.to_payload()
        self.assertEqual((p["m1"], p["m2"]), (0, 0))
        self.assertTrue(p["ok"])
        self.assertNotIn("sh", p)
        self.assertNotIn("pace", p)

    def test_status_thresholds(self):
        d = copy.deepcopy(FIXTURE)
        d["budgets"][0]["current_usage"] = 14000
        self.assertEqual(poll(make(handler=ok_handler(d))).status, "near-limit")
        d["budgets"][0]["current_usage"] = 15000
        self.assertEqual(poll(make(handler=ok_handler(d))).status, "over-budget")

    def test_display_note_wins(self):
        snap = poll(make({"display_note": "Team"}, ok_handler(FIXTURE)))
        self.assertEqual(snap.note, "Team")

    def test_pace_positive_when_ahead(self):
        d = copy.deepcopy(FIXTURE)
        d["budgets"][0]["current_usage"] = 15000 * 0.25
        self.assertGreater(poll(make(handler=ok_handler(d))).pace, 0)


class SharesTests(unittest.TestCase):
    def test_grouping_over_versions_and_regions(self):
        sh = bifrost.compute_shares([
            {"model": "eu.anthropic.claude-opus-5", "total_cost": 50},
            {"model": "eu.anthropic.claude-opus-5-5", "total_cost": 30},
            {"model": "eu.anthropic.claude-sonnet-5", "total_cost": 20},
        ])
        self.assertEqual(sh, [{"slug": "Opus", "pct": 80}, {"slug": "Sonnet", "pct": 20}])

    def test_tiny_shares_fall_into_rest(self):
        sh = bifrost.compute_shares([
            {"model": "claude-opus", "total_cost": 90},
            {"model": "claude-sonnet", "total_cost": 8},
            {"model": "claude-haiku", "total_cost": 0.2},
            {"model": "gpt-5", "total_cost": 0.01},
        ])
        self.assertEqual([e["slug"] for e in sh], ["Opus", "Sonnet", "Rest"][:len(sh)])
        self.assertEqual(sum(e["pct"] for e in sh), 100)
        self.assertNotIn("Haiku", [e["slug"] for e in sh])
        self.assertNotIn("Andere", [e["slug"] for e in sh])

    def test_rest_with_rounded_zero_is_dropped(self):
        sh = bifrost.compute_shares(FIXTURE["budgets"][0]["per_model_usage"])
        self.assertEqual([e["slug"] for e in sh], ["Opus", "Sonnet"])
        self.assertEqual(sum(e["pct"] for e in sh), 100)

    def test_max_three_families_plus_rest(self):
        sh = bifrost.compute_shares([
            {"model": "opus", "total_cost": 40}, {"model": "sonnet", "total_cost": 30},
            {"model": "haiku", "total_cost": 20}, {"model": "gpt", "total_cost": 10},
        ])
        self.assertEqual([e["slug"] for e in sh], ["Opus", "Sonnet", "Haiku", "Rest"])
        self.assertEqual(sum(e["pct"] for e in sh), 100)

    def test_sum_always_100(self):
        sh = bifrost.compute_shares([
            {"model": "opus", "total_cost": 1}, {"model": "sonnet", "total_cost": 1},
            {"model": "haiku", "total_cost": 1}])
        self.assertEqual(sum(e["pct"] for e in sh), 100)

    def test_missing_or_zero(self):
        self.assertEqual(bifrost.compute_shares(None), [])
        self.assertEqual(bifrost.compute_shares([]), [])
        self.assertEqual(bifrost.compute_shares([{"model": "opus", "total_cost": 0}]), [])
        d = copy.deepcopy(FIXTURE)
        del d["budgets"][0]["per_model_usage"]
        self.assertNotIn("sh", poll(make(handler=ok_handler(d))).to_payload())


class ErrorTests(unittest.TestCase):
    def good_then(self, bad_handler):
        prov = make(handler=ok_handler(FIXTURE))
        first = poll(prov)
        prov._transport = httpx.MockTransport(bad_handler)
        return first, poll(prov), prov

    def test_401_403_5xx_keep_last_state_stale(self):
        for code in (401, 403, 500, 503):
            first, snap, _ = self.good_then(lambda r, c=code: httpx.Response(c, json={"error": "x"}))
            p = snap.to_payload()
            self.assertEqual(p["st"], "stale", code)
            self.assertFalse(p["ok"])
            self.assertEqual(p["m1"], first.to_payload()["m1"])
            self.assertEqual(p["m2"], 15000)
            self.assertIn("sh", p)

    def test_timeout_and_connect_error(self):
        def boom(request):
            raise httpx.ConnectTimeout("t")
        _, snap, _ = self.good_then(boom)
        self.assertEqual((snap.status, snap.ok), ("stale", False))

    def test_structure_errors(self):
        for body in ([1, 2], {"budgets": "nope"}, "text"):
            _, snap, _ = self.good_then(lambda r, b=body: httpx.Response(200, json=b))
            self.assertEqual((snap.status, snap.ok), ("stale", False))

    def test_invalid_json(self):
        _, snap, _ = self.good_then(lambda r: httpx.Response(200, content=b"<html>"))
        self.assertFalse(snap.ok)

    def test_stale_without_history_still_sent(self):
        snap = poll(make(handler=lambda r: httpx.Response(401, json={"error": "x"})))
        p = snap.to_payload()
        self.assertEqual((p["st"], p["ok"]), ("stale", False))

    def test_no_key_returns_none_and_logs_name_only(self):
        prov = make(handler=ok_handler(FIXTURE))
        logs = []
        prov.log = logs.append
        self.assertIsNone(poll(prov, key=None))
        self.assertTrue(any("BIFROST_TEST_KEY" in m for m in logs))

    def test_logs_never_contain_key(self):
        prov = make(handler=lambda r: httpx.Response(401, json={"error": "Missing or invalid virtual key"}))
        logs = []
        prov.log = logs.append
        poll(prov)
        prov._transport = httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("t")))
        poll(prov)
        self.assertTrue(logs)
        self.assertFalse(any(FAKE_KEY in m for m in logs))
        self.assertTrue(any("401" in m for m in logs))


if __name__ == "__main__":
    unittest.main()
