"""Socket-Lebenszyklus des IPC-Servers: kein Daemon entfernt den Socket eines anderen."""

import asyncio
import shutil
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from clawdmeter_daemon import ipc_server


def make_state():
    return ipc_server.ServerState(stop_event=asyncio.Event(), refresh_event=asyncio.Event(),
                                  reload_event=asyncio.Event())


def bind_foreign(path: Path) -> socket.socket:
    """Simuliert einen anderen Prozess, der unter ``path`` lauscht."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(str(path))
    s.listen(1)
    return s


@unittest.skipIf(sys.platform == "win32", "Unix-Sockets")
class SocketLifecycleTest(unittest.TestCase):
    def setUp(self):
        # Kurzer Pfad: macOS begrenzt AF_UNIX-Pfade auf ~104 Zeichen.
        self.dir = Path(tempfile.mkdtemp(dir="/tmp"))
        self.path = self.dir / "d.sock"
        patcher = mock.patch.object(ipc_server, "socket_path", return_value=self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.dir, True)
        ipc_server._bound_socket_id = None

    def test_second_daemon_does_not_steal_live_socket(self):
        async def run():
            first = await ipc_server.start(make_state())
            second = await ipc_server.start(make_state())
            self.assertIsNotNone(first)
            self.assertIsNone(second)
            self.assertTrue(ipc_server._socket_is_live(self.path))
            await ipc_server.stop(first)
            self.assertFalse(self.path.exists())
        asyncio.run(run())

    def test_stale_socket_is_replaced(self):
        stale = bind_foreign(self.path)
        stale.close()  # Datei bleibt liegen, niemand lauscht mehr
        self.assertTrue(self.path.exists())

        async def run():
            srv = await ipc_server.start(make_state())
            self.assertIsNotNone(srv)
            self.assertTrue(ipc_server._socket_is_live(self.path))
            await ipc_server.stop(srv)
        asyncio.run(run())

    def test_stop_keeps_socket_of_another_daemon(self):
        async def run():
            srv = await ipc_server.start(make_state())
            # Ein anderer Daemon hat den Pfad inzwischen neu gebunden.
            self.path.unlink()
            foreign = bind_foreign(self.path)
            try:
                await ipc_server.stop(srv)
                self.assertTrue(self.path.exists())
                self.assertTrue(ipc_server._socket_is_live(self.path))
            finally:
                foreign.close()
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
