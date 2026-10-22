"""bff/net_phase.py (lot 30, the committente's instruction on the measure): a separate connection timeout and, for
every failure, its phase, with real sockets on this machine: no first byte of the answer = «attesa della risposta»;
a closed port = «connessione»; a name that does not resolve = «DNS»; a server that never speaks TLS = «TLS»."""
import asyncio
import socket

import pytest

from bff import net_phase


def run(coro):
    return asyncio.run(coro)


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


async def silent_server():
    """Accepts connections and never writes a byte."""
    async def handle(reader, writer):
        await reader.read(-1)                       # silent until the client gives up and closes
        writer.close()
    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


def test_no_answer_is_waiting_for_the_answer():
    async def main():
        server, port = await silent_server()
        async with server:
            with pytest.raises(net_phase.PhaseFailure) as exc:
                await net_phase.post_traced(f"http://127.0.0.1:{port}/x", json={}, headers={}, connect_s=1, read_s=0.3)
        return exc.value
    failure = run(main())
    assert (failure.phase, failure.timeout) == (net_phase.WAIT, True) and 0.25 < failure.seconds < 2


def test_a_server_that_never_speaks_tls_stops_in_tls():
    async def main():
        server, port = await silent_server()
        async with server:
            with pytest.raises(net_phase.PhaseFailure) as exc:
                await net_phase.post_traced(f"https://127.0.0.1:{port}/x", json={}, headers={}, connect_s=0.3, read_s=5)
        return exc.value
    failure = run(main())
    assert (failure.phase, failure.timeout) == (net_phase.TLS, True)


def test_a_closed_port_is_the_connection():
    port = free_port()
    with pytest.raises(net_phase.PhaseFailure) as exc:
        run(net_phase.post_traced(f"http://127.0.0.1:{port}/x", json={}, headers={}, connect_s=1, read_s=1))
    assert exc.value.phase == net_phase.CONNECT          # refused at once on Linux, after the timeout on Windows


def test_a_name_that_does_not_resolve_is_dns():
    with pytest.raises(net_phase.PhaseFailure) as exc:
        run(net_phase.post_traced("https://domhouse-prova.invalid/x", json={}, headers={}, connect_s=3, read_s=1))
    assert exc.value.phase == net_phase.DNS


def test_an_answer_reports_the_network_times():
    async def main():
        async def handle(reader, writer):
            await reader.readuntil(b"\r\n\r\n")
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{}")
            await writer.drain()
            writer.close()
        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        network = {}
        async with server:
            resp = await net_phase.post_traced(f"http://127.0.0.1:{port}/x", json={}, headers={}, connect_s=1,
                                               read_s=1, network=network)
        return resp, network
    resp, network = run(main())
    assert resp.status_code == 200 and resp.json() == {}
    assert set(network) == {"dns", "connessione", "tls"} and network["tls"] == 0.0


def test_the_phase_from_the_exception_alone():
    import httpx
    assert net_phase.phase_of(httpx.ReadTimeout("x")) == net_phase.WAIT
    assert net_phase.phase_of(httpx.ConnectTimeout("x")) == net_phase.CONNECT
    assert net_phase.phase_of(httpx.ConnectError("[Errno 11001] getaddrinfo failed")) == net_phase.DNS
    assert net_phase.phase_of(httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED]")) == net_phase.TLS
