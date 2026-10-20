import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

ctx_user: ContextVar[str | None] = ContextVar("user", default=None)
ctx_tenant: ContextVar[str | None] = ContextVar("tenant_id", default=None)
ctx_apartment: ContextVar[str | None] = ContextVar("apartment_id", default=None)
ctx_correlation: ContextVar[str | None] = ContextVar("correlation_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "user": ctx_user.get(),
            "tenant_id": ctx_tenant.get(),
            "apartment_id": getattr(record, "apartment_id", None) or ctx_apartment.get(),
            "correlation_id": ctx_correlation.get(),
            "msg": record.getMessage(),
        }
        extra = getattr(record, "fields", None)
        if extra:
            payload.update(extra)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> None:
    root = logging.getLogger("bff")
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    root.propagate = False


log = logging.getLogger("bff")


def info(msg: str, **fields) -> None:
    log.info(msg, extra={"fields": fields})


def warn(msg: str, **fields) -> None:
    log.warning(msg, extra={"fields": fields})
