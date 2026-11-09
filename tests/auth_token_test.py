"""D-198, the check of the Firebase token (bff/auth.py): off the event loop, within a time limit; when it cannot be done
the answer is 503 auth_unavailable, which the site treats as a hiccup, and not 401, which ends the session."""
import asyncio
import dataclasses
import threading
import time
from types import SimpleNamespace

import firebase_admin
import pytest
from fastapi import HTTPException
from firebase_admin import auth as fb_auth

from bff import accounts, auth
from bff.config import get_settings

CLAIMS = {"uid": "u1", "iat": 1, "email": "a@b.it"}
REQUEST = SimpleNamespace(headers={"Authorization": "Bearer un-token"})


@pytest.fixture(autouse=True)
def not_revoked(monkeypatch):
    monkeypatch.setattr(accounts, "token_revoked", lambda uid, issued_at: False)


def check(request=REQUEST):
    return asyncio.run(auth._verified_claims(request))


def refused(request=REQUEST) -> dict:
    with pytest.raises(HTTPException) as exc:
        check(request)
    return {"status": exc.value.status_code, **exc.value.detail}


def test_the_check_runs_off_the_event_loop(monkeypatch):
    seen = []

    def fake(token):
        seen.append(threading.current_thread())
        return dict(CLAIMS)
    monkeypatch.setattr(auth, "_verify_firebase_token", fake)
    assert check() == CLAIMS and seen[0] is not threading.main_thread()


def test_too_slow_a_check_is_try_again_not_session_over(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: dataclasses.replace(get_settings(), token_check_timeout_s=0.05))
    monkeypatch.setattr(auth, "_verify_firebase_token", lambda token: time.sleep(0.5))

    async def timed():
        started = time.monotonic()
        with pytest.raises(HTTPException) as exc:
            await auth._verified_claims(REQUEST)
        return exc.value, time.monotonic() - started          # asyncio.run then waits for the abandoned thread
    error, took = asyncio.run(timed())
    assert took < 0.45 and error.status_code == 503
    assert error.detail == {"error": "auth_unavailable", "message": "Controllo dell'accesso non disponibile: riprova tra poco"}


def test_google_keys_out_of_reach_is_try_again_not_session_over(monkeypatch):
    def unreachable(token, app=None):
        raise fb_auth.CertificateFetchError("niente rete", cause=OSError())
    monkeypatch.setattr(fb_auth, "verify_id_token", unreachable)
    monkeypatch.setattr(auth, "firebase_app", lambda: None)
    assert refused()["status"] == 503


def test_a_bad_token_is_still_session_over(monkeypatch):
    def bad(token, app=None):
        raise fb_auth.InvalidIdTokenError("firma sbagliata")
    monkeypatch.setattr(fb_auth, "verify_id_token", bad)
    monkeypatch.setattr(auth, "firebase_app", lambda: None)
    assert refused() == {"status": 401, "error": "unauthorized", "message": "Sessione non valida o scaduta"}
    assert refused(SimpleNamespace(headers={}))["status"] == 401


def test_two_threads_never_initialize_firebase_twice(monkeypatch):
    made = []

    def slow_init(options=None):
        time.sleep(0.05)
        made.append(1)
        return object()
    monkeypatch.setattr(firebase_admin, "_apps", {})
    monkeypatch.setattr(firebase_admin, "initialize_app", slow_init)
    monkeypatch.setattr(auth, "_firebase_app", None)
    threads = [threading.Thread(target=auth.firebase_app) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(made) == 1
