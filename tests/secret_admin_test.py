"""A2 (docs/proposta-a2.md §3.3; project §2.2): the server creates an apartment's two secrets with fixed parameters,
reuses one only if it is ours (label domhouse-op = the creation's op, recorded in Firestore before) with the same
metadata, adds a version only when none is enabled, never logs a value, and for «Annulla» destroys the versions with
the 7-day delay. Here on a fake Secret Manager; bff.secret_admin.GcpSecrets maps the real client (its conversion of a
real Secret is checked at the end, without network)."""
import asyncio
import logging
from datetime import timedelta

import pytest

from bff import secret_admin as sa

OP = "00000000-0000-4000-8000-0000000000a2"


class FakeSecrets:
    """The small interface of bff.secret_admin.GcpSecrets, in memory."""

    def __init__(self):
        self.secrets: dict[str, dict] = {}
        self.versions: dict[str, list[dict]] = {}
        self.calls: list[tuple] = []
        self.fail_on: dict[str, Exception] = {}

    def _maybe_fail(self, what):
        if what in self.fail_on:
            raise self.fail_on[what]

    def create(self, secret_id, body):
        self.calls.append(("create", secret_id))
        self._maybe_fail("create")
        if secret_id in self.secrets:
            raise sa.SecretExists(secret_id)
        self.secrets[secret_id] = sa.describe_body(body)
        self.versions[secret_id] = []

    def describe(self, secret_id):
        self.calls.append(("describe", secret_id))
        return dict(self.secrets[secret_id])

    def enabled_versions(self, secret_id):
        return [v["name"] for v in self.versions[secret_id] if v["state"] == "ENABLED"]

    def add_version(self, secret_id, data: bytes):
        self.calls.append(("add_version", secret_id))
        self._maybe_fail("add_version")
        n = len(self.versions[secret_id]) + 1
        self.versions[secret_id].append({"name": f"{secret_id}/versions/{n}", "state": "ENABLED", "data": data})

    def live_versions(self, secret_id):
        if secret_id not in self.secrets:
            return []
        return [v["name"] for v in self.versions[secret_id] if v["state"] == "ENABLED"]

    def destroy(self, version_name):
        self.calls.append(("destroy", version_name))
        for vs in self.versions.values():
            for v in vs:
                if v["name"] == version_name:
                    v["state"] = "DISABLED_PENDING"


def run(coro):
    return asyncio.run(coro)


def test_the_two_names():
    assert sa.names("lab-07") == ("langbrain-api-key-lab-07", "langbrain-shelly-lab-07")


def test_the_body_has_the_fixed_parameters():
    body = sa.secret_body("staging", "lab-07", OP)
    d = sa.describe_body(body)
    assert d == {"locations": ["europe-west8"], "automatic": False, "cmek": False, "expire": False, "topics": 0,
                 "rotation": False, "destroy_ttl_s": 7 * 86400,
                 "labels": {"domhouse-env": "staging", "domhouse-apt": "lab-07", "domhouse-op": OP}}


def test_a_new_pair_is_created_with_one_version_each_of_the_right_length(caplog):
    sm = FakeSecrets()
    with caplog.at_level(logging.DEBUG):
        run(sa.ensure_pair(sm, "staging", "lab-07", OP))
    key, conn = sa.names("lab-07")
    assert [c[0] for c in sm.calls] == ["create", "add_version", "create", "add_version"]
    k = sm.versions[key][0]["data"].decode()
    c = sm.versions[conn][0]["data"].decode()
    assert len(k) == 43 and len(c) == 32 and k != c          # token_urlsafe(32) and (24)
    assert k not in caplog.text and c not in caplog.text


def test_a_retry_reuses_our_secrets_and_adds_no_second_version():
    sm = FakeSecrets()
    run(sa.ensure_pair(sm, "staging", "lab-07", OP))
    key, conn = sa.names("lab-07")
    first = (sm.versions[key][0]["data"], sm.versions[conn][0]["data"])
    run(sa.ensure_pair(sm, "staging", "lab-07", OP))
    assert len(sm.versions[key]) == 1 and len(sm.versions[conn]) == 1
    assert (sm.versions[key][0]["data"], sm.versions[conn][0]["data"]) == first


def test_a_retry_after_a_failed_version_adds_the_missing_one():
    sm = FakeSecrets()
    sm.fail_on["add_version"] = sa.SecretError("PermissionDenied")
    with pytest.raises(sa.SecretError):
        run(sa.ensure_pair(sm, "staging", "lab-07", OP))
    del sm.fail_on["add_version"]
    run(sa.ensure_pair(sm, "staging", "lab-07", OP))
    key, conn = sa.names("lab-07")
    assert len(sm.versions[key]) == 1 and len(sm.versions[conn]) == 1


@pytest.mark.parametrize("change", [
    {"labels": {"domhouse-env": "staging", "domhouse-apt": "lab-07", "domhouse-op": "another-op"}},   # not ours
    {"labels": {"domhouse-env": "prod", "domhouse-apt": "lab-07", "domhouse-op": OP}},
    {"locations": ["europe-west1"]},
    {"automatic": True},
    {"cmek": True},
    {"expire": True},
    {"topics": 1},
    {"rotation": True},
    {"destroy_ttl_s": 0},
])
def test_a_secret_that_is_not_ours_or_differs_is_a_conflict_and_gets_no_version(change):
    sm = FakeSecrets()
    key, _ = sa.names("lab-07")
    sm.secrets[key] = {**sa.describe_body(sa.secret_body("staging", "lab-07", OP)), **change}
    sm.versions[key] = []
    with pytest.raises(sa.SecretConflict) as e:
        run(sa.ensure_pair(sm, "staging", "lab-07", OP))
    assert e.value.name == key
    assert ("add_version", key) not in sm.calls


def test_destroy_pair_destroys_every_live_version_and_tolerates_missing_secrets():
    sm = FakeSecrets()
    run(sa.ensure_pair(sm, "staging", "lab-07", OP))
    run(sa.destroy_pair(sm, "lab-07"))
    key, conn = sa.names("lab-07")
    assert sm.versions[key][0]["state"] == sm.versions[conn][0]["state"] == "DISABLED_PENDING"
    run(sa.destroy_pair(sm, "lab-07"))                     # twice: nothing more to do
    run(sa.destroy_pair(sm, "lab-99"))                     # never created: nothing to do


def test_the_real_client_s_secret_is_converted_like_the_body():
    from google.cloud import secretmanager
    s = secretmanager.Secret(replication={"user_managed": {"replicas": [{"location": "europe-west8"}]}},
                             labels={"domhouse-env": "staging", "domhouse-apt": "lab-07", "domhouse-op": OP},
                             version_destroy_ttl=timedelta(days=7))
    assert sa.describe_secret(s) == sa.describe_body(sa.secret_body("staging", "lab-07", OP))
    auto = secretmanager.Secret(replication={"automatic": {}}, labels={})
    d = sa.describe_secret(auto)
    assert d["automatic"] is True and d["locations"] == [] and d["destroy_ttl_s"] == 0
    cmek = secretmanager.Secret(replication={"user_managed": {"replicas": [
        {"location": "europe-west8", "customer_managed_encryption": {"kms_key_name": "k"}}]}})
    assert sa.describe_secret(cmek)["cmek"] is True
