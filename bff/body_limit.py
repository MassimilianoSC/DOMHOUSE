"""F-2 (attack-from-outside review, 22 November 2026): a limit on the size of every request body, BEFORE anything reads
it. FastAPI parses a typed body before the access check, and the webhook read the whole body before its signature: a few
bodies of about 30 MiB (Cloud Run's HTTP/1 limit is 32 MiB) used up the 512 MiB of an instance. Pure ASGI, outermost:
a declared Content-Length over the limit is refused without reading; otherwise the body is collected here, piece by piece,
and refused as soon as it passes the limit (bodies in pieces carry no Content-Length). Under the limit the application
gets the same body in one message, then the server's own messages (the disconnect of a stream).

The limits, from the largest legitimate bodies measured on 22 November (rereading P-2, P-4; offline, with the engine's
own request builder of scripts/measure_model.py): the engines' way to the model, for an apartment of 200 devices (the
agent's MAX_DEVICES) with 10 long recent decisions, about 77 KiB (ASCII-escaped, with spaces; 71 KiB compact UTF-8):
256 KiB, more than 3 times. Everything else 64 KiB: every rule of an apartment changed at once 0.7 KiB, a copy of the
rules to 100 apartments 7.5 KiB, an agent's result a few KiB, an Italianway booking under 2 KiB. A typed body is parsed
before the access check, and a JSON body takes up to about 24 times its size once parsed (256 KiB of [{},…] about
6 MiB and 30 ms of CPU): so nothing reachable without an account parses more than 64 KiB.

Rereading R2 (the committente's full run of 22 November, agent_server_test::test_r2): Pub/Sub delivers again, forever,
a push that does not get a 2xx. So on the push of the agent's results (/internal/agent/risultati) a body over the limit
is acknowledged with 204 instead of 413: never read past the limit, never given to the route, and a warn line «agent
result ignored» with reason «troppo_grande», as the route does for a result it ignores. Every other path keeps 413.
That 204 comes before the signature check, so (a6, 22 November, as for the unsigned webhooks of F-5) at most 10 of those
lines a minute per instance; the others get the same 204 and are counted in one line once the minute is over."""
import time

from starlette.datastructures import Headers

from .logs import warn

WEBHOOK_LIMIT = 64 * 1024
AI_CHAT_LIMIT = 256 * 1024
DEFAULT_LIMIT = 64 * 1024
LIMITS = {"/webhooks/": WEBHOOK_LIMIT, "/internal/ai/chat": AI_CHAT_LIMIT}
ACKNOWLEDGED = {"/internal/agent/risultati"}                     # R2: Pub/Sub's pushes, 204 even when too large
ACKNOWLEDGED_LINES_PER_MINUTE = 10
_acknowledged: dict = {}        # {"window": minute, "lines": lines written in it, "skipped": calls without a line}
_clock = time.monotonic

_BODY = (b'{"error":"payload_too_large","message":"Richiesta troppo grande"}')


def _own_path(path: str, root_path: str) -> str:
    return path[len(root_path):] if root_path and path.startswith(root_path) else path


def limit_for(path: str, root_path: str = "") -> int:
    path = _own_path(path, root_path)
    for prefix, limit in LIMITS.items():
        if path.startswith(prefix):
            return limit
    return DEFAULT_LIMIT


async def _refuse(send) -> None:
    await send({"type": "http.response.start", "status": 413,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(_BODY)).encode()),
                            (b"connection", b"close")]})
    await send({"type": "http.response.body", "body": _BODY})


def _acknowledged_line() -> None:
    window = int(_clock() // 60)
    if _acknowledged.get("window") != window:
        if _acknowledged.get("skipped"):
            warn("agent results ignored, lines not written", reason="troppo_grande", calls=_acknowledged["skipped"])
        _acknowledged.update(window=window, lines=0, skipped=0)
    if _acknowledged["lines"] < ACKNOWLEDGED_LINES_PER_MINUTE:
        _acknowledged["lines"] += 1
        warn("agent result ignored", reason="troppo_grande")
    else:
        _acknowledged["skipped"] += 1


async def _acknowledge(send) -> None:
    _acknowledged_line()
    await send({"type": "http.response.start", "status": 204, "headers": [(b"connection", b"close")]})
    await send({"type": "http.response.body", "body": b""})


class BodyLimit:
    def __init__(self, app, root_path: str = ""):
        self.app, self.root_path = app, root_path

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = limit_for(scope["path"], self.root_path)
        too_large = _acknowledge if _own_path(scope["path"], self.root_path) in ACKNOWLEDGED else _refuse
        declared = Headers(scope=scope).get("content-length")
        if declared is not None:
            declared = declared.strip()
            if not (declared.isascii() and declared.isdigit()) or int(declared) > limit:   # «²» passes isdigit() alone
                return await too_large(send)
        # rereading P-1: one growing buffer, not a list of pieces (a body sent 2 bytes at a time cost about 21 times its
        # size as bytes objects and list entries)
        buffer = bytearray()
        while True:
            message = await receive()
            if message["type"] != "http.request":             # the client went away before the end: passed on
                first = message
                break
            buffer += message.get("body", b"")
            if len(buffer) > limit:
                return await too_large(send)
            if not message.get("more_body", False):
                first = {"type": "http.request", "body": bytes(buffer), "more_body": False}
                break
        buffer = None
        given = False

        async def replay():
            nonlocal given, first
            if not given:
                given = True
                message, first = first, None
                return message
            return await receive()

        await self.app(scope, replay, send)
