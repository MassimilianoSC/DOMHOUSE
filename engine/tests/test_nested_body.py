"""Attack-from-outside review, F-2 point f (a6, 22 November 2026, D-198): a JSON body nested too deep for the parser
(RecursionError) gave a 500 in the engine: body_of caught ValueError only. Now it is «JSON non valido», 400, on every
route that reads a body. The BFF already limits the size (bff/body_limit.py); the depth is the engine's own.

Run: python -m pytest engine/tests -q
"""
import pytest
from starlette.testclient import TestClient

from engine.config import load_config
from engine.service import create_engine_app

KEY = "prova-chiave-0123456789"
HEADERS = {"X-API-Key": KEY, "X-Actor": "system:bff", "X-Correlation-Id": "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10",
           "Content-Type": "application/json"}
NESTED = {"list-5000": b"[" * 5000 + b"]" * 5000, "dict-5000": b'{"a":' * 5000 + b"1" + b"}" * 5000}
ROUTES = [("POST", "/api/v1/apartment/mode"), ("POST", "/api/v1/apartment/hold"), ("PUT", "/api/v1/rules"),
          ("POST", "/api/v1/schedule"), ("POST", "/api/v1/bookings"), ("POST", "/api/v1/ask"),
          ("POST", "/api/v1/_internal/reachability")]


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    env = {"APARTMENT_ID": "apt-prova-01", "API_KEY": KEY, "CONNECTOR": "simulated",
           "DATA_DIR": str(tmp_path_factory.mktemp("nested"))}
    with TestClient(create_engine_app(load_config(env)), raise_server_exceptions=False) as c:
        yield c


@pytest.mark.parametrize("kind", NESTED)
@pytest.mark.parametrize("method, path", ROUTES)
def test_a_body_nested_too_deep_is_bad_json_not_a_500(client, method, path, kind):
    r = client.request(method, path, content=NESTED[kind], headers=HEADERS)
    assert r.status_code == 400, (r.status_code, r.text[:200])
    assert r.json() == {"error": "bad_request", "message": "JSON non valido"}
