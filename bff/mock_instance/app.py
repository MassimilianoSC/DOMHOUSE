"""The BFF's demonstration apartments (D-97) and python -m bff.mock_instance: the engine's contract API over simulated
connectors, any apartment at /{apartment_id}/api/v1. The code is the engine's (engine/, P-60 step 2): one program."""
import os

from engine.api import create_contract_app
from engine.core import ALL_FEATURES, Registry


def create_mock_app(api_key: str, features: list[str] | None = None, ping_seconds: float | None = None):
    registry = Registry()
    env_features = os.environ.get("MOCK_FEATURES")
    enabled = features or ([f.strip() for f in env_features.split(",") if f.strip()] if env_features else ALL_FEATURES)
    app = create_contract_app(registry.get, api_key, features=enabled,
                              simulated=os.environ.get("DOMOTICA_SIMULATED", "1") == "1",
                              implementation={"name": "bff-mock-instance", "version": "0.1.0"},
                              ping_seconds=ping_seconds or float(os.environ.get("MOCK_PING_S", "25")),
                              title="Mock instance (contract 1.0.5)")
    app.state.registry = registry
    return app
