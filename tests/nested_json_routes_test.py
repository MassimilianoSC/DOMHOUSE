"""Rereading of F-2, P-3: the routes that read their body with request.json() caught ValueError only, so a JSON nested
too deep (RecursionError, about 10 KB, well under the 64 KiB limit) gave a 500: the assistant's rule proposal, its
«Applica», the copy of the rules (preview and copy) and the simulator's booking, whose body as a list also gave a 500
(TypeError). Now bad JSON: the same answer as a body that is not JSON. In-process, dev auth, memory repository."""
import asyncio

import httpx
import pytest

from bff.main import app

RIMINI = "apt-rimini-01"
ADMIN = "admin@demo.it"
NESTED = {"list-5000": b"[" * 5000 + b"]" * 5000, "dict-5000": b'{"a":' * 5000 + b"1" + b"}" * 5000}
ROUTES = [f"/app/apartments/{RIMINI}/rules/proposal", f"/app/apartments/{RIMINI}/rules/proposal/apply",
          f"/app/apartments/{RIMINI}/rules/copy/preview", f"/app/apartments/{RIMINI}/rules/copy",
          f"/app/apartments/{RIMINI}/simulator/booking"]


def post(path, raw):
    async def go():
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            return await c.post(path, content=raw, headers={"X-Dev-User": ADMIN, "Content-Type": "application/json"})
    return asyncio.run(go())


def _refused_as_bad(r, path):
    assert r.status_code in (400, 422), (path, r.status_code, r.text[:200])
    assert r.json()["error"] in ("bad_request", "untranslatable"), (path, r.text[:200])


@pytest.mark.parametrize("kind", NESTED)
@pytest.mark.parametrize("path", ROUTES, ids=lambda p: p.split(RIMINI)[1])
def test_a_body_nested_too_deep_is_refused_not_a_500(path, kind):
    _refused_as_bad(post(path, NESTED[kind]), path)


def test_a_simulator_booking_that_is_a_list_is_refused_not_a_500():
    path = f"/app/apartments/{RIMINI}/simulator/booking"
    r = post(path, b'[{"event": "booking_created"}]')
    assert r.status_code == 400 and r.json()["error"] == "bad_request", r.text[:200]
