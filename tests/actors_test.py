"""P-48 (D-87): the engine sees only pseudonyms; the BFF shows the organisation the email of its own members and of HQE
managers, and "user:removed" / "removed" for anyone else, including people who erased their account. In-process."""
import asyncio

from bff import actors
from bff.repository import Tenant, User, get_repository

TENANT, OTHER = "t-actors", "t-actors-other"


def run(coro):
    return asyncio.run(coro)


def setup_people():
    repo = get_repository()
    for t in (TENANT, OTHER):
        run(repo.upsert_tenant(Tenant(tenant_id=t, name=t)))
    run(repo.upsert_user(User(uid="u-act-1", email="anna@actors.it", tenant_id=TENANT, role="operator")))
    run(repo.upsert_user(User(uid="u-act-2", email="bruno@altro.it", tenant_id=OTHER, role="admin")))
    actors._resolved.clear()


def test_one_pseudonym_per_person_never_the_email():
    setup_people()
    ref = run(actors.actor_for("u-act-1", "anna@actors.it"))
    assert actors.is_pseudonym(ref) and "anna" not in ref
    actors._refs.clear()                                                   # another process: same pseudonym
    assert run(actors.actor_for("u-act-1", "anna@actors.it")) == ref
    assert run(actors.actor_for("u-act-2", "bruno@altro.it")) != ref


def test_decisions_approvals_and_hold_are_rewritten():
    setup_people()
    anna = run(actors.actor_for("u-act-1", "anna@actors.it"))
    bruno = run(actors.actor_for("u-act-2", "bruno@altro.it"))
    manager = run(actors.actor_for("dev-piattaforma", "piattaforma@demo.it"))   # seed platform manager (support)
    payload = {
        "items": [{"decision_id": "d1", "actor": f"user:{anna}"}, {"decision_id": "d2", "actor": f"user:{bruno}"},
                  {"decision_id": "d3", "actor": "rule:window_open_off"}, {"decision_id": "d4", "actor": "system"},
                  {"decision_id": "d5", "actor": f"user:{manager}"}, {"decision_id": "d6", "actor": "user:vecchio@actors.it"},
                  {"decision_id": "d7", "actor": "user:anna@actors.it"}],
        "approvals": [{"approval_id": "a1", "decided_by": anna}, {"approval_id": "a2", "decided_by": None}],
        "apartment": {"hold": {"mode": "eco", "until": "2026-10-16T20:00:00Z", "set_by": bruno}},
    }
    out = run(actors.rewrite(payload, TENANT))
    assert [d["actor"] for d in out["items"]] == [
        "user:anna@actors.it",          # a member: the email
        "user:removed",                 # someone of ANOTHER organisation: never revealed
        "rule:window_open_off", "system",
        "user:piattaforma@demo.it",     # HQE support: real identity (D-86)
        "user:removed",                 # an old decision with the email of someone no longer here
        "user:anna@actors.it",          # an old decision of a member: still readable
    ]
    assert [a["decided_by"] for a in out["approvals"]] == ["anna@actors.it", None]
    assert out["apartment"]["hold"]["set_by"] == "removed"
    assert payload["items"][0]["actor"] == f"user:{anna}"   # the input is not modified


def test_erased_person_reads_removed():
    setup_people()
    anna = run(actors.actor_for("u-act-1", "anna@actors.it"))
    assert run(actors.rewrite({"actor": f"user:{anna}"}, TENANT)) == {"actor": "user:anna@actors.it"}
    run(get_repository().delete_user("u-act-1"))
    run(actors.forget("u-act-1"))
    assert run(actors.rewrite({"actor": f"user:{anna}", "decided_by": anna}, TENANT)) == {
        "actor": "user:removed", "decided_by": "removed"}
    assert run(get_repository().get_actors([anna])) == {}


def test_nothing_to_do_returns_the_same_object():
    payload = {"devices": [{"device_id": "x"}]}
    assert run(actors.rewrite(payload, TENANT)) is payload


def test_stream_events_are_rewritten():
    import json

    from bff.routes.apartments import _event
    from bff.sse_hub import SseEvent

    setup_people()
    anna = run(actors.actor_for("u-act-1", "anna@actors.it"))
    env = {"id": "7", "event": "decision.logged", "apartment_id": "apt-x", "data": {"decision_id": "d", "actor": f"user:{anna}"}}
    out = run(_event(SseEvent(id="7", event="decision.logged", data=json.dumps(env), received=0.0), TENANT))
    assert "anna@actors.it" in out and anna not in out and out.startswith("id: 7\nevent: decision.logged\n")
    plain = SseEvent(id="8", event="device.state", data=json.dumps({"data": {"device_id": "x"}}), received=0.0)
    assert run(_event(plain, TENANT)) == plain.encode()


def test_the_pseudonym_belongs_to_the_person_not_to_an_organisation():
    """Fable on D-87: a manager inside an organisation through a support access has no record there; their pseudonym
    is bound to their uid and still shows their real identity (D-86), in any organisation they assist."""
    setup_people()
    ref = run(actors.actor_for("dev-piattaforma@demo.it", "piattaforma@demo.it"))
    for tenant in (TENANT, OTHER):
        assert run(actors.rewrite({"actor": f"user:{ref}"}, tenant)) == {"actor": "user:piattaforma@demo.it"}


def test_the_pseudonym_expiry_is_renewed_at_most_weekly(monkeypatch):
    """P-54: actor_for rewrites the mapping (and so its expiry) at most once a week per process."""
    repo = get_repository()
    writes, clock = [], [1000.0]
    real_put = repo.put_actor

    async def counting(record):
        writes.append(record.uid)
        return await real_put(record)
    monkeypatch.setattr(repo, "put_actor", counting)
    monkeypatch.setattr(actors.time, "monotonic", lambda: clock[0])
    actors._refs.clear()
    ref = run(actors.actor_for("u-renew", "r@x.it"))
    clock[0] += actors.RENEW_SECONDS - 1
    assert run(actors.actor_for("u-renew", "r@x.it")) == ref and writes == ["u-renew"]
    clock[0] += 2
    assert run(actors.actor_for("u-renew", "r@x.it")) == ref and writes == ["u-renew", "u-renew"]   # renewed, same one
