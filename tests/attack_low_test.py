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


# -------- F-14: an invitation of A to an email whose Firebase account holds the claims of B (answer 1243) --------
@pytest.fixture
def firebase_claims(monkeypatch):
    import types
    from bff import accounts

    class Fake:
        class UserNotFoundError(Exception):
            pass

        def __init__(self):
            self.users, self.fail = {}, False

        def get_user_by_email(self, email, app=None):
            if self.fail:
                raise RuntimeError("Firebase non risponde")
            if email not in self.users:
                raise self.UserNotFoundError(email)
            return types.SimpleNamespace(uid=f"u-{email}", email=email, custom_claims=self.users[email])

        def set_custom_user_claims(self, uid, claims, app=None):
            raise AssertionError("claims changed")
    fake = Fake()
    s = dataclasses.replace(get_settings(), auth_mode="firebase")
    monkeypatch.setattr(accounts, "get_settings", lambda: s)
    monkeypatch.setattr(accounts, "_auth", lambda: (fake, None))
    return fake


def test_f14_an_email_enabled_in_another_organisation_by_claims_is_refused_like_a_record_there(firebase_claims):
    """A person enabled in B with claims only (e.g. the first admin of set_claims.py, never signed in, so no record)
    invited by A's admin: at the first sign-in the invitation won and B lost the person without deciding it."""
    from bff.repository import Tenant, get_repository
    run(get_repository().upsert_tenant(Tenant(tenant_id="t-altra-f14", name="Altra F-14")))     # exists, active
    firebase_claims.users["f14@esempio.it"] = {"tenant_id": "t-altra-f14", "role": "admin"}
    r = run(_send_as("POST", "/app/admin/users", {"email": "f14@esempio.it", "role": "viewer"}))
    assert r.status_code == 409 and r.json() == {"error": "already_exists",
                                                 "message": "Questa email non può essere invitata"}, r.text
    assert run(get_repository().get_user_by_email("f14@esempio.it")) is None
    assert firebase_claims.users["f14@esempio.it"] == {"tenant_id": "t-altra-f14", "role": "admin"}   # untouched


def test_f14_claims_of_the_same_organisation_or_none_still_invite(firebase_claims):
    from bff.repository import get_repository
    firebase_claims.users["f14-stessa@esempio.it"] = {"tenant_id": "t-flatsharing-demo", "role": "viewer"}
    firebase_claims.users["f14-nessuno@esempio.it"] = {}
    for email in ("f14-stessa@esempio.it", "f14-nessuno@esempio.it", "f14-nuova@esempio.it"):
        r = run(_send_as("POST", "/app/admin/users", {"email": email, "role": "viewer"}))
        assert r.status_code == 201, (email, r.text[:200])
        run(get_repository().delete_user(r.json()["uid"]))


def test_f14_firebase_silent_is_try_again_never_an_invitation(firebase_claims):
    from bff.repository import get_repository
    firebase_claims.fail = True
    r = run(_send_as("POST", "/app/admin/users", {"email": "f14-silenzio@esempio.it", "role": "viewer"}))
    assert r.status_code == 503 and r.json()["error"] == "auth_unavailable", r.text
    assert run(get_repository().get_user_by_email("f14-silenzio@esempio.it")) is None


# -------- rereading of the low fixes, B-4: an address saved before F-11 must not block the apartment's form --------
def _stored_address(value):
    from bff.repository import get_repository
    repo = get_repository()
    apt = run(repo.get_apartment("apt-rimini-01"))
    run(repo.upsert_apartment(apt.model_copy(update={"address": value})))


@pytest.mark.parametrize("old", ["v" * 250, "Via\tRoma 1", "Vedi www.vecchio.example"], ids=["long", "tab", "link"])
def test_b4_the_form_saves_with_an_old_address_out_of_the_rule_sent_back_unchanged(old):
    """The site's apartment window always sends address with name, enabled and price: a saved address now out of the
    rule made every save fail with 422, A6's switch-off included. The address is checked only when it changes."""
    _stored_address(old)
    try:
        r = run(_send_as("PATCH", "/app/admin/apartments/apt-rimini-01", {"name": "Rimini centro", "address": old}))
        assert r.status_code == 200, (old[:20], r.text[:200])
        r = run(_send_as("PATCH", "/app/admin/apartments/apt-rimini-01", {"address": old + " "}))
        assert r.status_code == 422 and r.json()["error"] == "invalid_text"           # changed: the rule counts
    finally:
        _stored_address("Viale Vespucci 12, 47921 Rimini (RN)")


def test_b4_a_real_address_with_a_slash_and_a_dot_passes():
    try:
        for address in ("Via S.Maria/3", "Via S. Maria 3/A, int. 4", "C.so Garibaldi 10/b"):
            r = run(_send_as("PATCH", "/app/admin/apartments/apt-rimini-01", {"address": address}))
            assert r.status_code == 200, (address, r.text[:200])
    finally:
        _stored_address("Viale Vespucci 12, 47921 Rimini (RN)")


# -------- rereading of the low fixes, B-3: the rule of F-11 against Unicode --------
# final rereading R-6: in an address a domain with a path counts only with a known top-level domain, so the examples
# use .com; the homoglyph in the top-level domain and «.example» are refused in names (test_r4 below)
LINKS_EVERYWHERE = ["https：//evil.example", "https：／／evil.example", "evil。com/login",
                    "evil․com/login", "evil.com／login", "еvil.com/login",
                    "evil.com?x=1", "evil.com:8080", "evil.com\\login", "10.0.0.1/login",
                    "//evil.com", "mailto:x@evil.com", "javascript:alert(1)"]
INVISIBLE_ONES = ["a‎b", "a‏b", "a؜b", "a b", "a b", "a­b", "a⁡b", "aㅤb",
                  "a\U000e0041b", "ab", "a\U000f0000b"]


@pytest.mark.parametrize("text", LINKS_EVERYWHERE + INVISIBLE_ONES, ids=repr)
def test_b3_tricks_with_unicode_are_refused_in_names_and_addresses(text):
    from bff import plain_text
    assert plain_text.address_problem(text) is not None, text
    r = run(_send_as("PATCH", "/app/me", {"display_name": text}))
    assert r.status_code == 422 and r.json()["error"] == "invalid_text", (text, r.text[:120])


def test_b3_a_domain_alone_is_refused_in_a_name_and_allowed_in_an_address():
    """Gmail and Outlook make a link of a domain alone in an invitation email: not in a name; an address may name one."""
    from bff import plain_text
    for name in ("Verifica su evil-domhouse.com", "Casa.it", "mario@evil.com"):
        r = run(_send_as("PATCH", "/app/me", {"display_name": name}))
        assert r.status_code == 422 and r.json()["message"] == "Il nome non può contenere un indirizzo web.", name
    assert plain_text.address_problem("Residence Casa.it, Via Roma 1") is None


@pytest.mark.parametrize("name", ["Zoë Müller", "Maria Rossi-D'Amico", "Lucia Dell’Acqua", "José María Pérez",
                                  "Nguyễn Văn An", "王小明", "M. Rossi", "Dott.ssa Bianchi", "Ufficio 3, piano 2",
                                  "S.r.l. Rossi & Figli", "Ing. Giorgio Verdi"])
def test_b3_real_names_still_pass(name):
    r = run(_send_as("PATCH", "/app/me", {"display_name": name}))
    assert r.status_code == 200, (name, r.text[:200])


@pytest.mark.parametrize("address", ["Viale Vespucci 12, 47921 Rimini (RN)", "Via S.Maria/3", "C.so Garibaldi 10/b",
                                     "Località Ca' di Bassi 4", "Via dell’Orso 7, int. 2", "Piazza XX Settembre 1"])
def test_b3_real_addresses_still_pass(address):
    from bff import plain_text
    assert plain_text.address_problem(address) is None, address


# -------- rereading of the low fixes, B-11: the name taken from a token's «name» claim follows F-11's rule --------
@pytest.mark.parametrize("name, kept", [
    ("Clicca https://evil.example", "primo-admin"), ("x" * 90, "primo-admin"), ("Mario‮issoR", "primo-admin"),
    ("Anna Bianchi", "Anna Bianchi"), ("", ""),
])
def test_b11_the_first_admins_name_from_the_claims_follows_the_rule(name, kept):
    """The first admin of set_claims.py takes their name from Google's «name» claim, and that name is the inviter's in
    every invitation email: out of the rule, the part of the email before «@» (when that passes) is used instead."""
    from bff import auth
    from bff.repository import get_repository
    repo = get_repository()
    claims = {"uid": "u-b11", "email": "primo-admin@esempio.it", "email_verified": True, "name": name,
              "tenant_id": "t-flatsharing-demo", "role": "admin"}
    try:
        user = run(auth._from_claims(repo, claims))
        assert user.display_name == kept and run(repo.get_user("u-b11")).display_name == kept
    finally:
        run(repo.delete_user("u-b11"))
    assert auth.claims_name({"name": "Vai su www.evil.example", "email": "www.evil@x.it"}) == ""


# -------- rereading of the low fixes, B-2: an unreadable secret is the same 401 as F-12, not a 500 --------
def test_b2_an_apartment_whose_secret_cannot_be_read_answers_like_an_unknown_one(monkeypatch):
    from bff import instances

    async def unreadable(apt):
        raise RuntimeError("segreto inesistente")
    monkeypatch.setattr(instances, "api_key", unreadable)
    unknown = run(_ai("apt-che-non-esiste", "chiave-qualsiasi"))

    async def go():
        transport = httpx.ASGITransport(app=main.app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            return await c.post("/internal/ai/chat", json={"messages": [{"role": "user", "content": "x"}]},
                                headers={"X-Apartment-Id": "apt-bologna-01", "X-API-Key": "chiave-qualsiasi"})
    r = run(go())
    assert (r.status_code, r.json() if r.status_code != 500 else r.text) == (unknown.status_code, unknown.json())


# -------- final rereading R-1, R-4, R-6: Italian titles pass, any domain is refused in a name, real addresses pass --------
@pytest.mark.parametrize("name", ["Sig.ra Maria Rossi", "Sig.na Bianchi", "Avv.to Rossi", "Spett.le Ditta",
                                  "Ill.mo Prof. Verdi", "Gent.mo Rossi", "Gent.ma Sig.ra Neri", "Coop.va Sociale",
                                  "Ass.ne Culturale", "Egr.gio Sig. Rossi", "Dott.ssa Bianchi", "Prof.ssa Gialli",
                                  "Arch.tto Neri", "S.r.l. Rossi & Figli", "S.p.A. Verdi", "F.lli Bianchi"])
def test_r1_italian_titles_and_company_forms_pass_in_a_name(name):
    r = run(_send_as("PATCH", "/app/me", {"display_name": name}))
    assert r.status_code == 200, (name, r.text[:200])


@pytest.mark.parametrize("name", ["Vai su evil.zip", "evil.bank", "evil.icu", "evil.ninja", "evil.academy",
                                  "evil-dom.house", "evil.museum", "evil.pro", "пример.рф",
                                  "evil.comа", "evil.com_x", "evil.example/login", "evil.exаmple/login"],
                         ids=repr)
def test_r4_any_domain_is_refused_in_a_name(name):
    r = run(_send_as("PATCH", "/app/me", {"display_name": name}))
    assert r.status_code == 422 and r.json()["message"] == "Il nome non può contenere un indirizzo web.", (name, r.text)


@pytest.mark.parametrize("address", ["Fraz.Colle/2", "Loc.Prato/Fraz.Colle", "Via Sta.Maria/3", "Loc.Tà/3",
                                     "Via Roma 1 Tel: 06123456", "c/o Rossi, V.le Monza 12/14", "Km 12.300",
                                     "Str.Prov.le 12/A"])
def test_r6_real_addresses_with_dots_and_slashes_pass(address):
    from bff import plain_text
    assert plain_text.address_problem(address) is None, address


@pytest.mark.parametrize("address", ["Vedi evil.com/login", "evil.it/x", "www.evil.example", "https://evil.example",
                                     "10.0.0.1/x", "mailto:a@evil.com"])
def test_r6_web_addresses_are_still_refused_in_an_address(address):
    from bff import plain_text
    assert plain_text.address_problem(address) is not None, address



# -------- final rereading R-2 (a6's choice a): only claims naming an existing, active organisation refuse --------
@pytest.mark.parametrize("state", ["missing", "suspended"])
def test_r2_claims_of_an_organisation_gone_or_suspended_do_not_block_an_invitation(firebase_claims, state):
    """People removed before R4-1 may still hold the claims of their old organisation: if it no longer exists, or is
    suspended, another organisation can invite them; an active one still refuses (F-14), until the platform clears the
    claims with scripts/set_claims.py --orphan-claims --apply --email <email>."""
    from bff.repository import Tenant, get_repository
    repo = get_repository()
    tenant = f"t-r2-{state}"
    if state == "suspended":
        run(repo.upsert_tenant(Tenant(tenant_id=tenant, name=f"R-2 {state}", status="suspended")))
    email = f"r2-{state}@esempio.it"
    firebase_claims.users[email] = {"tenant_id": tenant, "role": "viewer"}
    r = run(_send_as("POST", "/app/admin/users", {"email": email, "role": "viewer"}))
    assert r.status_code == 201, (state, r.text[:200])
    run(repo.delete_user(r.json()["uid"]))


# -------- final rereading R-5: names saved before F-11 are checked again when the invitation email is written --------
@pytest.fixture
def outbox(monkeypatch):
    from bff import invites
    sent = []
    s = dataclasses.replace(get_settings(), smtp_user="mittente@esempio.it", smtp_password="x", smtp_host="smtp.x")
    monkeypatch.setattr(invites, "get_settings", lambda: s)
    monkeypatch.setattr(invites, "_password_link", lambda email, name: None)
    monkeypatch.setattr(invites, "_send", lambda msg: sent.append(msg))

    async def allowed(_buckets):
        return True
    from bff.repository import get_repository
    monkeypatch.setattr(get_repository(), "take_mail_quota", allowed)
    return sent


def _body(msg):
    return "\n".join(part.get_content() for part in msg.walk() if part.get_content_type().startswith("text/"))


def test_r5_an_invited_name_out_of_the_rule_is_left_out_of_the_email(outbox):
    from bff import invites
    status = run(invites.send_invitation("r5@esempio.it", "Vai su www.evil.example", "viewer", "Flatsharing",
                                         "Anna Bianchi", "t-flatsharing-demo"))
    assert status == "sent" and outbox
    body = _body(outbox[0])
    assert "evil" not in body and "Anna Bianchi" in body


def test_r5_an_inviters_name_out_of_the_rule_becomes_the_part_of_their_email(outbox):
    from bff import invites
    run(invites.send_invitation("r5b@esempio.it", "Mario Rossi", "viewer", "Flatsharing",
                                "Clicca https://evil.example", "t-flatsharing-demo", inviter_email="capo-ufficio@esempio.it"))
    body = _body(outbox[0])
    assert "evil" not in body and "capo-ufficio ti ha invitato" in body and "Ciao Mario Rossi" in body


# -------- final rereading R-10: an apartment that cannot be used answers 401 before its secret is read --------
@pytest.mark.parametrize("state", ["disabled", "not_ready", "suspended"])
def test_r10_no_secret_read_for_an_apartment_that_cannot_be_used(monkeypatch, state):
    """B-2 gave the right 401, but every request with the id of an A2 apartment in preparation or half deleted read
    Secret Manager (failed reads are not cached) and wrote a warn line, without limit, with a timing unlike an unknown
    id. The state is now checked first: no read, as for an id that does not exist."""
    from bff import auth, instances
    from bff.repository import get_repository
    from bff.repository.base import Creazione
    repo = get_repository()
    reads = []

    async def counted(apt):
        reads.append(apt.apartment_id)
        return get_settings().instance_api_key_fallback
    monkeypatch.setattr(instances, "api_key", counted)
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
        r = run(_ai("apt-bologna-01", "chiave-qualsiasi"))
        assert r.status_code == 401 and reads == [], (state, reads)
    finally:
        run(repo.upsert_apartment(original))
        run(repo.upsert_tenant(tenant))
        auth._known_tenants.clear()
