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


# -------- F-9: a device named «=HYPERLINK(...)» became a formula or a live link in the consumption Excel --------
def test_f9_names_are_text_never_formulas_nor_links_in_the_excel():
    import io
    import zipfile
    from datetime import UTC, datetime
    from bff import energy_report as er
    start, end = datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)
    report = er.Report(organisation="=1+1", apartment="http://x.example", apartment_id="apt-f9", timezone="Europe/Rome",
                       start=start, end=end, in_progress=False, price=0.25, title="Rendiconto mensile",
                       period="ottobre 2026", stay={"booking_id": "=HYPERLINK(\"http://x.example\",\"clic\")",
                                                    "guests": 2, "status": "confirmed"})
    usage = er.Usage(hours={start: 1.5}, devices={"d1": ["=1+1", 1.0], "d2": ["http://x.example", 0.5],
                                                 "d3": ["=HYPERLINK(\"http://x.example\",\"clic\")", 0.1]})
    data = er.workbook(report, usage, end)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        sheets = {n: z.read(n).decode("utf-8") for n in z.namelist() if n.startswith("xl/worksheets/")}
        strings = z.read("xl/sharedStrings.xml").decode("utf-8")
    assert sheets
    for name, xml in sheets.items():
        assert "<f>" not in xml and "<hyperlink" not in xml, name
    assert not [n for n in sheets if "/_rels/" in n]                               # no link relationship at all
    assert "=HYPERLINK" in strings and "=1+1" in strings and "http://x.example" in strings   # the names kept, as text
