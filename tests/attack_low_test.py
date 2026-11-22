"""The low defects of the attack-from-outside review (22 November 2026), one section each. In-process, memory
repository, no network."""
import asyncio
import dataclasses

import httpx
import pytest

from bff import main
from bff.config import get_settings


def run(coro):
    return asyncio.run(coro)


async def _get(app, path):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.get(path)


# -------- F-10: /docs, /redoc and /openapi.json listed every route, /internal/* and the platform's included --------
@pytest.mark.parametrize("env", ["prod", "staging"])
def test_f10_no_route_list_outside_development(monkeypatch, env):
    s = dataclasses.replace(get_settings(), app_env=env, auth_mode="firebase", instance_mode="mock")
    monkeypatch.setattr(main, "get_settings", lambda: s)
    app = main.create_app()
    for path in ("/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"):
        assert run(_get(app, path)).status_code == 404, (env, path)
    assert app.openapi()["paths"]                       # the schema stays at hand for the build (frontend types)


def test_f10_development_keeps_them(monkeypatch):
    s = dataclasses.replace(get_settings(), app_env="dev")
    monkeypatch.setattr(main, "get_settings", lambda: s)
    app = main.create_app()
    assert run(_get(app, "/openapi.json")).status_code == 200 and run(_get(app, "/docs")).status_code == 200
