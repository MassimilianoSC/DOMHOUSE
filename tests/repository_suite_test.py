"""Shared repository suite: every Repository implementation must pass it.

Memory runs always; Firestore runs only when FIRESTORE_EMULATOR_HOST is set (e.g. `gcloud emulators firestore start`).
"""
import asyncio
import os
import uuid

import pytest

from bff.repository.base import WEBHOOK_LOG_LIMIT, Apartment, ExternalIds, Tenant, User, WebhookLog, apply_booking_event
from bff.repository.memory import InMemoryRepository


def _backends():
    yield pytest.param("memory", id="memory")
    yield pytest.param(
        "firestore", id="firestore",
        marks=pytest.mark.skipif(not os.environ.get("FIRESTORE_EMULATOR_HOST"), reason="FIRESTORE_EMULATOR_HOST not set"),
    )


@pytest.fixture(params=list(_backends()))
def repo(request):
    if request.param == "memory":
        return InMemoryRepository()
    from bff.repository.firestore import FirestoreRepository

    return FirestoreRepository(project_id=os.environ.get("GCP_PROJECT_ID", "demo-test"), prefix=f"t{uuid.uuid4().hex[:8]}_")


_LOOP = asyncio.new_event_loop()  # one dedicated loop, never set as default, so other files' asyncio.run() can't close
                                  # it (Fable, D-70); the Firestore async client also stays bound to a single loop


def run(coro):
    return _LOOP.run_until_complete(coro)


def test_tenant_roundtrip(repo):
    t = Tenant(tenant_id="t1", name="Uno")
    run(repo.upsert_tenant(t))
    assert run(repo.get_tenant("t1")).name == "Uno"
    assert run(repo.get_tenant("nope")) is None
    assert [x.tenant_id for x in run(repo.list_tenants())] == ["t1"]


def test_users_by_tenant_and_email(repo):
    run(repo.upsert_user(User(uid="u1", email="A@x.it", tenant_id="t1", role="admin")))
    run(repo.upsert_user(User(uid="u2", email="b@x.it", tenant_id="t1", role="viewer")))
    run(repo.upsert_user(User(uid="u3", email="c@y.it", tenant_id="t2", role="viewer")))
    assert run(repo.get_user_by_email("a@x.it")).uid == "u1"
    assert [u.uid for u in run(repo.list_users("t1"))] == ["u1", "u2"]
    assert run(repo.delete_user("u2")) is True
    assert run(repo.delete_user("u2")) is False
    assert run(repo.get_user("u2")) is None


def test_user_apartment_ids_none_empty_list(repo):
    # None = every apartment, [] = none: the two must survive a round trip as different values (P-18)
    run(repo.upsert_user(User(uid="ua", email="ua@x.it", tenant_id="t1", role="viewer")))
    run(repo.upsert_user(User(uid="ub", email="ub@x.it", tenant_id="t1", role="viewer", apartment_ids=[])))
    run(repo.upsert_user(User(uid="uc", email="uc@x.it", tenant_id="t1", role="operator", apartment_ids=["a2", "a1"])))
    assert run(repo.get_user("ua")).apartment_ids is None
    assert run(repo.get_user("ub")).apartment_ids == []
    assert run(repo.get_user("uc")).apartment_ids == ["a2", "a1"]
    by_uid = {u.uid: u.apartment_ids for u in run(repo.list_users("t1"))}
    assert by_uid == {"ua": None, "ub": [], "uc": ["a2", "a1"]}


def test_user_record_without_apartment_ids_means_all(repo):
    # records written before P-18 have no apartment_ids at all: they must read back as None (= every apartment)
    raw = {"uid": "uold", "email": "old@x.it", "display_name": "", "tenant_id": "t1", "role": "operator",
           "notification_prefs": {"approvals": True, "offline": True, "decisions": False}, "push_tokens": []}
    if isinstance(repo, InMemoryRepository):
        repo.users["uold"] = User.model_validate(raw)
    else:
        run(repo._col("users").document("uold").set(raw))
    assert run(repo.get_user("uold")).apartment_ids is None
    assert [u.apartment_ids for u in run(repo.list_users("t1")) if u.uid == "uold"] == [None]


def test_platform_members(repo):
    # P-36: keyed by normalised email, so "  Gestore@X.it " and "gestore@x.it" are the same person
    from bff.repository import PlatformMember

    run(repo.add_platform_member(PlatformMember(email="  Gestore@X.it ", added_by="prova")))
    run(repo.add_platform_member(PlatformMember(email="altro@x.it")))
    assert run(repo.get_platform_member("gestore@x.it")).email == "gestore@x.it"
    assert run(repo.get_platform_member("GESTORE@x.it")) is not None
    assert [m.email for m in run(repo.list_platform_members())] == ["altro@x.it", "gestore@x.it"]
    assert run(repo.remove_platform_member("Gestore@X.it")) is True
    assert run(repo.remove_platform_member("gestore@x.it")) is False
    assert run(repo.get_platform_member("gestore@x.it")) is None


def test_returned_objects_are_copies(repo):
    run(repo.upsert_user(User(uid="u9", email="z@x.it", tenant_id="t1", role="viewer")))
    u = run(repo.get_user("u9"))
    u.role = "admin"
    assert run(repo.get_user("u9")).role == "viewer"


def test_apartments_filter_sort_external_id(repo):
    run(repo.upsert_apartment(Apartment(apartment_id="a2", tenant_id="t1", name="Zeta", instance_url="mock://builtin",
                                        external_ids=ExternalIds(italianway="IW-2"))))
    run(repo.upsert_apartment(Apartment(apartment_id="a1", tenant_id="t1", name="Alfa", instance_url="mock://builtin")))
    run(repo.upsert_apartment(Apartment(apartment_id="a3", tenant_id="t2", name="Beta", instance_url="mock://builtin")))
    assert [a.apartment_id for a in run(repo.list_apartments("t1"))] == ["a1", "a2"]
    assert len(run(repo.list_apartments())) == 3
    assert [a.apartment_id for a in run(repo.find_apartments_by_external_id("italianway", "IW-2"))] == ["a2"]
    assert run(repo.find_apartments_by_external_id("italianway", "IW-9")) == []
    assert run(repo.delete_apartment("a3")) is True
    assert run(repo.get_apartment("a3")) is None


def test_bookings_archive(repo):
    ev = {"event_id": "e1", "type": "booking_created", "booking_id": "bk1", "checkin_at": "2026-11-01T15:00:00Z",
          "checkout_at": "2026-11-03T10:00:00Z", "guests": 2, "source": "simulator", "ts": "2026-10-01T00:00:00Z"}
    rec = apply_booking_event(None, "a1", ev)
    run(repo.upsert_booking(rec))
    rec = apply_booking_event(run(repo.get_booking("a1", "bk1")), "a1", {**ev, "event_id": "e2", "type": "checkin"})
    run(repo.upsert_booking(rec))
    stored = run(repo.get_booking("a1", "bk1"))
    assert stored.status == "checked_in" and stored.event_ids == ["e1", "e2"]
    assert apply_booking_event(stored, "a1", {**ev, "event_id": "e2", "type": "checkin"}).event_ids == ["e1", "e2"]
    run(repo.upsert_booking(apply_booking_event(None, "a1", {**ev, "event_id": "e3", "booking_id": "bk0",
                                                            "checkin_at": "2026-10-20T15:00:00Z", "checkout_at": "2026-10-22T10:00:00Z"})))
    assert [b.booking_id for b in run(repo.list_bookings("a1"))] == ["bk0", "bk1"]
    assert run(repo.list_bookings("zzz")) == []
    assert run(repo.get_booking("a1", "nope")) is None


def test_cancel_then_recreate(repo):
    base = {"booking_id": "bk7", "checkin_at": "2026-12-01T15:00:00Z", "checkout_at": "2026-12-05T10:00:00Z",
            "guests": None, "source": "italianway", "ts": "2026-10-01T00:00:00Z"}
    rec = apply_booking_event(None, "a1", {**base, "event_id": "c1", "type": "booking_created"})
    rec = apply_booking_event(rec, "a1", {**base, "event_id": "c2", "type": "booking_cancelled"})
    assert rec.status == "cancelled"
    rec = apply_booking_event(rec, "a1", {**base, "event_id": "c3", "type": "booking_changed", "checkout_at": "2026-12-06T10:00:00Z"})
    assert rec.status == "booked" and rec.checkout_at == "2026-12-06T10:00:00Z"


def test_webhook_logs_per_tenant_newest_first(repo, monkeypatch):
    # P-36 S1: strictly per tenant (None = unattributed calls, platform only); the limit applies per tenant, so a busy
    # organisation never pushes out another one's logs. Limit lowered to 4 to keep the emulator run short.
    import bff.repository.firestore as fs
    import bff.repository.memory as mem
    for mod in (fs, mem):
        monkeypatch.setattr(mod, "WEBHOOK_LOG_LIMIT", 4)

    def log(i, tenant):
        return WebhookLog(log_id=f"wh-{i:04d}", received_at=f"2026-10-15T10:{i // 60:02d}:{i % 60:02d}.000Z", tenant_id=tenant,
                          signature_ok=i % 7 != 0, status_code=200 if i % 7 else 401, outcome="accepted" if i % 7 else "invalid_signature",
                          event_id=f"e{i}", correlation_id=f"c{i}", forward_status=200, forward_attempts=1, raw_body="{}")

    for i in range(12):
        run(repo.add_webhook_log(log(i, "t1" if i % 2 else None)))
    run(repo.add_webhook_log(log(20, "t2")))
    t1 = run(repo.list_webhook_logs("t1"))
    assert [x.log_id for x in t1] == ["wh-0011", "wh-0009", "wh-0007", "wh-0005"]      # newest first, 4 kept
    none = run(repo.list_webhook_logs(None))
    assert [x.log_id for x in none] == ["wh-0010", "wh-0008", "wh-0006", "wh-0004"] and all(x.tenant_id is None for x in none)
    assert [x.log_id for x in run(repo.list_webhook_logs("t2"))] == ["wh-0020"]        # not pushed out by t1
    assert run(repo.list_webhook_logs("t3")) == []
    assert len(run(repo.list_webhook_logs("t1", limit=2))) == 2
    assert t1[0].raw_body == "{}" and t1[0].signature_ok is True


def test_users_with_push_token(repo):
    run(repo.upsert_user(User(uid="p1", email="p1@x.it", tenant_id="t1", role="viewer", push_tokens=["tok-shared", "tok-1"])))
    run(repo.upsert_user(User(uid="p2", email="p2@x.it", tenant_id="t2", role="viewer", push_tokens=["tok-shared"])))
    run(repo.upsert_user(User(uid="p3", email="p3@x.it", tenant_id="t1", role="viewer", push_tokens=["tok-3"])))
    assert sorted(u.uid for u in run(repo.users_with_push_token("tok-shared"))) == ["p1", "p2"]   # across tenants
    assert run(repo.users_with_push_token("tok-none")) == []


def test_atomic_claims(repo):
    # P-36: double clicks and concurrent requests never create two invitations, reuse a name or an apartment id
    u = User(uid="inv-abc", email="Doppio@X.it", tenant_id="t1", role="admin")
    assert run(repo.create_user_if_absent(u)) is True
    assert run(repo.create_user_if_absent(u.model_copy(update={"tenant_id": "t2"}))) is False
    assert run(repo.get_user("inv-abc")).tenant_id == "t1"
    assert run(repo.claim_tenant_name("flatsharing", "t-a")) is None
    assert run(repo.claim_tenant_name("flatsharing", "t-a")) is None         # same owner: idempotent
    assert run(repo.claim_tenant_name("flatsharing", "t-b")) == "t-a"        # taken: the owner is returned
    run(repo.release_tenant_name("flatsharing", "t-b"))                      # not the owner: no effect
    assert run(repo.claim_tenant_name("flatsharing", "t-b")) == "t-a"
    run(repo.release_tenant_name("flatsharing", "t-a"))
    assert run(repo.claim_tenant_name("flatsharing", "t-b")) is None
    assert run(repo.reserve_apartment_id("apt-x")) is True
    assert run(repo.reserve_apartment_id("apt-x")) is False                  # never released (D-67)


def _two_admins(repo, tenant):
    for uid in ("adm-a", "adm-b"):
        run(repo.upsert_user(User(uid=f"{tenant}-{uid}", email=f"{uid}@{tenant}.it", tenant_id=tenant, role="admin")))
    return f"{tenant}-adm-a", f"{tenant}-adm-b"


def test_last_admin_concurrent_demotions(repo):
    # P-36 point 14b: A demotes B while B demotes A, at the same moment: exactly one may succeed
    a, b = _two_admins(repo, "tc1")

    async def both():
        ua, ub = await repo.get_user(a), await repo.get_user(b)
        ua.role, ub.role = "viewer", "viewer"
        return await asyncio.gather(repo.upsert_user_keeping_an_admin(ua), repo.upsert_user_keeping_an_admin(ub))
    results = run(both())
    assert sorted(results) == [False, True]
    assert [u.role for u in run(repo.list_users("tc1"))].count("admin") == 1
    ok = run(repo.get_user(a)).model_copy(update={"display_name": "Nome"})        # other changes still pass
    assert run(repo.upsert_user_keeping_an_admin(ok)) is True


def test_last_admin_concurrent_deletions(repo):
    a, b = _two_admins(repo, "tc2")

    async def both():
        return await asyncio.gather(repo.delete_user_keeping_an_admin(a), repo.delete_user_keeping_an_admin(b))
    assert sorted(run(both())) == ["deleted", "last_admin"]
    assert len(run(repo.list_users("tc2"))) == 1
    assert run(repo.delete_user_keeping_an_admin("nessuno")) == "not_found"
    run(repo.upsert_user(User(uid="tc2-viewer", email="v@tc2.it", tenant_id="tc2", role="viewer")))
    assert run(repo.delete_user_keeping_an_admin("tc2-viewer")) == "deleted"      # non-admins are never blocked


def test_last_platform_manager_concurrent_removals(repo):
    from bff.repository import PlatformMember

    run(repo.add_platform_member(PlatformMember(email="g1@x.it")))
    run(repo.add_platform_member(PlatformMember(email="g2@x.it")))

    async def both():
        return await asyncio.gather(repo.remove_platform_member_keeping_one("g1@x.it"),
                                    repo.remove_platform_member_keeping_one("G2@x.it"))
    assert sorted(run(both())) == ["last", "removed"]
    assert len(run(repo.list_platform_members())) == 1
    assert run(repo.remove_platform_member_keeping_one("nessuno@x.it")) == "not_found"


def test_external_id_claims(repo):
    # P-36 point 7: an Italianway code is claimed atomically by one apartment
    assert run(repo.claim_external_id("italianway", "IW-X", "apt-1")) is None
    assert run(repo.claim_external_id("italianway", "IW-X", "apt-1")) is None      # same owner: idempotent
    assert run(repo.claim_external_id("italianway", "IW-X", "apt-2")) == "apt-1"
    run(repo.release_external_id("italianway", "IW-X", "apt-2"))                    # not the owner: no effect
    assert run(repo.claim_external_id("italianway", "IW-X", "apt-2")) == "apt-1"
    run(repo.release_external_id("italianway", "IW-X", "apt-1"))
    assert run(repo.claim_external_id("italianway", "IW-X", "apt-2")) is None


def _entry(tenant_id, n, action="invite_sent"):
    from bff.repository.base import AuditActor, AuditEntry, AuditTarget

    at = f"2026-10-16T10:00:{n:02d}.000Z"
    return AuditEntry(audit_id=f"{at}-{n:08x}", at=at, tenant_id=tenant_id, action=action,
                      actor=AuditActor(kind="user", ref="u1"), target=AuditTarget(type="user", id="u2", ref="u2"),
                      details={"role": "viewer"})


def test_audit_log_per_tenant_newest_first_with_cursor(repo):
    """P-47: one log per organisation plus the platform's (None), newest first, paged by audit_id."""
    for n in range(5):
        run(repo.add_audit(_entry("t1", n)))
    run(repo.add_audit(_entry("t2", 9)))
    run(repo.add_audit(_entry(None, 7, "manager_added")))
    first = run(repo.list_audit("t1", 2))
    assert [e.audit_id[17:19] for e in first] == ["04", "03"]
    second = run(repo.list_audit("t1", 2, first[-1].audit_id))
    assert [e.audit_id[17:19] for e in second] == ["02", "01"]
    assert [e.audit_id[17:19] for e in run(repo.list_audit("t1", 10, second[-1].audit_id))] == ["00"]
    assert [e.tenant_id for e in run(repo.list_audit("t2", 10))] == ["t2"]                # never another tenant's
    platform = run(repo.list_audit(None, 10))
    assert [e.action for e in platform] == ["manager_added"]
    assert first[0].details == {"role": "viewer"} and first[0].target.ref == "u2"


def test_audit_people_resolved_and_forgotten(repo):
    from bff.repository.base import AuditPerson

    run(repo.put_audit_person(AuditPerson(ref="u1", email="a@x.it", display_name="Anna")))
    run(repo.put_audit_person(AuditPerson(ref="u2", email="b@x.it")))
    people = run(repo.get_audit_people(["u1", "u2", "u1", "nessuno"]))
    assert set(people) == {"u1", "u2"} and people["u1"].display_name == "Anna"
    assert run(repo.get_audit_people([])) == {}
    assert run(repo.delete_audit_person("u1")) is True
    assert run(repo.delete_audit_person("u1")) is False
    assert set(run(repo.get_audit_people(["u1", "u2"]))) == {"u2"}


def test_a_named_database_is_another_world():
    """P-67 (D-136): staging writes to its own database of the same project, production never sees it (emulator)."""
    from bff.repository.firestore import FirestoreRepository
    if "FIRESTORE_EMULATOR_HOST" not in os.environ:
        pytest.skip("solo con l'emulatore di Firestore")
    project, prefix = os.environ.get("GCP_PROJECT_ID", "demo-test"), f"t{uuid.uuid4().hex[:8]}_"
    staging = FirestoreRepository(project_id=project, prefix=prefix, database="staging")
    prod = FirestoreRepository(project_id=project, prefix=prefix)
    run(staging.upsert_tenant(Tenant(tenant_id="t-solo-staging", name="Solo staging")))
    assert run(staging.get_tenant("t-solo-staging")).name == "Solo staging"
    assert run(prod.get_tenant("t-solo-staging")) is None and staging.database == "staging" and prod.database == "(default)"


def _list_demos(env_extra: dict, timeout: float = 60):
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    env = {**os.environ, "REPOSITORY": "firestore", "GCP_PROJECT_ID": os.environ.get("GCP_PROJECT_ID", "demo-test"),
           **env_extra}
    return subprocess.run([sys.executable, str(root / "scripts" / "list_demos.py")], cwd=root, env=env,
                          capture_output=True, text=True, encoding="utf-8", timeout=timeout)


def test_list_demos_reads_firestore_and_says_when_it_does_not_answer():
    """P-67 M1 (D-136): the read-only list of the demonstrations against the emulator; with nothing listening, a clear
    message within the time limit instead of a silent wait (seen on 21 Oct)."""
    if "FIRESTORE_EMULATOR_HOST" not in os.environ:
        pytest.skip("solo con l'emulatore di Firestore")
    r = _list_demos({"FIRESTORE_DATABASE": f"d{uuid.uuid4().hex[:8]}"})       # an empty database of its own
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines()[0].startswith("Database Firestore d") and "Nessun appartamento dimostrativo" in r.stdout
    r = _list_demos({"FIRESTORE_EMULATOR_HOST": "127.0.0.1:9", "FIRESTORE_TIMEOUT_S": "3"})   # nobody answers
    assert r.returncode == 2 and "Firestore non risponde entro 3 secondi" in r.stdout and "quota project" in r.stdout
    assert r.stdout.splitlines()[0].startswith("Database Firestore")       # the first line came at once


def test_ai_usage_adds_up_and_alerts_once(repo):
    """P-60 step 9: the assistant's spending of a month adds up atomically; the 80 % alert is claimed once."""
    assert run(repo.get_ai_usage("2026-10")) == {"cost_eur": 0.0, "calls": 0, "input_tokens": 0, "output_tokens": 0,
                                                "alerted": False}
    run(repo.add_ai_usage("2026-10", 0.5, 1000, 200))
    totals = run(repo.add_ai_usage("2026-10", 0.25, 10, 2))
    assert (totals["calls"], totals["input_tokens"], totals["output_tokens"]) == (2, 1010, 202)
    assert totals["cost_eur"] == pytest.approx(0.75) and run(repo.get_ai_usage("2026-10"))["cost_eur"] == pytest.approx(0.75)
    assert run(repo.get_ai_usage("2026-11"))["calls"] == 0                  # another month starts from zero
    assert run(repo.mark_ai_alert("2026-10")) is True
    assert run(repo.mark_ai_alert("2026-10")) is False
    assert run(repo.get_ai_usage("2026-10"))["alerted"] is True and run(repo.mark_ai_alert("2026-11")) is True


def test_mail_quota_all_or_nothing(repo):
    """P-49: every bucket below its limit -> all go up by one; one bucket full -> none changes."""
    assert run(repo.take_mail_quota([("a", 2), ("b", 1)])) is True
    assert run(repo.take_mail_quota([("a", 2), ("b", 1)])) is False      # b is full: a must not move
    assert run(repo.take_mail_quota([("a", 2)])) is True                  # a was still at 1
    assert run(repo.take_mail_quota([("a", 2)])) is False
    assert run(repo.take_mail_quota([("c", 1)])) is True


def test_update_tenant_changes_only_the_given_fields(repo):
    """P-50: a rename or a features change written after a suspension never undoes it."""
    run(repo.upsert_tenant(Tenant(tenant_id="t1", name="Uno", enabled_features=["devices"])))
    run(repo.update_tenant("t1", {"status": "suspended", "suspended_reason": "Fattura"}))
    t = run(repo.update_tenant("t1", {"name": "Uno bis"}))
    assert (t.name, t.status, t.suspended_reason, t.enabled_features) == ("Uno bis", "suspended", "Fattura", ["devices"])
    assert run(repo.get_tenant("t1")).status == "suspended"
    assert run(repo.update_tenant("nessuna", {"name": "x"})) is None


def test_support_access_by_tenant_and_operator(repo):
    from bff.repository.base import SupportAccess

    def acc(aid, tenant, op, opened):
        return SupportAccess(access_id=aid, tenant_id=tenant, operator_uid=op, operator_email=f"{op}@hqe.it", reason="r",
                             opened_at=opened, expires_at="2099-01-01T00:00:00.000Z")
    run(repo.add_support_access(acc("sa-1", "t1", "m1", "2026-10-16T10:00:00.000Z")))
    run(repo.add_support_access(acc("sa-2", "t1", "m2", "2026-10-16T11:00:00.000Z")))
    run(repo.add_support_access(acc("sa-3", "t2", "m1", "2026-10-16T12:00:00.000Z")))
    assert [a.access_id for a in run(repo.list_support_access(tenant_id="t1"))] == ["sa-2", "sa-1"]   # newest first
    assert [a.access_id for a in run(repo.list_support_access(operator_uid="m1"))] == ["sa-3", "sa-1"]
    closed = run(repo.update_support_access("sa-1", {"closed_at": "2026-10-16T10:30:00.000Z", "closed_by": "admin"}))
    assert closed.closed_by == "admin" and run(repo.get_support_access("sa-1")).closed_at == "2026-10-16T10:30:00.000Z"
    assert run(repo.update_support_access("sa-nessuno", {"closed_at": "x"})) is None
    assert run(repo.get_support_access("sa-nessuno")) is None


def test_actor_pseudonyms_claimed_once_and_forgotten(repo):
    """P-48: the first pseudonym claimed for a person stays theirs; forgetting removes both directions."""
    from bff.repository.base import ActorRecord

    assert run(repo.claim_actor_ref("u1", "p-aaa@pseudo.hqe.it")) == "p-aaa@pseudo.hqe.it"
    assert run(repo.claim_actor_ref("u1", "p-bbb@pseudo.hqe.it")) == "p-aaa@pseudo.hqe.it"   # the existing one wins
    run(repo.put_actor(ActorRecord(ref="p-aaa@pseudo.hqe.it", uid="u1", email="a@x.it")))
    got = run(repo.get_actors(["p-aaa@pseudo.hqe.it", "p-nessuno@pseudo.hqe.it"]))
    assert list(got) == ["p-aaa@pseudo.hqe.it"] and got["p-aaa@pseudo.hqe.it"].uid == "u1"
    assert run(repo.forget_actor("u1")) is True and run(repo.forget_actor("u1")) is False
    assert run(repo.get_actors(["p-aaa@pseudo.hqe.it"])) == {}
    assert run(repo.claim_actor_ref("u1", "p-ccc@pseudo.hqe.it")) == "p-ccc@pseudo.hqe.it"   # a new person, a new one


def test_support_access_closes_once(repo):
    """D-88: only one of two closings at the same moment closes it (closed_at still null), so one log entry."""
    from bff.repository.base import SupportAccess

    run(repo.add_support_access(SupportAccess(access_id="sa-c", tenant_id="t1", operator_uid="m1", operator_email="m@hqe.it",
                                              reason="r", opened_at="2026-10-16T10:00:00.000Z",
                                              expires_at="2099-01-01T00:00:00.000Z")))
    assert run(repo.close_support_access("sa-c", "2026-10-16T10:05:00.000Z", "admin")) is True
    assert run(repo.close_support_access("sa-c", "2026-10-16T10:06:00.000Z", "platform")) is False
    a = run(repo.get_support_access("sa-c"))
    assert (a.closed_at, a.closed_by) == ("2026-10-16T10:05:00.000Z", "admin")
    assert run(repo.close_support_access("sa-nessuno", "x", "admin")) is False


def test_support_access_listed_without_filters(repo):
    """D-91 F1: with no filter every access is listed (on Firestore it used to become operator_uid IS NULL: nothing)."""
    from bff.repository.base import SupportAccess

    for aid, tenant, op in (("sa-a", "t1", "m1"), ("sa-b", "t2", "m2")):
        run(repo.add_support_access(SupportAccess(access_id=aid, tenant_id=tenant, operator_uid=op, operator_email=f"{op}@hqe.it",
                                                  reason="r", opened_at=f"2026-10-16T10:0{aid[-1] == 'b' and 1 or 0}:00.000Z",
                                                  expires_at="2099-01-01T00:00:00.000Z")))
    assert sorted(a.access_id for a in run(repo.list_support_access())) == ["sa-a", "sa-b"]


def test_removing_a_manager_through_the_route_closes_their_accesses(repo, monkeypatch):
    """D-91 F1: the same, end to end through DELETE /app/platform/managers on each backend."""
    from bff import audit, support
    from bff.auth import Identity
    from bff.repository import PlatformMember, Tenant
    from bff.routes import platform

    for module in (audit, support, platform):
        monkeypatch.setattr(module, "get_repository", lambda: repo)
    run(repo.upsert_tenant(Tenant(tenant_id="t-rm", name="Rimozione")))
    for email in ("via@hqe.it", "resta@hqe.it"):
        run(repo.add_platform_member(PlatformMember(email=email)))
    leaving = Identity(uid="u-via", email="via@hqe.it", display_name="", user=None, platform_manager=True)
    staying = Identity(uid="u-resta", email="resta@hqe.it", display_name="", user=None, platform_manager=True)
    aid = run(platform.open_support_access("t-rm", platform.SupportOpen(hours=1, reason="r"), identity=leaving))["access_id"]
    assert run(platform.remove_manager({"email": "via@hqe.it"}, identity=staying)).status_code == 204
    assert run(repo.get_support_access(aid)).closed_at is not None


# -------- P-54 (D-94): expiry written for the Firestore TTL policies --------
def _firestore_only(repo):
    from bff.repository.firestore import FirestoreRepository

    if not isinstance(repo, FirestoreRepository):
        pytest.skip("expire_at esiste solo su Firestore (il TTL è di Firestore)")


def _expire(ref):
    return run(ref.get()).to_dict()["expire_at"]


def test_every_kept_record_gets_its_expiry(repo):
    from datetime import UTC, datetime, timedelta

    from bff.repository.base import ActorRecord, AuditPerson, BookingRecord, SupportAccess, WebhookLog

    _firestore_only(repo)
    run(repo.upsert_booking(BookingRecord(apartment_id="a1", booking_id="b1", checkin_at="2026-03-08T14:00:00.000Z",
                                          checkout_at="2026-03-10T10:00:00.000Z", source="italianway")))
    assert _expire(repo._col("bookings").document("a1__b1")) == datetime(2027, 3, 10, 10, tzinfo=UTC)
    e = _entry("t1", 1)
    run(repo.add_audit(e))
    assert _expire(repo._audit_col("t1").document(e.audit_id)) == datetime(2028, 10, 16, 10, 0, 1, tzinfo=UTC)
    p = _entry(None, 2, "manager_added")
    run(repo.add_audit(p))
    assert _expire(repo._audit_col(None).document(p.audit_id)) == datetime(2028, 10, 16, 10, 0, 2, tzinfo=UTC)
    run(repo.add_support_access(SupportAccess(access_id="sa-x", tenant_id="t1", operator_uid="m", operator_email="m@hqe.it",
                                              reason="r", opened_at="2026-10-16T10:00:00.000Z",
                                              expires_at="2026-10-16T12:00:00.000Z")))
    assert _expire(repo._col("support_access").document("sa-x")) == datetime(2028, 10, 16, 12, tzinfo=UTC)
    run(repo.add_webhook_log(WebhookLog(log_id="wh-x", received_at="2026-10-16T10:00:00.000Z", signature_ok=True,
                                        status_code=200, outcome="accepted", correlation_id="c")))
    assert _expire(repo._col("webhook_logs").document("wh-x")) == datetime(2027, 1, 14, 10, tzinfo=UTC)
    now = datetime.now(UTC)
    run(repo.take_mail_quota([("k", 5)]))
    assert timedelta(days=3) - timedelta(minutes=1) < _expire(repo._col("mail_limits").document("k")) - now < timedelta(days=3, minutes=1)
    run(repo.put_audit_person(AuditPerson(ref="u1", email="a@x.it")))
    run(repo.put_actor(ActorRecord(ref="p-x@pseudo.hqe.it", uid="u1", email="a@x.it")))
    for ref in (repo._col("audit_people").document("u1"), repo._col("actors").document("p-x@pseudo.hqe.it"),
                repo._col("actor_refs").document("u1")):
        assert timedelta(days=725) < _expire(ref) - now < timedelta(days=733)   # about 24 months from now
    assert run(repo._col("actor_refs").document("u1").get()).to_dict()["ref"] == "p-x@pseudo.hqe.it"


def test_backfill_counts_then_writes_only_where_missing(repo):
    import importlib.util
    from datetime import UTC, datetime
    from pathlib import Path

    _firestore_only(repo)
    spec = importlib.util.spec_from_file_location("backfill", Path(__file__).resolve().parent.parent / "scripts" / "backfill_expire_at.py")
    bf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bf)
    run(repo.upsert_tenant(Tenant(tenant_id="t-old", name="Vecchia")))
    old = {   # documents as saved before lot 11: no expire_at
        repo._col("bookings").document("a__b"): {"checkout_at": "2026-01-31T10:00:00.000Z"},
        repo._col("tenants").document("t-old").collection("audit").document("x"): {"at": "2026-10-01T08:00:00.000Z"},
        repo._col("webhook_logs").document("w"): {"received_at": "2026-10-01T08:00:00.000Z"},
        repo._col("audit_people").document("u"): {"email": "a@x.it"},
    }
    for ref, data in old.items():
        run(ref.set(data))
    kept = datetime(2030, 1, 1, tzinfo=UTC)
    run(repo._col("webhook_logs").document("w-new").set({"received_at": "2026-10-01T08:00:00.000Z", "expire_at": kept}))
    counts = run(bf.backfill(repo, apply=False))
    assert {k: v[0] for k, v in counts.items() if v[0]} == {"bookings": 1, "audit": 1, "webhook_logs": 1, "audit_people": 1}
    assert "expire_at" not in run(repo._col("bookings").document("a__b").get()).to_dict()      # only counted
    counts = run(bf.backfill(repo, apply=True))
    assert sum(v[1] for v in counts.values()) == 4
    assert _expire(repo._col("bookings").document("a__b")) == datetime(2027, 1, 31, 10, tzinfo=UTC)
    assert _expire(repo._col("webhook_logs").document("w-new")) == kept                       # an existing one stays
    assert sum(v[0] for v in run(bf.backfill(repo, apply=False)).values()) == 0              # idempotent


def test_weekly_summaries(repo):
    """P-60 step 11 (D-150): one summary per apartment and week, newest first; on Firestore it expires 12 months after
    it was made and the expiry never comes back to the caller."""
    def summary(apt, week, made):
        return {"apartment_id": apt, "week": week, "from": "x", "to": "y", "generated_at": made, "items": [], "notable": False}
    assert run(repo.get_summary("a1", "2026-W42")) is None and run(repo.list_summaries("a1")) == []
    run(repo.put_summary(summary("a1", "2026-W41", "2026-10-12T06:00:00.000Z")))
    run(repo.put_summary(summary("a1", "2026-W42", "2026-10-19T06:00:00.000Z")))
    run(repo.put_summary(summary("a2", "2026-W42", "2026-10-19T06:00:00.000Z")))
    assert run(repo.get_summary("a1", "2026-W42")) == summary("a1", "2026-W42", "2026-10-19T06:00:00.000Z")
    assert [s["week"] for s in run(repo.list_summaries("a1"))] == ["2026-W42", "2026-W41"]
    assert [s["week"] for s in run(repo.list_summaries("a1", limit=1))] == ["2026-W42"]
    assert "expire_at" not in run(repo.list_summaries("a2"))[0]
    from bff.repository.firestore import FirestoreRepository
    if isinstance(repo, FirestoreRepository):
        from datetime import UTC, datetime
        assert _expire(repo._col("summaries").document("a1__2026-W42")) == datetime(2027, 10, 19, 6, 0, tzinfo=UTC)


def test_assistant_weekly_counters(repo):
    """Decision 120 (D-183 point 129): ai_stats/{apartment}__{week}, an ask counted once, the causes, the twins; on
    Firestore it expires 12 months after the week's Monday."""
    bounds = ("2026-10-19", "2026-10-25")
    assert run(repo.get_ai_stats(["a1__2026-W43"])) == {} and run(repo.get_ai_stats([])) == {}
    assert run(repo.add_ai_stats("a1", "2026-W43", bounds, asks=1, timeouts=1, quick="timeout", ask_id="q1")) is True
    assert run(repo.add_ai_stats("a1", "2026-W43", bounds, asks=1, timeouts=1, quick="timeout", ask_id="q1")) is False
    assert run(repo.add_ai_stats("a1", "2026-W43", bounds, asks=1, ask_id="q2")) is True
    assert run(repo.add_ai_stats("a1", "2026-W43", bounds, twins=1)) is True
    d = run(repo.get_ai_stats(["a1__2026-W43", "a2__2026-W43"]))
    assert list(d) == ["a1__2026-W43"]
    d = d["a1__2026-W43"]
    assert (d["asks"], d["timeouts"], d["twins"], d["quick"], d["ask_ids"]) == (2, 1, 1, {"timeout": 1}, ["q1", "q2"])
    assert (d["apartment_id"], d["week"], d["from"], d["to"]) == ("a1", "2026-W43", "2026-10-19", "2026-10-25")
    from bff.repository.firestore import FirestoreRepository
    if isinstance(repo, FirestoreRepository):
        from datetime import UTC, datetime
        assert _expire(repo._col("ai_stats").document("a1__2026-W43")) == datetime(2027, 10, 19, tzinfo=UTC)
