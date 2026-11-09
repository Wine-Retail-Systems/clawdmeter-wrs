"""Der Daemon muss sich auch dann beenden, wenn BLE hängt oder der
PyInstaller-Bootloader (Elternprozess) verschwunden ist."""

import asyncio
import threading
import unittest
from unittest import mock

from clawdmeter_daemon import polling


class HangingClient:
    """BleakClient-Ersatz, dessen connect() nie zurückkehrt (CoreBluetooth
    nach Ruhezustand)."""

    async def connect(self):
        await asyncio.Event().wait()


class QuickClient:
    async def connect(self):
        return True


class ConnectOrStopTest(unittest.TestCase):
    def test_stop_event_aborts_hanging_connect(self):
        async def run():
            stop = asyncio.Event()
            asyncio.get_running_loop().call_later(0.05, stop.set)
            return await asyncio.wait_for(
                polling._connect_or_stop(HangingClient(), stop, timeout=30), 2
            )
        self.assertFalse(asyncio.run(run()))

    def test_hanging_connect_times_out(self):
        async def run():
            await polling._connect_or_stop(HangingClient(), asyncio.Event(), timeout=0.05)
        with self.assertRaises(asyncio.TimeoutError):
            asyncio.run(asyncio.wait_for(run(), 2))

    def test_successful_connect(self):
        async def run():
            return await polling._connect_or_stop(QuickClient(), asyncio.Event(), timeout=1)
        self.assertTrue(asyncio.run(run()))


class ParentWatchdogTest(unittest.TestCase):
    def test_reparenting_sets_stop_event(self):
        ppids = iter([4711, 4711, 1])

        async def run():
            stop = asyncio.Event()
            await asyncio.wait_for(
                polling._watch_parent(stop, 4711, getppid=lambda: next(ppids), interval=0.01),
                2,
            )
            return stop.is_set()
        self.assertTrue(asyncio.run(run()))

    def test_watchdog_returns_when_stopped(self):
        async def run():
            stop = asyncio.Event()
            stop.set()
            await asyncio.wait_for(
                polling._watch_parent(stop, 4711, getppid=lambda: 4711, interval=0.01), 2
            )
        asyncio.run(run())


class ShutdownDeadlineTest(unittest.TestCase):
    def test_deadline_forces_exit(self):
        called = threading.Event()
        exit_fn = mock.Mock(side_effect=lambda code: called.set())
        timer = polling._start_shutdown_deadline(0.05, exit_fn=exit_fn)
        self.assertTrue(called.wait(2))
        exit_fn.assert_called_once_with(1)
        self.assertTrue(timer.daemon)


if __name__ == "__main__":
    unittest.main()
