"""Ordinary tests cannot resolve names or make real connections, even with live opt-in."""

import socket

import pytest


@pytest.mark.parametrize("operation", ["connect", "connect_ex", "create_connection", "getaddrinfo"])
def test_unmarked_tests_have_no_network_access(operation: str) -> None:
    with pytest.raises(RuntimeError, match="Offline tests cannot open network"):
        if operation in {"connect", "connect_ex"}:
            with socket.socket() as connection:
                getattr(connection, operation)(("127.0.0.1", 11434))
        elif operation == "create_connection":
            socket.create_connection(("127.0.0.1", 11434))
        else:
            socket.getaddrinfo("example.invalid", 443)
