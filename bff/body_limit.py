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
6 MiB and 30 ms of CPU): so nothing reachable without an account parses more than 64 KiB."""
from starlette.datastructures import Headers

WEBHOOK_LIMIT = 64 * 1024
AI_CHAT_LIMIT = 256 * 1024
DEFAULT_LIMIT = 64 * 1024
LIMITS = {"/webhooks/": WEBHOOK_LIMIT, "/internal/ai/chat": AI_CHAT_LIMIT}

_BODY = (b'{"error":"payload_too_large","message":"Richiesta troppo grande"}')


def limit_for(path: str, root_path: str = "") -> int:
    if root_path and path.startswith(root_path):
        path = path[len(root_path):]
    for prefix, limit in LIMITS.items():
        if path.startswith(prefix):
            return limit
    return DEFAULT_LIMIT


async def _refuse(send) -> None:
    await send({"type": "http.response.start", "status": 413,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(_BODY)).encode()),
                            (b"connection", b"close")]})
    await send({"type": "http.response.body", "body": _BODY})


class BodyLimit:
    def __init__(self, app, root_path: str = ""):
        self.app, self.root_path = app, root_path

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = limit_for(scope["path"], self.root_path)
        declared = Headers(scope=scope).get("content-length")
        if declared is not None:
            declared = declared.strip()
            if not (declared.isascii() and declared.isdigit()) or int(declared) > limit:   # «²» passes isdigit() alone
                return await _refuse(send)
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
                return await _refuse(send)
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
