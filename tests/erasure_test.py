"""P-48 (D-87): after erase_person no trace of the person's email or name is left in the BFF's records; their actions
stay, as «utente rimosso». In-process, memory repository."""
import asyncio

from bff import actors, audit, erasure
from bff.repository import PlatformMember, SupportAccess, Tenant, User, get_repository

UID, EMAIL = "u-erase", "Cancella.Me@Esempio.it"


def run(coro):
    return asyncio.run(coro)


def test_every_trace_goes_and_the_actions_stay():
    repo = get_repository()
    run(repo.upsert_tenant(Tenant(tenant_id="t-erase", name="Da cancellare", created_by="cancella.me@esempio.it",
                                  first_admin_email="cancella.me@esempio.it")))
    run(repo.add_platform_member(PlatformMember(email="aggiunto@esempio.it", added_by="cancella.me@esempio.it")))
    run(repo.add_support_access(SupportAccess(access_id="sa-erase", tenant_id="t-erase", operator_uid=UID,
                                              operator_email="cancella.me@esempio.it", operator_name="Cancella Me",
                                              reason="Guasto", opened_at="2026-10-16T10:00:00.000Z",
                                              expires_at="2026-10-16T11:00:00.000Z")))
    me = User(uid=UID, email="cancella.me@esempio.it", display_name="Cancella Me", tenant_id="t-erase", role="admin")
    run(audit.record("invite_resent", audit.by_user(me), "t-erase", audit.user_target(me)))
    ref = run(actors.actor_for(UID, "cancella.me@esempio.it"))

    run(erasure.erase_person(UID, EMAIL))

    t = run(repo.get_tenant("t-erase"))
    assert t.created_by == "" and t.first_admin_email is None and t.name == "Da cancellare"
    assert run(repo.get_platform_member("aggiunto@esempio.it")).added_by == ""
    a = run(repo.get_support_access("sa-erase"))
    assert (a.operator_email, a.operator_name, a.reason) == ("", "", "Guasto")       # the access itself stays
    item = run(audit.page("t-erase", 10, None, viewer="admin"))["items"][0]
    assert item["action"] == "invite_resent" and item["actor"]["removed"] is True and item["target"]["removed"] is True
    assert run(repo.get_actors([ref])) == {}


def test_a_failing_step_does_not_stop_the_others(monkeypatch):
    repo = get_repository()
    run(repo.upsert_tenant(Tenant(tenant_id="t-erase-2", name="Altra", created_by="due@esempio.it")))

    async def broken(uid, email):
        raise RuntimeError("registro non raggiungibile")
    monkeypatch.setattr(audit, "forget", broken)
    run(erasure.erase_person("u-erase-2", "due@esempio.it"))
    assert run(repo.get_tenant("t-erase-2")).created_by == ""
