"""Single source of the contract's x-features map (feature -> endpoints), used by the engine and by the BFF."""
import re

FEATURE_MAP: dict[str, list[str]] = {
    "apartment": ["GET /apartment", "POST /apartment/mode", "POST /apartment/hold"],
    "devices": ["GET /devices", "PATCH /devices/{device_id}"],
    "commands": ["POST /devices/{device_id}/commands", "GET /commands/{command_id}"],
    "energy": ["GET /energy"],
    "schedule": ["GET /schedule", "POST /schedule", "PATCH /schedule/{schedule_id}", "DELETE /schedule/{schedule_id}"],
    "rules": ["GET /rules", "PUT /rules"],
    "approvals": ["GET /approvals", "POST /approvals/{approval_id}/decision"],
    "decisions": ["GET /decisions"],
    "ask": ["POST /ask", "GET /ask/{ask_id}"],
    "bookings": ["POST /bookings"],
    "stream": ["GET /stream"],
}


def _compile() -> list[tuple[str, re.Pattern, str]]:
    out = []
    for feature, endpoints in FEATURE_MAP.items():
        for ep in endpoints:
            method, path = ep.split(" ", 1)
            pattern = "^" + re.sub(r"\{[^}]+\}", r"[^/]+", path) + "$"
            out.append((method, re.compile(pattern), feature))
    return out


_ROUTES = _compile()


def feature_for(method: str, path: str) -> str | None:
    path = "/" + path.strip("/")
    for m, pattern, feature in _ROUTES:
        if m == method.upper() and pattern.match(path):
            return feature
    return None
