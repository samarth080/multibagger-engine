"""Fail-closed network guard for static/offline build processes."""

from __future__ import annotations

import socket
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from unittest.mock import patch


class OfflineNetworkError(RuntimeError):
    pass


@dataclass
class NetworkAudit:
    attempted: bool = False
    target: str | None = None


@contextmanager
def deny_network():
    """Deny socket and urllib entry points, including provider/RSS clients."""
    audit = NetworkAudit()

    def blocked(*args, **kwargs):
        audit.attempted = True
        audit.target = repr(args[0]) if args else "unknown"
        raise OfflineNetworkError(
            f"network access is forbidden during an offline build: {audit.target}"
        )

    with (
        patch.object(socket, "create_connection", blocked),
        patch.object(socket.socket, "connect", blocked),
        patch.object(socket.socket, "connect_ex", blocked),
        patch.object(urllib.request, "urlopen", blocked),
    ):
        yield audit
