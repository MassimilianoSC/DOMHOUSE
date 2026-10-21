"""Standalone mock instance: python -m bff.mock_instance --port 8100 (serves /{apartment_id}/api/v1/...).

The key is required (--api-key or INSTANCE_API_KEY_FALLBACK): no fixed fallback any more (P-60 step 2). For one
apartment at /api/v1, as on the VM, use the engine itself: python -m engine (README)."""
import argparse
import os

import uvicorn

from .app import create_mock_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Mock domotic instance (contract 1.0.5)")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--api-key", default=os.environ.get("INSTANCE_API_KEY_FALLBACK", ""))
    args = parser.parse_args()
    if not args.api_key.strip():
        parser.error("la chiave è obbligatoria: --api-key oppure INSTANCE_API_KEY_FALLBACK")
    print(f"Mock instance on http://{args.host}:{args.port}/<apartment_id>/api/v1 (X-API-Key: {'*' * len(args.api_key)})")
    uvicorn.run(create_mock_app(api_key=args.api_key), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
