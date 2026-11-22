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


# -------- F-11: an admin's free texts became phishing in the invitation email, or fields of about 1 MiB --------
async def _send_as(method, path, body, who="admin@demo.it"):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://t") as c:
        return await c.request(method, path, json=body, headers={"X-Dev-User": who})


@pytest.mark.parametrize("name", [
    "x" * 81, "Clicca qui https://evil.example/login", "Vai su www.evil.example", "Accedi a evil.example/login",
    "Mario\nRossi", "Mario\x00Rossi", "Mario‮issoR",
], ids=["81", "scheme", "www", "domain-path", "newline", "nul", "bidi"])
def test_f11_a_name_too_long_link_like_or_with_control_characters_is_refused(name):
    from bff.repository import get_repository
    before = len(run(get_repository().list_users("t-flatsharing-demo")))
    email = f"f11-{abs(hash(name)) % 10_000_000}@esempio.it"
    r = run(_send_as("POST", "/app/admin/users", {"email": email, "role": "viewer", "display_name": name}))
    assert r.status_code == 422, (name, r.status_code, r.text[:200])
    assert len(run(get_repository().list_users("t-flatsharing-demo"))) == before
    r = run(_send_as("PATCH", "/app/me", {"display_name": name}))          # the inviter's name, in the email too
    assert r.status_code == 422, (name, r.status_code)


def test_f11_ordinary_names_and_addresses_still_pass():
    for name in ("Maria Rossi-D'Amico", "Zoë Müller", "M. Rossi", "Ufficio 3, piano 2"):
        r = run(_send_as("PATCH", "/app/me", {"display_name": name}))
        assert r.status_code == 200, (name, r.text[:200])
    r = run(_send_as("PATCH", "/app/admin/apartments/apt-rimini-01", {"address": "Viale Vespucci 12, 47921 Rimini (RN)"}))
    assert r.status_code == 200, r.text[:200]


def test_f11_an_address_over_200_characters_or_link_like_is_refused():
    for address in ("v" * 201, "Via Roma 1 https://evil.example", "Via\tRoma\r\n1"):
        r = run(_send_as("PATCH", "/app/admin/apartments/apt-rimini-01", {"address": address}))
        assert r.status_code == 422, (address[:30], r.status_code)


def test_f11_a_user_s_name_changed_by_the_admin_follows_the_same_rule():
    from bff.repository import get_repository
    users = run(get_repository().list_users("t-flatsharing-demo"))
    target = next(u for u in users if u.role == "viewer")
    r = run(_send_as("PATCH", f"/app/admin/users/{target.uid}", {"display_name": "Vedi https://evil.example"}))
    assert r.status_code == 422, r.text[:200]
