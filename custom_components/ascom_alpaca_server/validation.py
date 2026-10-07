"""Checks for the options flow, without Home Assistant imports so that they can be tested."""

from __future__ import annotations

import os
import socket


def port_is_free(port: int) -> bool:
    """True if a TCP server can listen on the port (on all interfaces)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if os.name != "nt":
            # like the server: a port in TIME_WAIT after a restart is free, a listening one is not.
            # (On Windows this option would let a second server share the port.)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True


def switch_name_errors(names: dict[str, str]) -> dict[str, str]:
    """The names of the switches that cannot be used: ``{entity_id: translation key}``.

    Astronomy software tells the switches apart by their names: a name must not be empty and must not
    be used twice (not case-sensitive).
    """
    errors: dict[str, str] = {}
    seen: dict[str, list[str]] = {}
    for entity_id, name in names.items():
        key = str(name).strip().casefold()
        if not key:
            errors[entity_id] = "name_empty"
        else:
            seen.setdefault(key, []).append(entity_id)

    for entity_ids in seen.values():
        if len(entity_ids) > 1:
            for entity_id in entity_ids:
                errors[entity_id] = "name_duplicate"
    return errors
