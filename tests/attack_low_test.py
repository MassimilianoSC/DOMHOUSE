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


# -------- F-12: without a key one learnt whether an apartment existed; a key opened unusable apartments --------
async def _ai(apartment, key):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://t") as c:
        return await c.post("/internal/ai/chat", json={"messages": [{"role": "user", "content": "x"}]},
                            headers={"X-Apartment-Id": apartment, "X-API-Key": key})


def test_f12_an_unknown_apartment_and_a_wrong_key_get_the_same_answer():
    unknown = run(_ai("apt-che-non-esiste", "chiave-qualsiasi"))
    wrong = run(_ai("apt-bologna-01", "chiave-qualsiasi"))
    assert (unknown.status_code, unknown.json()) == (wrong.status_code, wrong.json())
    assert unknown.status_code == 401


@pytest.mark.parametrize("state", ["disabled", "not_ready", "suspended"])
def test_f12_the_right_key_of_an_apartment_that_cannot_be_used_is_refused(monkeypatch, state):
    from bff import ai_gateway, auth
    from bff.repository import Tenant, get_repository
    from bff.repository.base import Creazione
    repo = get_repository()
    called = []

    async def model(body):
        called.append(body)
        return {"choices": [{"message": {"role": "assistant", "content": "Ciao"}}], "usage": {}}
    monkeypatch.setattr(ai_gateway, "call_model", model)
    apt = run(repo.get_apartment("apt-bologna-01")).model_copy(deep=True)
    original = apt.model_copy(deep=True)
    tenant = run(repo.get_tenant(apt.tenant_id))
    try:
        if state == "disabled":
            apt.enabled = False
        elif state == "not_ready":
            apt.creazione = Creazione.model_construct(stato="in_preparazione", porta=8151)
        run(repo.upsert_apartment(apt))
        if state == "suspended":
            run(repo.upsert_tenant(tenant.model_copy(update={"status": "suspended"})))
            auth._known_tenants.clear()
        r = run(_ai("apt-bologna-01", get_settings().instance_api_key_fallback))
        assert r.status_code == 401 and called == [], (state, r.status_code, r.text[:200])
    finally:
        run(repo.upsert_apartment(original))
        run(repo.upsert_tenant(tenant))
        auth._known_tenants.clear()


# -------- F-8: Firebase in error = not revoked; an account disabled in Firebase's console still came in --------
class _FakeFirebase:
    class UserNotFoundError(Exception):
        pass

    def __init__(self):
        self.fail, self.disabled, self.valid_after_ms = False, False, 0

    def get_user(self, uid, app=None):
        if self.fail:
            raise RuntimeError("Firebase non risponde")
        import types
        return types.SimpleNamespace(uid=uid, tokens_valid_after_timestamp=self.valid_after_ms, disabled=self.disabled,
                                     custom_claims={}, email_verified=True)


@pytest.fixture
def firebase(monkeypatch):
    from bff import accounts, auth
    fake = _FakeFirebase()
    s = dataclasses.replace(get_settings(), auth_mode="firebase")
    monkeypatch.setattr(accounts, "get_settings", lambda: s)
    monkeypatch.setattr(accounts, "_auth", lambda: (fake, None))
    monkeypatch.setattr(auth, "_verify_firebase_token", lambda token: {"uid": "u-f8", "iat": 1000.0})
    accounts._valid_after.clear()
    yield fake
    accounts._valid_after.clear()


def _check():
    import types
    from fastapi import HTTPException
    from bff import auth
    try:
        run(auth._verified_claims(types.SimpleNamespace(headers={"Authorization": "Bearer t"})))
        return 200
    except HTTPException as exc:
        return exc.status_code


def test_f8_firebase_in_error_without_a_known_answer_is_try_again_not_valid(firebase):
    firebase.fail = True
    assert _check() == 503


def test_f8_firebase_in_error_reuses_the_last_known_answer_even_old(firebase, monkeypatch):
    from bff import accounts
    firebase.valid_after_ms = 5_000_000                             # revoked at 5000 s: the token of 1000 s is not valid
    assert _check() == 401
    now = accounts.time.monotonic()
    monkeypatch.setattr(accounts.time, "monotonic", lambda: now + accounts.REVOCATION_CACHE_S + 5)
    firebase.fail = True
    assert _check() == 401                                          # the old answer still says revoked


def test_f8_an_account_disabled_in_firebase_is_refused(firebase):
    firebase.disabled = True
    assert _check() == 401


# -------- F-11, the answer: one error code with the field and an Italian sentence (a6, 22 November) --------
@pytest.mark.parametrize("name, message", [
    ("x" * 81, "Il nome può avere al massimo 80 caratteri."),
    ("Mario\nRossi", "Il nome contiene caratteri non ammessi."),
    ("Mario‮issoR", "Il nome contiene caratteri non ammessi."),
    ("Vai su www.evil.example", "Il nome non può contenere un indirizzo web."),
])
def test_f11_the_refusal_of_a_name_says_why_in_italian(name, message):
    for method, path, body in (("POST", "/app/admin/users", {"email": "f11-msg@esempio.it", "role": "viewer",
                                                            "display_name": name}),
                               ("PATCH", "/app/me", {"display_name": name})):
        r = run(_send_as(method, path, body))
        assert r.status_code == 422 and r.json() == {"error": "invalid_text", "field": "display_name",
                                                     "message": message}, (path, r.text[:200])


@pytest.mark.parametrize("address, message", [
    ("v" * 201, "L'indirizzo può avere al massimo 200 caratteri."),
    ("Via\tRoma 1", "L'indirizzo contiene caratteri non ammessi."),
    ("Via Roma 1 https://evil.example", "L'indirizzo non può contenere un indirizzo web."),
])
def test_f11_the_refusal_of_an_address_says_why_in_italian(address, message):
    r = run(_send_as("PATCH", "/app/admin/apartments/apt-rimini-01", {"address": address}))
    assert r.status_code == 422 and r.json() == {"error": "invalid_text", "field": "address", "message": message}


def test_f11_other_validation_errors_keep_their_usual_answer():
    r = run(_send_as("POST", "/app/admin/users", {"email": "non-una-email", "role": "viewer"}))
    assert r.status_code == 422 and "detail" in r.json()
