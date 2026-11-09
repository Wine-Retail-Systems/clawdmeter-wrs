"""`status` muss den echten BLE-Verbindungsstand und den letzten Poll melden,
nicht feste Platzhalter."""

import asyncio
import unittest
from datetime import datetime
from unittest import mock

from clawdmeter_daemon import ipc_server, polling


def _state() -> ipc_server.ServerState:
    return ipc_server.ServerState(
        stop_event=asyncio.Event(),
        refresh_event=asyncio.Event(),
        reload_event=asyncio.Event(),
    )


class _FakeProvider:
    slot_id = "fake"
    poll_seconds = 60

    async def poll(self):
        return None


class StatusFieldsTest(unittest.TestCase):
    def test_defaults_before_any_activity(self):
        async def run():
            return await ipc_server._status(_state(), {})
        result = asyncio.run(run())
        self.assertFalse(result["device_connected"])
        self.assertIsNone(result["last_poll_at"])

    def test_reports_device_connected_flag(self):
        async def run():
            st = _state()
            st.device_connected = True
            return await ipc_server._status(st, {})
        self.assertTrue(asyncio.run(run())["device_connected"])

    def test_last_poll_at_is_newest_poll_as_iso(self):
        async def run():
            st = _state()
            a = polling.ProviderState(_FakeProvider())
            b = polling.ProviderState(_FakeProvider())
            a.last_polled_at = 1_000_000.0
            b.last_polled_at = 2_000_000.0
            st.provider_states_ref = [a, b]
            return await ipc_server._status(st, {})
        value = asyncio.run(run())["last_poll_at"]
        parsed = datetime.fromisoformat(value)
        self.assertIsNotNone(parsed.tzinfo)
        self.assertEqual(parsed.timestamp(), 2_000_000.0)

    def test_schedule_records_poll_time(self):
        s = polling.ProviderState(_FakeProvider())
        self.assertIsNone(s.last_polled_at)
        with mock.patch.object(polling.time, "time", return_value=123.0):
            s.schedule(ok=False)
        self.assertEqual(s.last_polled_at, 123.0)


class _Client:
    """Verbindet sofort; `is_connected` protokolliert den Status-Stand und
    meldet nach der ersten Loop-Prüfung einen Verbindungsabbruch."""

    def __init__(self, ipc_state):
        self._ipc_state = ipc_state
        self._checks = 0
        self.seen = []

    async def connect(self):
        return True

    async def disconnect(self):
        return True

    @property
    def is_connected(self):
        self._checks += 1
        self.seen.append(self._ipc_state.device_connected)
        return self._checks <= 2


class _Session:
    def __init__(self, _client):
        self.refresh_requested = asyncio.Event()

    async def setup_refresh_subscription(self):
        return None


class ConnectAndRunStatusTest(unittest.TestCase):
    def test_flag_set_while_connected_and_cleared_after(self):
        async def run():
            st = _state()
            st.subscribers = []
            client = _Client(st)
            with mock.patch.object(polling, "BleakClient", lambda _a: client), \
                 mock.patch.object(polling.ble, "Session", _Session), \
                 mock.patch.object(polling.ble, "log"), \
                 mock.patch.object(polling, "TICK", 0.01):
                await polling.connect_and_run(
                    "addr", None, [], st.stop_event, st.refresh_event,
                    st.reload_event, ipc_state=st,
                )
            return st, client
        st, client = asyncio.run(run())
        # Zweite Prüfung ist die Loop-Bedingung: dort muss das Flag stehen.
        self.assertEqual(client.seen[1], True)
        self.assertFalse(st.device_connected)


class _Snap:
    def __init__(self, ok=True, status="ok"):
        self.ok = ok
        self.status = status

    def to_payload(self):
        return {"ok": self.ok}


class _Provider:
    poll_seconds = 60

    def __init__(self, slot_id, result):
        self.slot_id = slot_id
        self._result = result

    async def poll(self):
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class _SendSession:
    async def send_cycle(self, _payloads):
        return True


class PollEventsTest(unittest.TestCase):
    def _run(self, providers):
        events = []

        async def fake_emit(_state, name, data):
            events.append((name, data))

        async def run():
            st = _state()
            states = [polling.ProviderState(p) for p in providers]
            with mock.patch.object(polling.ipc_server, "emit_event", fake_emit), \
                 mock.patch("sys.stderr"):
                await polling.run_cycle(_SendSession(), states, True, ipc_state=st)
        asyncio.run(run())
        return events

    def test_success_event(self):
        events = self._run([_Provider("anthropic", _Snap())])
        self.assertEqual(len(events), 1)
        name, data = events[0]
        self.assertEqual(name, "poll-success")
        self.assertEqual(data["provider"], "anthropic")
        self.assertIsNotNone(datetime.fromisoformat(data["at"]).tzinfo)

    def test_error_events(self):
        events = self._run([
            _Provider("codex", _Snap(ok=False, status="auth")),
            _Provider("bedrock", None),
            _Provider("langdock", RuntimeError("boom")),
        ])
        self.assertEqual([e[0] for e in events], ["poll-error"] * 3)
        self.assertEqual(
            [(e[1]["provider"], e[1]["error"]) for e in events],
            [("codex", "auth"), ("bedrock", "keine Daten"), ("langdock", "boom")],
        )

    def test_no_events_without_ipc_state(self):
        async def run():
            states = [polling.ProviderState(_Provider("a", _Snap()))]
            with mock.patch.object(polling.ipc_server, "emit_event") as emit:
                await polling.run_cycle(_SendSession(), states, True)
                return emit.call_count
        self.assertEqual(asyncio.run(run()), 0)


if __name__ == "__main__":
    unittest.main()
