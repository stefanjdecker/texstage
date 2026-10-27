# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Windows socket cleanup for the standalone server.

CPython's Proactor socket transport calls shutdown before close, but a peer's TCP
reset can make shutdown raise WinError 10054 and skip close/detach entirely. Keep
the Proactor loop (including its support for large classes); tolerate that reset
only during shutdown. No global asyncio patch or exception filter is installed.

The two transport hooks below follow asyncio.proactor_events in Python 3.12-3.14.
Keep the Windows regression tests when updating the supported Python versions.
"""
from __future__ import annotations

import asyncio
import socket
from asyncio.proactor_events import _ProactorSocketTransport


class _SocketTransport(_ProactorSocketTransport):
    def _call_connection_lost(self, exc):
        if self._called_connection_lost:
            return
        try:
            self._protocol.connection_lost(exc)
        finally:
            try:
                if self._sock.fileno() != -1:
                    try:
                        self._sock.shutdown(socket.SHUT_RDWR)
                    except ConnectionResetError as error:
                        if getattr(error, "winerror", None) != 10054:
                            raise
            finally:
                self._sock.close()
                self._sock = None
                if self._server is not None:
                    self._server._detach(self)
                    self._server = None
                self._called_connection_lost = True


class ProactorEventLoop(asyncio.ProactorEventLoop):
    def _make_socket_transport(self, sock, protocol, waiter=None, extra=None, server=None):
        return _SocketTransport(self, sock, protocol, waiter, extra, server)
