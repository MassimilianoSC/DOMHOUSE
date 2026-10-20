"""The engine's log (connector.md §5): one JSON line per event on stdout, with ts, level, msg, apartment_id and the
fields given (in commands: correlation_id, command_id, device_id). For the engine and for every connector:

    from engine import log
    log.info("command sent", correlation_id=cmd.correlation_id, command_id=cmd.command_id, device_id=cmd.device_id)

msg is short, in English and stable (the alerts read it); the details go in the fields. Never secrets: a field whose
name says key, token, password, secret or authorization is written as "[redacted]" anyway. Modelled on bff/logs.py.
"""
import json
import logging
import re
import sys
from datetime import UTC, datetime

SECRET_NAME = re.compile(r"key|token|password|secret|authorization", re.IGNORECASE)
_apartment_id: str | None = None


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "msg": record.getMessage(),
            "apartment_id": _apartment_id,
        }
        for name, value in (getattr(record, "fields", None) or {}).items():
            payload[name] = "[redacted]" if SECRET_NAME.search(name) else value
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(apartment_id: str | None) -> None:
    """Called once by the engine at start: from then on every line carries the apartment."""
    global _apartment_id
    _apartment_id = apartment_id
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False


logger = logging.getLogger("engine")


def info(msg: str, **fields) -> None:
    logger.info(msg, extra={"fields": fields})


def warn(msg: str, **fields) -> None:
    logger.warning(msg, extra={"fields": fields})


def error(msg: str, **fields) -> None:
    logger.error(msg, extra={"fields": fields})
