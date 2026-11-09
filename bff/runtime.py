"""D-198 (E-27): what each process says about itself in the log, so that a replaced instance, its streams and a stalled
event loop can be read minute by minute. Never a token, an email or a person: these lines are written in an empty
context, because the request's would add the user.

    process started | process got SIGTERM | process stopping     boot_id, revision (K_REVISION), pid, uptime_s
    stream opened | stream closed                                boot_id, stream_id, apartment_id, seconds, reason
    process status (every STATUS_LOG_S)                          boot_id, streams_open, requests_active, queue_max,
                                                                 loop_lag_ms (the worst of the period)

The reason of a closed stream: max_duration, client_disconnect, queue_full, apartment_removed, access_ended, error.
"""
import asyncio
import contextvars
import os
import secrets
import signal
import threading
import time

from .logs import info

BOOT_ID = secrets.token_hex(4)
_started = time.monotonic()
_streams: dict[str, float] = {}
_requests = 0


def _say(message: str, **fields) -> None:
    contextvars.Context().run(info, message, boot_id=BOOT_ID, **fields)


def process_started() -> None:
    _say("process started", revision=os.environ.get("K_REVISION", ""), pid=os.getpid())


def process_stopping() -> None:
    _say("process stopping", uptime_s=round(time.monotonic() - _started), streams_open=len(_streams))


def watch_sigterm():
    """Notes the signal, then lets uvicorn do what it does. Returns what puts things back (nothing outside the main
    thread, where a handler cannot be set)."""
    if threading.current_thread() is not threading.main_thread():
        return lambda: None
    previous = signal.getsignal(signal.SIGTERM)

    def handler(signum, frame):
        _say("process got SIGTERM", uptime_s=round(time.monotonic() - _started), streams_open=len(_streams))
        if callable(previous):
            previous(signum, frame)
    signal.signal(signal.SIGTERM, handler)
    return lambda: signal.signal(signal.SIGTERM, previous)


def stream_opened(apartment_id: str) -> str:
    stream_id = secrets.token_hex(4)
    _streams[stream_id] = time.monotonic()
    _say("stream opened", stream_id=stream_id, apartment_id=apartment_id)
    return stream_id


def stream_closed(stream_id: str, apartment_id: str, reason: str) -> None:
    seconds = time.monotonic() - _streams.pop(stream_id, time.monotonic())
    _say("stream closed", stream_id=stream_id, apartment_id=apartment_id, seconds=round(seconds, 1), reason=reason)


class RequestCounter:
    """The HTTP requests in progress, streams included. Pure ASGI, so the streams keep streaming. Not the built-in
    engine's on /mock: they come from this same process, on loopback, and Cloud Run does not count them."""

    def __init__(self, app, root_path: str = ""):
        self.app, self.mock = app, f"{root_path}/mock"

    async def __call__(self, scope, receive, send):
        global _requests
        if scope["type"] != "http" or scope["path"].startswith(self.mock):
            return await self.app(scope, receive, send)
        _requests += 1
        try:
            await self.app(scope, receive, send)
        finally:
            _requests -= 1


def requests_active() -> int:
    return _requests


def _queue_max() -> int:
    from .sse_hub import hub_manager
    return max((q.qsize() for hub in hub_manager.hubs.values() for q in hub.subscribers), default=0)


async def status_loop(every_s: float, tick_s: float = 0.5) -> None:
    """Every tick the sleep is timed: what it took beyond tick_s is how long the event loop was busy with something else."""
    loop = asyncio.get_running_loop()
    worst, last, since = 0.0, loop.time(), loop.time()
    while True:
        await asyncio.sleep(tick_s)
        now = loop.time()
        worst, last = max(worst, now - last - tick_s), now
        if now - since >= every_s:
            _say("process status", streams_open=len(_streams), requests_active=_requests, queue_max=_queue_max(),
                 loop_lag_ms=round(worst * 1000))
            worst, since = 0.0, now
