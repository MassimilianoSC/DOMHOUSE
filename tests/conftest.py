"""Shared by every test under tests/."""
import sys

import pytest


@pytest.fixture(autouse=True)
def _per_process_counters_fresh():
    """F-5: bff/routes/webhooks.py lets UNSIGNED_ROWS_PER_MINUTE unsigned calls a minute write their row, per process;
    each test starts with a fresh minute, or one test's unsigned calls would leave the next without its rows. Nothing
    is imported here: only a module already loaded is touched (the HTTP suites never load it in the test process)."""
    module = sys.modules.get("bff.routes.webhooks")
    if module is not None:
        module._unsigned.clear()
    routes = sys.modules.get("bff.routes.apartments")         # F-6: streams opened by calling the route, never sent
    if routes is not None:
        routes._open_streams.clear()
    yield
