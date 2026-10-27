# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""A reset during Windows socket shutdown must still release the connection."""
from __future__ import annotations

import asyncio
import socket
import struct
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

if sys.platform == "win32":
    from texstage.server.windows_loop import ProactorEventLoop, _SocketTransport


@unittest.skipUnless(sys.platform == "win32", "Windows Proactor transport")
class WindowsCleanupTests(unittest.TestCase):
    def transport(self, shutdown_error=None, protocol_error=None):
        sock, protocol, server = Mock(), Mock(), Mock()
        sock.fileno.return_value = 42
        sock.shutdown.side_effect = shutdown_error
        protocol.connection_lost.side_effect = protocol_error
        transport = SimpleNamespace(_sock=sock, _protocol=protocol, _server=server,
                                    _called_connection_lost=False)
        return transport, sock, protocol, server

    def assert_released(self, transport, sock, protocol, server):
        sock.close.assert_called_once()
        protocol.connection_lost.assert_called_once_with(None)
        server._detach.assert_called_once_with(transport)
        self.assertIsNone(transport._sock)
        self.assertIsNone(transport._server)
        self.assertTrue(transport._called_connection_lost)
        _SocketTransport._call_connection_lost(transport, None)
        sock.close.assert_called_once()
        protocol.connection_lost.assert_called_once()

    def test_peer_reset_during_shutdown_still_releases_socket(self):
        values = self.transport(ConnectionResetError(0, "peer reset", None, 10054))
        _SocketTransport._call_connection_lost(values[0], None)
        self.assert_released(*values)

    def test_normal_close(self):
        values = self.transport()
        _SocketTransport._call_connection_lost(values[0], None)
        self.assert_released(*values)

    def test_other_shutdown_errors_remain_visible(self):
        for error in (OSError(0, "other failure", None, 10022), ConnectionResetError("unspecified")):
            with self.subTest(error=error):
                values = self.transport(error)
                with self.assertRaises(OSError) as caught:
                    _SocketTransport._call_connection_lost(values[0], None)
                self.assertIs(caught.exception, error)
                self.assert_released(*values)

    def test_protocol_errors_remain_visible_even_if_shutdown_resets(self):
        error = ConnectionResetError(0, "application failure", None, 10054)
        values = self.transport(ConnectionResetError(0, "shutdown reset", None, 10054), error)
        with self.assertRaises(ConnectionResetError) as caught:
            _SocketTransport._call_connection_lost(values[0], None)
        self.assertIs(caught.exception, error)
        self.assert_released(*values)

    def test_real_connections_can_reset_and_reconnect(self):
        async def exercise():
            loop = asyncio.get_running_loop()
            errors, transports, lost = [], [], []
            loop.set_exception_handler(lambda loop, context: errors.append(context))

            class Protocol(asyncio.Protocol):
                def connection_made(self, transport):
                    self.transport = transport
                    transports.append(transport)

                def data_received(self, data):
                    self.transport.write(data)

                def connection_lost(self, exc):
                    lost.append(exc)

            listener = await loop.create_server(Protocol, "127.0.0.1", 0)
            address = listener.sockets[0].getsockname()
            try:
                for count in range(10):
                    client = socket.socket()
                    client.setblocking(False)
                    try:
                        await loop.sock_connect(client, address)
                        await loop.sock_sendall(client, b"reset")
                        self.assertEqual(await loop.sock_recv(client, 5), b"reset")
                        client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("HH", 1, 0))
                    finally:
                        client.close()
                    async with asyncio.timeout(3):
                        while len(lost) <= count:
                            await asyncio.sleep(0.01)
                reader, writer = await asyncio.open_connection(*address)
                writer.write(b"still serving")
                await writer.drain()
                self.assertEqual(await reader.readexactly(13), b"still serving")
                writer.close()
                await writer.wait_closed()
            finally:
                for transport in transports:
                    transport.close()
                listener.close()
                await asyncio.wait_for(listener.wait_closed(), 3)
            self.assertFalse(errors, errors)
            self.assertTrue(all(transport._sock is None for transport in transports))

        with asyncio.Runner(loop_factory=ProactorEventLoop) as runner:
            runner.run(exercise())


if __name__ == "__main__":
    unittest.main()
