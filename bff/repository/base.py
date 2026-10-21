from datetime import UTC, datetime
from typing import Literal, Protocol

from pydantic import BaseModel, Field, model_validator

Role = Literal["admin", "operator", "viewer"]


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Tenant(BaseModel):
    tenant_id: str
    name: str
    created_at: str = Field(default_factory=now_iso)
    enabled_features: list[str] | None = None
    created_by: str = ""                    # platform manager who created it (P-36); "" for older records
    first_admin_email: str | None = None    # the admin invited by the platform at creation (P-36)
    # P-50 (D-85): a suspended organisation keeps its data and its bookings, but its people cannot use the app
    status: Literal["active", "suspended"] = "active"
    suspended_at: str | None = None
    suspended_reason: str | None = None
    energy_price_eur_kwh: float | None = None   # P-52 (D-92): set by the admin; None = not set


def tenant_name_key(name: str) -> str:
    """Organisation names are unique ignoring case and repeated spaces (D-61a g)."""
    return " ".join(name.split()).casefold()


class NotificationPrefs(BaseModel):
    approvals: bool = True
    offline: bool = True
    decisions: bool = False
    # D-123 «Prenotazioni»: bookings that change the apartment's schedule (today: cancelled after the prearrival). On by
    # default, also for preferences saved before it existed: a stored record without the key reads True.
    bookings: bool = True


class User(BaseModel):
    uid: str
    email: str
    display_name: str = ""
    tenant_id: str
    role: Role
    notification_prefs: NotificationPrefs = Field(default_factory=NotificationPrefs)
    push_tokens: list[str] = Field(default_factory=list)
    # Apartments an operator or viewer may see (P-18, D-41). None (or missing in older records) = every apartment of
    # the tenant; [] = none. Ignored for admins. Never turned from a list into None by anything but an explicit choice.
    apartment_ids: list[str] | None = None
    # D-91 (F3): the invitation's email and any earlier one, so that erasing the person reaches their traces too
    former_emails: list[str] = Field(default_factory=list)


class ExternalIds(BaseModel):
    italianway: str | None = None


class LastCheck(BaseModel):
    """Outcome of the last 'Verifica connessione' (D-64), shown to the platform and to the admin."""
    ok: bool
    checked_at: str
    error: str | None = None
    secret_problem: bool = False   # D-90: the error names a secret; the admin reads a generic message instead


class Apartment(BaseModel):
    apartment_id: str
    tenant_id: str
    name: str
    address: str = ""
    timezone: str = "Europe/Rome"
    instance_url: str
    instance_secret_name: str | None = None
    port: int | None = None
    enabled: bool = True
    external_ids: ExternalIds = Field(default_factory=ExternalIds)
    enabled_features: list[str] | None = None
    created_at: str = Field(default_factory=now_iso)
    last_check: LastCheck | None = None
    energy_price_eur_kwh: float | None = None   # P-52: the apartment's own price; None = the organisation's
    # D-130: start (ISO, UTC) of the first hour with measured consumption, found by bff/energy_since.py; None = none yet
    energy_since: str | None = None
    # D-97: a demonstration apartment, where admins may use the simulator. Set by the platform; always true on the
    # built-in mock (also for records saved before the field existed); a real engine in simulated mode can be marked too
    simulated: bool = False

    @model_validator(mode="after")
    def _mock_is_simulated(self):
        if self.instance_url.strip().lower().startswith("mock://"):
            self.simulated = True
        return self


BookingStatus = Literal["booked", "checked_in", "checked_out", "cancelled"]


class BookingRecord(BaseModel):
    """Latest known state of a booking the BFF forwarded to the instance (the contract exposes only current_booking_id)."""

    apartment_id: str
    booking_id: str
    checkin_at: str
    checkout_at: str
    guests: int | None = None
    source: str
    status: BookingStatus = "booked"
    event_ids: list[str] = Field(default_factory=list)
    last_event_type: str = ""
    updated_at: str = Field(default_factory=now_iso)

    @property
    def key(self) -> str:
        return f"{self.apartment_id}__{self.booking_id}"


class PlatformMember(BaseModel):
    """P-36 (D-62): a platform manager, by normalised email. The role is matched against the token's VERIFIED email and
    gives access only to /app/platform/*, never to an organisation's data."""
    email: str
    added_by: str = ""
    added_at: str = Field(default_factory=now_iso)
    first_seen_at: str | None = None        # first sign-in with the role ("active" in the platform list)
    display_name: str = ""


def normalize_email(email: str) -> str:
    return email.strip().lower()


class WebhookLog(BaseModel):
    """One received webhook call; the last 100 are kept (raw body is admin-only)."""

    log_id: str
    source: str = "italianway"
    received_at: str = Field(default_factory=now_iso)
    tenant_id: str | None = None
    apartment_id: str | None = None
    signature_ok: bool
    status_code: int
    outcome: str
    event_id: str | None = None
    booking_id: str | None = None
    correlation_id: str
    forward_status: int | None = None
    forward_attempts: int = 0
    # D-90: only what is useful is kept: the structured fields below, and the body with the guests' data obscured
    event_type: str | None = None
    external_id: str | None = None
    checkin_at: str | None = None
    checkout_at: str | None = None
    guests: int | None = None
    raw_body: str = ""


WEBHOOK_LOG_LIMIT = 100

# P-47: closed set; the PWA has a sentence for each one (a new action is agreed with o2 first)
AuditAction = Literal[
    "invite_sent", "invite_resent", "invite_email_deferred", "role_changed", "scope_changed", "user_removed",
    "apartment_created", "apartment_updated", "apartment_relinked", "apartment_deleted", "features_changed",
    "italianway_changed", "tenant_created", "tenant_renamed", "tenant_suspended", "tenant_reactivated",
    "support_access_requested", "support_access_approved", "support_access_rejected", "support_access_opened",
    "support_access_closed", "support_access_expired", "manager_added", "manager_removed", "account_deleted",
    "energy_price_changed", "apartment_simulated_changed", "simulator_reset",
]


class AuditActor(BaseModel):
    kind: Literal["user", "platform", "support", "system"]
    ref: str | None = None                  # key of the person in audit_people (the uid); None for "system"
    support_access_id: str | None = None
    role: Role | None = None                # D-90: what the platform sees of an organisation's people


class AuditTarget(BaseModel):
    type: Literal["user", "apartment", "tenant", "support_access", "manager"]
    id: str
    label: str | None = None                # names of apartments and organisations only, never a person's data
    ref: str | None = None                  # person targets (user, manager): key in audit_people
    role: Role | None = None                # user targets: their role at that moment (D-90)


class AuditEntry(BaseModel):
    """P-47: one administrative action. No email or name of a person is stored here, only keys into audit_people, so
    erasing a person (P-48) never rewrites the log: their entries read "utente rimosso"."""

    audit_id: str                           # time-sortable "<at>-<random>": order and pagination cursor
    at: str
    tenant_id: str | None                   # None = platform-level action (managers)
    action: AuditAction
    actor: AuditActor
    target: AuditTarget
    details: dict = Field(default_factory=dict)


class AuditPerson(BaseModel):
    """The only place where the log keeps who a person is; removed with the person's own account (P-48)."""

    ref: str
    email: str
    display_name: str = ""


AUDIT_PAGE_MAX = 100


class ActorRecord(BaseModel):
    """P-48 (D-87): who is behind a pseudonym sent to the engine as X-Actor (see bff/actors.py)."""

    ref: str
    uid: str
    email: str


class SupportAccess(BaseModel):
    """P-50 (D-86): a platform manager inside an organisation for 1-24 h, with the rights of an operator. Its status is
    computed from closed_at and expires_at (see bff/support.py): nothing has to run when it expires."""

    access_id: str
    tenant_id: str
    operator_uid: str
    operator_email: str                     # the real identity, shown to the organisation (P-50)
    operator_name: str = ""
    reason: str
    role: Literal["operator"] = "operator"   # D-86: never more than an operator (D-88: fixed, not read from the record)
    opened_at: str
    expires_at: str
    closed_at: str | None = None
    closed_by: Literal["platform", "admin"] | None = None
    expiry_logged: bool = False             # support_access_expired written once


class Repository(Protocol):
    async def get_tenant(self, tenant_id: str) -> Tenant | None: ...
    async def list_tenants(self) -> list[Tenant]: ...
    async def upsert_tenant(self, tenant: Tenant) -> Tenant: ...
    # only the given fields: a rename or a features change can never undo a suspension written in between (P-50)
    async def update_tenant(self, tenant_id: str, fields: dict) -> Tenant | None: ...

    async def get_user(self, uid: str) -> User | None: ...
    async def get_user_by_email(self, email: str) -> User | None: ...
    async def users_with_push_token(self, token: str) -> list[User]: ...   # any tenant (P-36, point 11)
    async def list_users(self, tenant_id: str) -> list[User]: ...
    async def upsert_user(self, user: User) -> User: ...
    async def delete_user(self, uid: str) -> bool: ...

    async def get_apartment(self, apartment_id: str) -> Apartment | None: ...
    async def list_apartments(self, tenant_id: str | None = None) -> list[Apartment]: ...
    # every match, not the first: a code must be unique across tenants (P-36 S2), callers refuse ambiguity
    async def find_apartments_by_external_id(self, source: str, external_id: str) -> list[Apartment]: ...
    async def upsert_apartment(self, apartment: Apartment) -> Apartment: ...
    async def delete_apartment(self, apartment_id: str) -> bool: ...

    async def get_booking(self, apartment_id: str, booking_id: str) -> BookingRecord | None: ...
    async def list_bookings(self, apartment_id: str) -> list[BookingRecord]: ...
    async def upsert_booking(self, booking: BookingRecord) -> BookingRecord: ...
    async def delete_bookings(self, apartment_id: str) -> int: ...   # D-97: reset of a demonstration apartment

    async def add_webhook_log(self, log: WebhookLog) -> WebhookLog: ...
    # per tenant, strictly: tenant_id=None are the unattributed calls, seen only by the platform (P-36 S1); the last
    # WEBHOOK_LOG_LIMIT are kept per tenant, so a busy organisation never pushes out another one's logs
    async def list_webhook_logs(self, tenant_id: str | None, limit: int = WEBHOOK_LOG_LIMIT) -> list[WebhookLog]: ...

    # atomic claims (P-36): False / the existing owner when someone got there first, so a double click or two
    # concurrent requests never create two invitations, two organisations with one name, or reuse an apartment id
    async def create_user_if_absent(self, user: User) -> bool: ...
    async def claim_tenant_name(self, name_key: str, tenant_id: str) -> str | None: ...   # None = claimed
    async def release_tenant_name(self, name_key: str, tenant_id: str) -> None: ...
    async def reserve_apartment_id(self, apartment_id: str) -> bool: ...   # never released (D-67)
    async def claim_external_id(self, source: str, code: str, apartment_id: str) -> str | None: ...   # None = claimed
    async def release_external_id(self, source: str, code: str, apartment_id: str) -> None: ...
    # P-36 point 14: "at least one admin" / "at least one platform manager", checked and written in ONE transaction,
    # so two people demoting or removing each other at the same moment cannot leave nobody in charge
    async def upsert_user_keeping_an_admin(self, user: User) -> bool: ...                 # False = would leave no admin
    async def delete_user_keeping_an_admin(self, uid: str) -> str: ...                   # deleted | not_found | last_admin
    async def remove_platform_member_keeping_one(self, email: str) -> str: ...           # removed | not_found | last

    # P-47: newest first; `before` is the audit_id of the last entry already shown (exclusive)
    async def add_audit(self, entry: AuditEntry) -> AuditEntry: ...
    async def list_audit(self, tenant_id: str | None, limit: int, before: str | None = None) -> list[AuditEntry]: ...
    async def put_audit_person(self, person: AuditPerson) -> AuditPerson: ...
    async def get_audit_people(self, refs: list[str]) -> dict[str, AuditPerson]: ...
    async def delete_audit_person(self, ref: str) -> bool: ...

    # P-49: anti-abuse counters for invitation emails. Atomic: when every bucket is below its limit each one goes up by
    # one and the answer is True; otherwise nothing changes and the answer is False
    async def take_mail_quota(self, buckets: list[tuple[str, int]]) -> bool: ...

    # pseudonyms towards the engine (P-48): claim is atomic (the existing one wins), forget removes both directions
    async def claim_actor_ref(self, uid: str, candidate: str) -> str: ...
    async def put_actor(self, record: ActorRecord) -> ActorRecord: ...
    async def get_actors(self, refs: list[str]) -> dict[str, ActorRecord]: ...
    async def forget_actor(self, uid: str) -> bool: ...

    # support access (P-50): newest first; by organisation, or by the manager who opened them
    async def add_support_access(self, access: SupportAccess) -> SupportAccess: ...
    async def get_support_access(self, access_id: str) -> SupportAccess | None: ...
    async def list_support_access(self, tenant_id: str | None = None, operator_uid: str | None = None) -> list[SupportAccess]: ...
    async def update_support_access(self, access_id: str, fields: dict) -> SupportAccess | None: ...
    # D-88: closes only an access still open (closed_at null), atomically; True for the one call that closed it
    async def close_support_access(self, access_id: str, closed_at: str, by: str) -> bool: ...

    async def get_platform_member(self, email: str) -> PlatformMember | None: ...
    async def list_platform_members(self) -> list[PlatformMember]: ...
    async def add_platform_member(self, member: PlatformMember) -> PlatformMember: ...
    async def remove_platform_member(self, email: str) -> bool: ...


def apply_booking_event(existing: BookingRecord | None, apartment_id: str, ev: dict) -> BookingRecord:
    """Folds a forwarded BookingEvent into the archived record (idempotent on event_id)."""
    rec = existing or BookingRecord(apartment_id=apartment_id, booking_id=ev["booking_id"], checkin_at=ev["checkin_at"],
                                    checkout_at=ev["checkout_at"], guests=ev.get("guests"), source=ev["source"])
    if ev["event_id"] in rec.event_ids:
        return rec
    rec.event_ids = rec.event_ids + [ev["event_id"]]
    rec.last_event_type = ev["type"]
    rec.guests = ev.get("guests", rec.guests)
    rec.source = ev["source"]
    if ev["type"] == "booking_cancelled":
        rec.status = "cancelled"
    elif ev["type"] == "checkin":
        rec.status = "checked_in"
    elif ev["type"] == "checkout":
        rec.status = "checked_out"
    else:
        rec.checkin_at, rec.checkout_at = ev["checkin_at"], ev["checkout_at"]
        if rec.status == "cancelled":
            rec.status = "booked"
    rec.updated_at = now_iso()
    return rec
