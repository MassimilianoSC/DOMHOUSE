"""Tool A, package A2 (docs/proposta-a2.md §3.3; docs/progetto-strumento-a-base.md §2.2, §4.1): the two secrets of an
apartment created from the app.

- `langbrain-api-key-<apt>`: the engine's key (secrets.token_urlsafe(32)); the server reads it to call the engine.
- `langbrain-shelly-<apt>`: the connector's password on the broker (secrets.token_urlsafe(24)); only the VM reads it.
  The server GENERATES it: «does not read it» means it can never get it back after the creation (review point 13).

Every secret is created with fixed parameters (user-managed replica in europe-west8 only; no expireTime, topics,
rotation or CMEK; labels domhouse-env, domhouse-apt, domhouse-op; 7 days of delayed destruction). One that already
exists is reused only if it is ours (domhouse-op = the creation's op, which the caller recorded in Firestore BEFORE
calling) and its metadata are exactly these: otherwise SecretConflict and no version is added. A version is added
only when the secret has no enabled one, so a «Riprova» never changes a key the engine may already use. The values go
only to versions.add: never to a log, an order or Firestore.

The calls to Secret Manager have a 20 s timeout and no automatic retry (20 November: a retry loop hid an expired
credential for minutes); the creation's «Riprova» is the retry.
"""
from __future__ import annotations

import asyncio
import secrets
from datetime import timedelta

LOCATION = "europe-west8"
DESTROY_TTL = timedelta(days=7)
CONNECTOR_PREFIX = "langbrain-shelly-"
CALL_TIMEOUT_S = 20


class SecretExists(Exception):
    """create() of a secret id that exists."""


class SecretError(Exception):
    """Secret Manager refused or failed (the message is the error's class, never a value)."""


class SecretConflict(Exception):
    """A secret with our name exists and is not ours, or its metadata differ: nothing is added (409 secret_conflict)."""

    def __init__(self, name: str):
        super().__init__(name)
        self.name = name


def names(apartment_id: str) -> tuple[str, str]:
    """(engine key, connector password): the same names the VM reads (engine-vm.sh write_key)."""
    from .instances import secret_name
    return secret_name(apartment_id), f"{CONNECTOR_PREFIX}{apartment_id}"


def labels_for(env: str, apartment_id: str, op: str) -> dict[str, str]:
    return {"domhouse-env": env, "domhouse-apt": apartment_id, "domhouse-op": op}


def secret_body(env: str, apartment_id: str, op: str) -> dict:
    """The Secret to create, as the client takes it."""
    return {"replication": {"user_managed": {"replicas": [{"location": LOCATION}]}},
            "labels": labels_for(env, apartment_id, op), "version_destroy_ttl": DESTROY_TTL}


def describe_secret(secret) -> dict:
    """What we compare of a Secret (google.cloud.secretmanager.Secret), never its value."""
    from google.cloud import secretmanager
    pb = secretmanager.Secret.pb(secret)
    rep = pb.replication
    automatic = rep.HasField("automatic")
    replicas = list(rep.user_managed.replicas)
    cmek = any(r.HasField("customer_managed_encryption") for r in replicas) \
        or (automatic and rep.automatic.HasField("customer_managed_encryption")) \
        or ("customer_managed_encryption" in pb.DESCRIPTOR.fields_by_name and pb.HasField("customer_managed_encryption"))
    return {"locations": sorted(r.location for r in replicas), "automatic": automatic, "cmek": bool(cmek),
            "expire": pb.HasField("expire_time") or pb.HasField("ttl"), "topics": len(pb.topics),
            "rotation": pb.HasField("rotation"),
            "destroy_ttl_s": pb.version_destroy_ttl.seconds if pb.HasField("version_destroy_ttl") else 0,
            "labels": dict(pb.labels)}


def describe_body(body: dict) -> dict:
    """The same description for the body we create: built through the real Secret, so the body is a valid one."""
    from google.cloud import secretmanager
    return describe_secret(secretmanager.Secret(**body))


def matches(found: dict, env: str, apartment_id: str, op: str) -> bool:
    return found == describe_body(secret_body(env, apartment_id, op))


async def _ensure_one(sm, name: str, env: str, apartment_id: str, op: str, nbytes: int) -> None:
    try:
        await asyncio.to_thread(sm.create, name, secret_body(env, apartment_id, op))
    except SecretExists:
        if not matches(await asyncio.to_thread(sm.describe, name), env, apartment_id, op):
            raise SecretConflict(name) from None
    if not await asyncio.to_thread(sm.enabled_versions, name):
        value = secrets.token_urlsafe(nbytes)
        try:
            await asyncio.to_thread(sm.add_version, name, value.encode("ascii"))
        finally:
            value = ""


async def ensure_pair(sm, env: str, apartment_id: str, op: str) -> None:
    """Both secrets exist, ours, each with one enabled version. Raises SecretConflict or SecretError."""
    key, connector = names(apartment_id)
    await _ensure_one(sm, key, env, apartment_id, op, 32)
    await _ensure_one(sm, connector, env, apartment_id, op, 24)


async def destroy_pair(sm, apartment_id: str) -> None:
    """«Annulla», after togli_motore succeeded: every live version of the two secrets destroyed with the delay (they
    can be re-enabled for 7 days). A missing secret or an already destroyed version is nothing to do."""
    for name in names(apartment_id):
        for version in await asyncio.to_thread(sm.live_versions, name):
            await asyncio.to_thread(sm.destroy, version)


class GcpSecrets:
    """The real Secret Manager, with the server's identity (roles «creazione» and «versioni» of project §4.1)."""

    def __init__(self, project: str):
        from google.cloud import secretmanager
        self.project = project
        self.client = secretmanager.SecretManagerServiceClient()

    def _path(self, secret_id: str) -> str:
        return f"projects/{self.project}/secrets/{secret_id}"

    def _call(self, fn, **request):
        from google.api_core import exceptions
        try:
            return fn(request=request, retry=None, timeout=CALL_TIMEOUT_S)
        except exceptions.AlreadyExists:
            raise SecretExists(request.get("secret_id", "")) from None
        except exceptions.GoogleAPICallError as exc:
            raise SecretError(type(exc).__name__) from None

    def create(self, secret_id: str, body: dict) -> None:
        self._call(self.client.create_secret, parent=f"projects/{self.project}", secret_id=secret_id, secret=body)

    def describe(self, secret_id: str) -> dict:
        return describe_secret(self._call(self.client.get_secret, name=self._path(secret_id)))

    def enabled_versions(self, secret_id: str) -> list[str]:
        return [v.name for v in self._call(self.client.list_secret_versions, parent=self._path(secret_id),
                                           filter="state:ENABLED")]

    def add_version(self, secret_id: str, data: bytes) -> None:
        self._call(self.client.add_secret_version, parent=self._path(secret_id), payload={"data": data})

    def live_versions(self, secret_id: str) -> list[str]:
        """Enabled versions, and disabled ones not yet scheduled for destruction; none for a missing secret."""
        from google.api_core import exceptions
        from google.cloud import secretmanager
        try:
            versions = self.client.list_secret_versions(request={"parent": self._path(secret_id)}, retry=None,
                                                        timeout=CALL_TIMEOUT_S)
            out = []
            for v in versions:
                pb = secretmanager.SecretVersion.pb(v)
                state = secretmanager.SecretVersion.State
                if v.state == state.ENABLED or (v.state == state.DISABLED and not pb.HasField("scheduled_destroy_time")):
                    out.append(v.name)
            return out
        except exceptions.NotFound:
            return []
        except exceptions.GoogleAPICallError as exc:
            raise SecretError(type(exc).__name__) from None

    def destroy(self, version_name: str) -> None:
        from google.api_core import exceptions
        try:
            self.client.destroy_secret_version(request={"name": version_name}, retry=None, timeout=CALL_TIMEOUT_S)
        except (exceptions.FailedPrecondition, exceptions.NotFound):
            return                                  # already destroyed or scheduled: nothing to do
        except exceptions.GoogleAPICallError as exc:
            raise SecretError(type(exc).__name__) from None


_admin = None


def get_secret_admin():
    """The Secret Manager the creation uses; the tests put a fake one with set_secret_admin()."""
    global _admin
    if _admin is None:
        from .config import get_settings
        _admin = GcpSecrets(get_settings().gcp_project_id)
    return _admin


def set_secret_admin(admin) -> None:
    global _admin
    _admin = admin
