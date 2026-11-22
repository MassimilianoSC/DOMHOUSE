"""F-2 (attack-from-outside review, 22 November 2026): a limit on the size of every request body, BEFORE anything reads
it. FastAPI parses a typed body before the access check, and the webhook read the whole body before its signature: a few
bodies of about 30 MiB (Cloud Run's HTTP/1 limit is 32 MiB) used up the 512 MiB of an instance. Pure ASGI, outermost:
a declared Content-Length over the limit is refused without reading; otherwise the body is collected here, piece by piece,
and refused as soon as it passes the limit (bodies in pieces carry no Content-Length). Under the limit the application
gets the same body in one message, then the server's own messages (the disconnect of a stream).

The limits, from the largest legitimate body (22 November): every /app route and the agent's results carry a few KiB at
most; the engines' way to the model carries the system prompt with the apartment's state (devices, recent decisions,
schedules), some tens of KiB; an Italianway booking is under 2 KiB. A JSON body parsed by Python takes about 12 times
its size, and parsing happens before the access check: so the limits stay well below 1 MiB."""
from starlette.datastructures import Headers

WEBHOOK_LIMIT = 64 * 1024
AI_CHAT_LIMIT = 256 * 1024
DEFAULT_LIMIT = 256 * 1024
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
        if declared is not None and (not declared.strip().isdigit() or int(declared) > limit):
            return await _refuse(send)
        pieces, size = [], 0
        while True:
            message = await receive()
            if message["type"] != "http.request":             # the client went away before the end: passed on
                first = message
                break
            piece = message.get("body", b"")
            size += len(piece)
            if size > limit:
                return await _refuse(send)
            pieces.append(piece)
            if not message.get("more_body", False):
                first = {"type": "http.request", "body": b"".join(pieces), "more_body": False}
                break
        pieces = None
        given = False

        async def replay():
            nonlocal given, first
            if not given:
                given = True
                message, first = first, None
                return message
            return await receive()

        await self.app(scope, replay, send)
