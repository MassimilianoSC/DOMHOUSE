"""scripts/load/ambiente.py (P-84): what the load test needs in staging and its removal, on the memory repository with
stand-ins for Firebase Authentication and Secret Manager that record what they are asked. Proved: the dry run writes
nothing; prepara makes the secrets (one region, label, the two readers), the organisation, the apartments on the VM's
ports, the people (staging claims only, operators, one apartment each) and the file for the tool; it can run again;
pulisci removes all of it, the apartments first, and nothing else; verifica says what is left."""
import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

from bff.repository import Apartment, Tenant, User
from bff.repository.memory import InMemoryRepository

ROOT = Path(__file__).resolve().parent.parent


def load():
    spec = importlib.util.spec_from_file_location("ambiente", ROOT / "scripts" / "load" / "ambiente.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


amb = load()


class FakeUser:
    def __init__(self, uid, email, **kw):
        self.uid, self.email, self.custom_claims = uid, email, None
        self.password, self.email_verified = kw.get("password"), kw.get("email_verified", False)


class FakeAuth:
    class UserNotFoundError(Exception):
        pass

    def __init__(self):
        self.users: dict[str, FakeUser] = {}
        self.calls: list[str] = []

    def get_user_by_email(self, email):
        for u in self.users.values():
            if u.email == email:
                return u
        raise self.UserNotFoundError(email)

    def create_user(self, email, password, email_verified, display_name):
        self.calls.append(f"create {email}")
        u = FakeUser(f"uid-{len(self.users) + 1}", email, password=password, email_verified=email_verified)
        self.users[u.uid] = u
        return u

    def update_user(self, uid, password, email_verified):
        self.calls.append(f"update {uid}")
        self.users[uid].password, self.users[uid].email_verified = password, email_verified

    def set_custom_user_claims(self, uid, claims):
        self.calls.append(f"claims {uid}")
        self.users[uid].custom_claims = claims

    def delete_user(self, uid):
        self.calls.append(f"delete {self.users[uid].email}")
        del self.users[uid]

    def list_users(self):
        users = list(self.users.values())

        class Page:
            def iterate_all(self):
                return iter(users)
        return Page()


class FakeSecrets:
    def __init__(self):
        self.store: dict[str, dict] = {}
        self.calls: list[str] = []

    def exists(self, name):
        return name in self.store

    def labelled(self):
        return sorted(n for n, s in self.store.items() if s["labels"].get("domhouse") == "carico")

    def create(self, name):
        self.calls.append(f"create {name}")
        self.store[name] = {"versions": [], "readers": [], "labels": {"domhouse": "carico"}, "location": amb.LOCATION}

    def has_version(self, name):
        return bool(self.store[name]["versions"])

    def add_version(self, name, value):
        self.calls.append(f"version {name}")
        self.store[name]["versions"].append(value)

    def grant(self, name, members):
        self.calls.append(f"grant {name}")
        self.store[name]["readers"] = sorted(set(self.store[name]["readers"]) | set(members))

    def delete(self, name):
        self.calls.append(f"delete {name}")
        del self.store[name]


@pytest.fixture
def env(tmp_path):
    repo = InMemoryRepository()
    repo.tenants["t-altra"] = Tenant(tenant_id="t-altra", name="Altra")
    repo.apartments["apt-vero"] = Apartment(apartment_id="apt-vero", tenant_id="t-altra", name="Vero",
                                            instance_url="http://10.198.0.2:8100")
    repo.users["u-vero"] = User(uid="u-vero", email="vero@esempio.it", tenant_id="t-altra", role="admin")
    auth, secrets = FakeAuth(), FakeSecrets()
    auth.users["fb-vero"] = FakeUser("fb-vero", "vero@esempio.it")
    secrets.store["langbrain-api-key-dev"] = {"versions": ["k"], "readers": [], "labels": {}, "location": "x"}
    return amb.Env(repo, auth, secrets, "progetto", "10.198.0.2", "https://staging.example", tmp_path / "logs" / "u.json",
                   api_key=lambda: "chiave-pubblica-del-sito")


def run(coro):
    return asyncio.run(coro)


def test_the_dry_run_writes_nothing(env):
    before = (dict(env.repo.tenants), dict(env.repo.apartments), dict(env.repo.users))
    run(amb.prepare(env, 3, 6, dry=True))
    assert (env.repo.tenants, env.repo.apartments, env.repo.users) == before
    assert env.auth.calls == [] and env.secrets.calls == [] and not env.users_file.exists()
    run(amb.prepare(env, 3, 6, dry=False))
    snapshot = (len(env.repo.users), len(env.auth.users), len(env.secrets.store))
    env.auth.calls.clear()
    env.secrets.calls.clear()
    run(amb.clean(env, dry=True))
    assert (len(env.repo.users), len(env.auth.users), len(env.secrets.store)) == snapshot
    assert env.auth.calls == [] and env.secrets.calls == [] and env.users_file.exists()


def test_prepare_makes_secrets_organisation_apartments_people_and_the_file(env):
    run(amb.prepare(env, 5, 12, dry=False))
    ids = [f"carico-{i:02d}" for i in range(1, 6)]
    for apt in ids:
        s = env.secrets.store[f"langbrain-api-key-{apt}"]
        assert s["location"] == "europe-west8" and s["labels"] == {"domhouse": "carico"} and len(s["versions"]) == 1
        assert s["readers"] == ["serviceAccount:domotica-bff@progetto.iam.gserviceaccount.com",
                                "serviceAccount:langbrain-vm@progetto.iam.gserviceaccount.com"]
    assert len({env.secrets.store[f"langbrain-api-key-{a}"]["versions"][0] for a in ids}) == 5   # five different keys
    assert env.repo.tenants["t-carico-prova"].name == "Carico (prova)"
    assert [(a, env.repo.apartments[a].instance_url) for a in ids] == [
        (a, f"http://10.198.0.2:{8150 + i}") for i, a in enumerate(ids)]
    assert all(env.repo.apartments[a].tenant_id == "t-carico-prova" for a in ids)
    people = [u for u in env.auth.users.values() if u.email.endswith("@carico.domhouse.invalid")]
    assert len(people) == 12
    for u in people:
        assert u.custom_claims == {"staging": {"tenant_id": "t-carico-prova", "role": "operator"}}   # never production
        assert u.email_verified and u.password
        rec = env.repo.users[u.uid]
        assert rec.role == "operator" and rec.tenant_id == "t-carico-prova" and not rec.push_tokens
        assert len(rec.apartment_ids) == 1
    data = json.loads(env.users_file.read_text(encoding="utf-8"))
    assert data["bff_url"] == "https://staging.example" and data["firebase_api_key"] == "chiave-pubblica-del-sito"
    assert data["service"] == "domotica-bff-staging" and data["database"] == "staging"
    assert [u["apartment_id"] for u in data["utenti"]][:6] == ids + ["carico-01"]           # in turn
    assert {u["email"]: u["password"] for u in data["utenti"]} == {u.email: u.password for u in people}
    # the real organisation is untouched
    assert env.repo.apartments["apt-vero"].tenant_id == "t-altra" and "u-vero" in env.repo.users


def test_prepare_again_keeps_the_keys_and_renews_the_passwords(env):
    run(amb.prepare(env, 2, 3, dry=False))
    keys = {n: list(s["versions"]) for n, s in env.secrets.store.items()}
    first = json.loads(env.users_file.read_text(encoding="utf-8"))["utenti"]
    run(amb.prepare(env, 2, 3, dry=False))
    assert {n: s["versions"] for n, s in env.secrets.store.items()} == keys          # the engines keep reading them
    second = json.loads(env.users_file.read_text(encoding="utf-8"))["utenti"]
    assert [u["email"] for u in second] == [u["email"] for u in first]
    assert all(a["password"] != b["password"] for a, b in zip(first, second))
    assert len([u for u in env.auth.users.values() if amb.is_test_email(u.email)]) == 3


def test_an_apartment_of_another_organisation_stops_everything(env):
    env.repo.apartments["carico-02"] = Apartment(apartment_id="carico-02", tenant_id="t-altra", name="x",
                                                 instance_url="http://x")
    with pytest.raises(SystemExit, match="un'altra organizzazione"):
        run(amb.prepare(env, 3, 3, dry=False))
    assert env.repo.apartments["carico-02"].tenant_id == "t-altra"


def test_clean_removes_everything_of_the_test_and_nothing_else(env, capsys):
    run(amb.prepare(env, 3, 6, dry=False))
    uid = next(u.uid for u in env.auth.users.values() if amb.is_test_email(u.email))
    run(env.repo.claim_actor_ref(uid, "p-1"))                       # what the server writes when a person acts
    env.repo.actors["p-1"] = object()
    env.repo.stream_cursors["carico-01"] = {"last_id": "9"}
    env.repo.audit["t-carico-prova"] = {"a": object()}
    capsys.readouterr()
    run(amb.clean(env, dry=False))
    printed = capsys.readouterr().out
    assert printed.index("Appartamenti di prova") < printed.index("Persone di prova") < printed.index("Segreti")
    assert run(amb.left(env)) == []
    assert not any(a.startswith("carico-") for a in env.repo.apartments) and "carico-01" not in env.repo.stream_cursors
    assert uid not in env.repo.actor_refs and "p-1" not in env.repo.actors and "t-carico-prova" not in env.repo.audit
    assert not env.users_file.exists()
    # the rest of the project is untouched
    assert "apt-vero" in env.repo.apartments and "u-vero" in env.repo.users and "t-altra" in env.repo.tenants
    assert "fb-vero" in env.auth.users and "langbrain-api-key-dev" in env.secrets.store


def test_verify_lists_what_is_left(env):
    run(amb.prepare(env, 1, 1, dry=False))
    remaining = run(amb.left(env))
    assert "organizzazione t-carico-prova" in remaining and "appartamento carico-01" in remaining
    assert "segreto langbrain-api-key-carico-01" in remaining and "account Firebase carico-01@carico.domhouse.invalid" in remaining
    assert any(r.startswith("file ") for r in remaining)


def test_the_site_key_is_read_from_the_build_file_and_never_invented(tmp_path):
    f = tmp_path / ".env.production"
    f.write_text("VITE_APP_NAME=x\nVITE_FIREBASE_API_KEY=abc123\n", encoding="utf-8")
    assert amb.site_api_key(f) == "abc123"
    f.write_text("VITE_FIREBASE_API_KEY=\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        amb.site_api_key(f)
    with pytest.raises(SystemExit):
        amb.site_api_key(tmp_path / "manca")


def test_the_real_secret_store_adds_only_the_missing_readers_with_the_librarys_own_objects():
    from google.iam.v1 import policy_pb2

    class Client:
        def __init__(self):
            self.policy = policy_pb2.Policy()
            b = self.policy.bindings.add()
            b.role = "roles/secretmanager.secretAccessor"
            b.members.append("serviceAccount:domotica-bff@progetto.iam.gserviceaccount.com")
            self.set_calls = 0

        def get_iam_policy(self, request):
            return self.policy

        def set_iam_policy(self, request):
            self.set_calls += 1
            self.policy = request["policy"]
            return self.policy
    store = amb.Secrets.__new__(amb.Secrets)
    store.client, store.project = Client(), "progetto"
    readers = ["serviceAccount:domotica-bff@progetto.iam.gserviceaccount.com",
               "serviceAccount:langbrain-vm@progetto.iam.gserviceaccount.com"]
    store.grant("langbrain-api-key-carico-01", readers)
    store.grant("langbrain-api-key-carico-01", readers)               # again: nothing to add, no write
    assert store.client.set_calls == 1
    (binding,) = store.client.policy.bindings
    assert sorted(binding.members) == readers
