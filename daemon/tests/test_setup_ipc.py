import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from clawdmeter_daemon import config, ipc_server, paths, secrets, setup_wizard

TOKEN = "sk-bf-0123456789abcdefghijWXYZ"  # fake test token


class HomeCase(unittest.TestCase):
    """Run every test with an isolated HOME so real user config is untouched."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        env = {"HOME": str(self.home), "USERPROFILE": str(self.home),
               "APPDATA": str(self.home / "AppData"), "LOCALAPPDATA": str(self.home / "Local")}
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        for k in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CONFIG_DIR", "BIFROST_VIRTUAL_KEY"):
            os.environ.pop(k, None)
        self.addCleanup(self._tmp.cleanup)
        self.assertTrue(str(paths.config_file()).startswith(str(self.home)))

    def write_settings(self, env):
        d = self.home / ".claude"
        d.mkdir(parents=True, exist_ok=True)
        (d / "settings.json").write_text(json.dumps({"env": env}))


class DetectTests(HomeCase):
    def test_none(self):
        d = setup_wizard.detect_bifrost()
        self.assertFalse(d["detected"])
        self.assertIsNone(d["masked"])

    def test_settings_json(self):
        self.write_settings({"ANTHROPIC_AUTH_TOKEN": TOKEN,
                             "ANTHROPIC_BASE_URL": "https://gw.example/anthropic"})
        d = setup_wizard.detect_bifrost()
        self.assertTrue(d["detected"])
        self.assertTrue(d["source"].endswith("settings.json"))
        self.assertEqual(d["base_url"], "https://gw.example")
        self.assertEqual(d["masked"], "sk-bf-…WXYZ")
        self.assertNotIn(TOKEN, json.dumps(d))

    def test_env_wins_and_default_url(self):
        self.write_settings({"ANTHROPIC_AUTH_TOKEN": "sk-bf-fromsettings000000"})
        with mock.patch.dict(os.environ, {"ANTHROPIC_AUTH_TOKEN": TOKEN}):
            d = setup_wizard.detect_bifrost()
        self.assertEqual(d["source"], "env:ANTHROPIC_AUTH_TOKEN")
        self.assertEqual(d["base_url"], "https://llm-gw.wineretailsystems.cloud")

    def test_non_bifrost_token_ignored(self):
        self.write_settings({"ANTHROPIC_AUTH_TOKEN": "sk-ant-oat01-xxxxxxxx"})
        self.assertFalse(setup_wizard.detect_bifrost()["detected"])

    def test_broken_settings(self):
        d = self.home / ".claude"
        d.mkdir()
        (d / "settings.json").write_text("{not json")
        self.assertFalse(setup_wizard.detect_bifrost()["detected"])


class DefaultConfigTests(HomeCase):
    def test_default_config_has_bifrost_block_and_no_opencode(self):
        cfg = config.load_config()
        ids = [p.id for p in cfg.providers]
        self.assertIn("bifrost", ids)
        self.assertNotIn("opencode", ids)
        b = next(p for p in cfg.providers if p.id == "bifrost")
        self.assertFalse(b.enabled)
        self.assertEqual(b.poll_seconds, 120)
        self.assertEqual(b.display_name, "LLM Gateway")
        self.assertEqual(b.get("api_key_env"), "BIFROST_VIRTUAL_KEY")
        self.assertNotIn("sk-bf-0", paths.config_file().read_text())


def make_state():
    return ipc_server.ServerState(stop_event=asyncio.Event(), refresh_event=asyncio.Event(),
                                  reload_event=asyncio.Event())


def call(command, args, state=None):
    state = state or make_state()
    h = ipc_server.HANDLERS[command]
    return asyncio.run(h(state, args)), state


class IpcTests(HomeCase):
    def block(self):
        cfg = config.load_config()
        return next(p for p in cfg.providers if p.id == "bifrost").raw

    def test_detect_contract(self):
        self.write_settings({"ANTHROPIC_AUTH_TOKEN": TOKEN, "ANTHROPIC_BASE_URL": "https://gw.example/x"})
        res, _ = call("provider-detect", {"id": "bifrost"})
        self.assertEqual(set(res), {"id", "detected", "source", "notes", "masked", "base_url"})
        self.assertEqual(res["id"], "bifrost")
        self.assertTrue(res["detected"])
        self.assertNotIn(TOKEN, json.dumps(res))

    def test_save_with_source_inside_fields_copies_key(self):
        self.write_settings({"ANTHROPIC_AUTH_TOKEN": TOKEN, "ANTHROPIC_BASE_URL": "https://gw.example/anthropic"})
        res, state = call("provider-save", {"id": "bifrost", "fields": {"source": "claude-settings"}})
        self.assertTrue(res["saved"], res)
        self.assertEqual(res["masked"], "sk-bf-…WXYZ")
        self.assertNotIn(TOKEN, json.dumps(res))
        self.assertEqual(secrets.read_all()["BIFROST_VIRTUAL_KEY"], TOKEN)
        self.assertEqual(os.environ["BIFROST_VIRTUAL_KEY"], TOKEN)
        self.assertEqual(os.stat(paths.secrets_file()).st_mode & 0o777, 0o600)
        cfg_text = paths.config_file().read_text()
        self.assertNotIn(TOKEN, cfg_text)
        self.assertNotIn("source", cfg_text)
        b = self.block()
        self.assertTrue(b["enabled"])
        self.assertEqual(b["api_key_env"], "BIFROST_VIRTUAL_KEY")
        self.assertEqual(b["base_url"], "https://gw.example")
        self.assertEqual(b["poll_seconds"], 120)
        self.assertEqual(b["display_name"], "LLM Gateway")
        self.assertTrue(state.reload_event.is_set())

    def test_save_source_without_detectable_key_fails(self):
        res, state = call("provider-save", {"id": "bifrost", "fields": {"source": "claude-settings"}})
        self.assertFalse(res["saved"])
        self.assertFalse(state.reload_event.is_set())

    def test_foreign_source_value_never_written(self):
        res, _ = call("provider-save", {"id": "bifrost", "fields": {"source": "Shell-Env", "api_key_env": "BIFROST_VIRTUAL_KEY"}})
        self.assertTrue(res["saved"])
        self.assertNotIn("source", self.block())
        self.assertNotIn("BIFROST_VIRTUAL_KEY", secrets.read_all())

    def test_manual_flow_secret_write_then_save(self):
        res, _ = call("secret-write", {"key": "BIFROST_VIRTUAL_KEY", "value": TOKEN})
        self.assertTrue(res["saved"])
        res, _ = call("provider-save", {"id": "bifrost", "fields": {"api_key_env": "BIFROST_VIRTUAL_KEY"}})
        self.assertTrue(res["saved"])
        b = self.block()
        self.assertEqual(b["base_url"], "https://llm-gw.wineretailsystems.cloud")
        self.assertTrue(b["enabled"])
        self.assertNotIn(TOKEN, paths.config_file().read_text())

    def test_bad_base_url_rejected(self):
        res, _ = call("provider-save", {"id": "bifrost", "fields": {"base_url": "ftp://x"}})
        self.assertFalse(res["saved"])

    def test_other_providers_keep_source_field(self):
        res, _ = call("provider-save", {"id": "langdock", "fields": {"source": "Shell-Env", "api_key_env": "LANGDOCK_API_KEY"}})
        self.assertTrue(res["saved"])
        raw = next(p for p in config.load_config().providers if p.id == "langdock").raw
        self.assertEqual(raw["source"], "Shell-Env")  # unchanged legacy behaviour

    def test_opencode_rejected(self):
        res, _ = call("provider-save", {"id": "opencode", "fields": {}})
        self.assertFalse(res["saved"])
        res, _ = call("provider-detect", {"id": "opencode"})
        self.assertFalse(res["detected"])


if __name__ == "__main__":
    unittest.main()
