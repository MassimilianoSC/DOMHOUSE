"""python -m engine: the engine of one apartment, configured by environment variables (engine/config.py).

Exit codes: 2 the configuration is not valid (e.g. no API_KEY, or DATA_DIR not writable), 3 the connector cannot be
used (unknown, or its api_version differs from the engine's). Every problem is also a JSON log line on stdout.
"""
import os
import sys

import uvicorn

from . import log
from .config import ConfigError, load_config, prepare_data_dir
from .service import StartupError, create_engine_app


def main() -> int:
    try:
        config = load_config()
        prepare_data_dir(config)
    except ConfigError as exc:
        log.setup_logging(os.environ.get("APARTMENT_ID") or None)
        log.error("invalid configuration", problems=str(exc).splitlines())
        print(f"Configurazione non valida:\n{exc}", file=sys.stderr)
        return 2
    log.setup_logging(config.apartment_id)
    if config.simulated:
        os.environ.setdefault("MOCK_TIME_SCALE", "60")     # the rules' minutes in real time unless a test asks
    else:
        os.environ["MOCK_TIME_SCALE"] = "60"               # with real devices, always real time
    try:
        app = create_engine_app(config)
    except StartupError as exc:
        log.error(exc.msg, **exc.fields)
        print(f"{exc.msg}: {exc.fields}", file=sys.stderr)
        return 3
    uvicorn.run(app, host=config.host, port=config.port, log_level="warning", access_log=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
