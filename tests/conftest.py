"""Shared by every test under tests/."""
import sys

import pytest


@pytest.fixture(autouse=True)
def _a_winter_day(monkeypatch):
    """Item 15: the built-in engines (simulated connector) follow MOCK_TODAY for the heating season, a fixed winter day:
    no test depends on today's date (from 16 April to 14 October the boilers would stay on the frost protection)."""
    monkeypatch.setenv("MOCK_TODAY", "2026-01-15")


@pytest.fixture(autouse=True)
def _per_process_counters_fresh():
    """F-5: bff/routes/webhooks.py lets UNSIGNED_ROWS_PER_MINUTE unsigned calls a minute write their row, per process;
    each test starts with a fresh minute, or one test's unsigned calls would leave the next without its rows. Nothing
    is imported here: only a module already loaded is touched (the HTTP suites never load it in the test process)."""
    module = sys.modules.get("bff.routes.webhooks")
    if module is not None:
        module._unsigned.clear()
    limit = sys.modules.get("bff.body_limit")                  # R2: the «troppo_grande» lines of the minute
    if limit is not None:
        limit._acknowledged.clear()
    routes = sys.modules.get("bff.routes.apartments")         # F-6: streams opened by calling the route, never sent
    if routes is not None:
        routes._open_streams.clear()
    yield
