"""Where a call to the model stops (the committente's instruction on the measure, lot 30): a separate connection timeout
and, for every failure, the phase it stopped in: «DNS», «connessione» (TCP), «TLS», «invio della richiesta», «attesa
della risposta» (no first byte of the answer within the read timeout), «lettura della risposta». «No answer» becomes
one of these. Used by bff/ai_gateway.py (the BFF's calls to Agent Platform) and scripts/measure_model.py.

How: the host is resolved first, timed, with the connection timeout (so a slow DNS is told apart from a slow TCP
connect); then httpx with httpx.Timeout(read, connect=connect) and httpcore's «trace» extension, which reports each
step started and completed: the step started and not completed when the error comes is the phase.
"""
import asyncio
import time
from urllib.parse import urlsplit

import httpx

DNS, CONNECT, TLS, SEND, WAIT, READ = ("DNS", "connessione", "TLS", "invio della richiesta", "attesa della risposta",
                                       "lettura della risposta")
_STEPS = {"connect_tcp": CONNECT, "start_tls": TLS, "send_request_headers": SEND, "send_request_body": SEND,
          "receive_response_headers": WAIT, "receive_response_body": READ}
_DNS_WORDS = ("getaddrinfo", "name or service not known", "nodename nor servname", "no address associated",
              "temporary failure in name resolution", "11001", "11004")


class PhaseFailure(Exception):
    """A call that failed: the phase, whether it was a timeout, and how long it lasted."""

    def __init__(self, phase: str, timeout: bool, seconds: float, cause: BaseException):
        super().__init__(f"{'tempo scaduto' if timeout else 'errore'} nella fase «{phase}» dopo {seconds:.1f} s "
                         f"({type(cause).__name__})")
        self.phase, self.timeout, self.seconds, self.cause = phase, timeout, seconds, cause


class Tracker:
    """httpcore's trace events -> the step in progress, and the duration of the completed ones (seconds)."""

    def __init__(self):
        self.current: str | None = None
        self.started: dict[str, float] = {}
        self.took: dict[str, float] = {}

    async def hook(self, name: str, info: dict) -> None:
        parts = name.split(".")
        step, state = parts[-2], parts[-1]
        if step not in _STEPS:
            return
        if state == "started":
            self.current = step
            self.started[step] = time.monotonic()
        elif state in ("complete", "failed"):
            self.took[step] = time.monotonic() - self.started.get(step, time.monotonic())
            if state == "complete" and self.current == step:
                self.current = None

    def phase(self, exc: BaseException) -> str:
        if any(w in str(exc).lower() for w in _DNS_WORDS):
            return DNS
        if self.current in _STEPS:
            return _STEPS[self.current]
        return phase_of(exc)


def phase_of(exc: BaseException) -> str:
    """The phase from the exception's type alone (when there is no trace, e.g. a fake in the tests)."""
    if any(w in str(exc).lower() for w in _DNS_WORDS):
        return DNS
    if isinstance(exc, (httpx.ConnectTimeout, httpx.ConnectError, httpx.PoolTimeout)):
        return TLS if "ssl" in str(exc).lower() or "certificate" in str(exc).lower() else CONNECT
    if isinstance(exc, httpx.WriteTimeout | httpx.WriteError):
        return SEND
    if isinstance(exc, httpx.ReadTimeout):
        return WAIT
    if isinstance(exc, httpx.RemoteProtocolError | httpx.ReadError):
        return READ
    return WAIT


async def post_traced(url: str, *, json: dict, headers: dict, connect_s: float, read_s: float,
                      network: dict | None = None) -> httpx.Response:
    """POST with the phases watched. Raises PhaseFailure; `network` (if given) receives the seconds of «dns»,
    «connessione», «tls» of a call that got that far."""
    tracker = Tracker()
    parts = urlsplit(url)
    started = time.monotonic()
    loop = asyncio.get_running_loop()
    try:
        await asyncio.wait_for(loop.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80)),
                               timeout=connect_s)
    except (TimeoutError, OSError) as exc:
        raise PhaseFailure(DNS, isinstance(exc, TimeoutError), time.monotonic() - started, exc) from None
    if network is not None:
        network["dns"] = time.monotonic() - started
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(read_s, connect=connect_s, write=connect_s,
                                                           pool=connect_s)) as client:
            resp = await client.post(url, json=json, headers=headers, extensions={"trace": tracker.hook})
    except httpx.HTTPError as exc:
        raise PhaseFailure(tracker.phase(exc), isinstance(exc, httpx.TimeoutException), time.monotonic() - started,
                           exc) from None
    if network is not None:
        network["connessione"] = tracker.took.get("connect_tcp", 0.0)
        network["tls"] = tracker.took.get("start_tls", 0.0)
    return resp
