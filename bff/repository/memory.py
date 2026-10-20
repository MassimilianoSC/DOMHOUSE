from .base import (WEBHOOK_LOG_LIMIT, ActorRecord, Apartment, AuditEntry, AuditPerson, BookingRecord, PlatformMember, SupportAccess,
                   Tenant, User, WebhookLog, normalize_email)


class InMemoryRepository:
    def __init__(self) -> None:
        self.tenants: dict[str, Tenant] = {}
        self.users: dict[str, User] = {}
        self.apartments: dict[str, Apartment] = {}
        self.bookings: dict[str, BookingRecord] = {}
        self.webhook_logs: list[WebhookLog] = []
        self.platform_members: dict[str, PlatformMember] = {}
        self.tenant_names: dict[str, str] = {}
        self.used_apartment_ids: set[str] = set()
        self.external_id_owners: dict[str, str] = {}
        self.audit: dict[str | None, dict[str, AuditEntry]] = {}   # tenant_id (None = platform) -> audit_id -> entry
        self.audit_people: dict[str, AuditPerson] = {}
        self.mail_counts: dict[str, int] = {}
        self.support_access: dict[str, SupportAccess] = {}
        self.actor_refs: dict[str, str] = {}             # uid -> pseudonym
        self.actors: dict[str, ActorRecord] = {}         # pseudonym -> who

    async def get_tenant(self, tenant_id):
        t = self.tenants.get(tenant_id)
        return t.model_copy(deep=True) if t else None

    async def list_tenants(self):
        return [t.model_copy(deep=True) for t in self.tenants.values()]

    async def upsert_tenant(self, tenant):
        self.tenants[tenant.tenant_id] = tenant.model_copy(deep=True)
        return tenant

    async def update_tenant(self, tenant_id, fields):
        t = self.tenants.get(tenant_id)
        if t is None:
            return None
        self.tenants[tenant_id] = t.model_copy(update=fields, deep=True)
        return self.tenants[tenant_id].model_copy(deep=True)

    async def get_user(self, uid):
        u = self.users.get(uid)
        return u.model_copy(deep=True) if u else None

    async def get_user_by_email(self, email):
        email = email.lower()
        for u in self.users.values():
            if u.email.lower() == email:
                return u.model_copy(deep=True)
        return None

    async def users_with_push_token(self, token):
        return [u.model_copy(deep=True) for u in self.users.values() if token in u.push_tokens]

    async def list_users(self, tenant_id):
        return sorted(
            (u.model_copy(deep=True) for u in self.users.values() if u.tenant_id == tenant_id),
            key=lambda u: u.email,
        )

    async def upsert_user(self, user):
        self.users[user.uid] = user.model_copy(deep=True)
        return user

    async def delete_user(self, uid):
        return self.users.pop(uid, None) is not None

    async def get_apartment(self, apartment_id):
        a = self.apartments.get(apartment_id)
        return a.model_copy(deep=True) if a else None

    async def list_apartments(self, tenant_id=None):
        items = [a for a in self.apartments.values() if tenant_id is None or a.tenant_id == tenant_id]
        return sorted((a.model_copy(deep=True) for a in items), key=lambda a: a.name)

    async def find_apartments_by_external_id(self, source, external_id):
        found = [a for a in self.apartments.values() if getattr(a.external_ids, source, None) == external_id]
        return [a.model_copy(deep=True) for a in sorted(found, key=lambda a: a.apartment_id)]

    async def upsert_apartment(self, apartment):
        self.apartments[apartment.apartment_id] = apartment.model_copy(deep=True)
        return apartment

    async def delete_apartment(self, apartment_id):
        return self.apartments.pop(apartment_id, None) is not None

    async def get_booking(self, apartment_id, booking_id):
        b = self.bookings.get(f"{apartment_id}__{booking_id}")
        return b.model_copy(deep=True) if b else None

    async def list_bookings(self, apartment_id):
        items = [b for b in self.bookings.values() if b.apartment_id == apartment_id]
        return sorted((b.model_copy(deep=True) for b in items), key=lambda b: b.checkin_at)

    async def delete_bookings(self, apartment_id):
        gone = [k for k, b in self.bookings.items() if b.apartment_id == apartment_id]
        for k in gone:
            del self.bookings[k]
        return len(gone)

    async def upsert_booking(self, booking):
        self.bookings[booking.key] = booking.model_copy(deep=True)
        return booking

    async def add_webhook_log(self, log):
        self.webhook_logs.append(log.model_copy(deep=True))
        same = [i for i, l in enumerate(self.webhook_logs) if l.tenant_id == log.tenant_id]
        for i in reversed(same[:-WEBHOOK_LOG_LIMIT]):
            del self.webhook_logs[i]
        return log

    async def list_webhook_logs(self, tenant_id, limit=WEBHOOK_LOG_LIMIT):
        items = [log for log in reversed(self.webhook_logs) if log.tenant_id == tenant_id]
        return [log.model_copy(deep=True) for log in items[:limit]]

    # administrative log (P-47)
    async def add_audit(self, entry):
        self.audit.setdefault(entry.tenant_id, {})[entry.audit_id] = entry.model_copy(deep=True)
        return entry

    async def list_audit(self, tenant_id, limit, before=None):
        entries = self.audit.get(tenant_id, {})
        ids = sorted((i for i in entries if before is None or i < before), reverse=True)
        return [entries[i].model_copy(deep=True) for i in ids[:limit]]

    async def put_audit_person(self, person):
        self.audit_people[person.ref] = person.model_copy(deep=True)
        return person

    async def get_audit_people(self, refs):
        return {r: self.audit_people[r].model_copy(deep=True) for r in set(refs) if r in self.audit_people}

    async def delete_audit_person(self, ref):
        return self.audit_people.pop(ref, None) is not None

    # invitation email limits (P-49)
    async def take_mail_quota(self, buckets):
        if any(self.mail_counts.get(key, 0) >= limit for key, limit in buckets):
            return False
        for key, _ in buckets:
            self.mail_counts[key] = self.mail_counts.get(key, 0) + 1
        return True

    # pseudonyms towards the engine (P-48)
    async def claim_actor_ref(self, uid, candidate):
        return self.actor_refs.setdefault(uid, candidate)

    async def put_actor(self, record):
        self.actors[record.ref] = record.model_copy(deep=True)
        return record

    async def get_actors(self, refs):
        return {r: self.actors[r].model_copy(deep=True) for r in set(refs) if r in self.actors}

    async def forget_actor(self, uid):
        ref = self.actor_refs.pop(uid, None)
        if ref is None:
            return False
        self.actors.pop(ref, None)
        return True

    # support access (P-50)
    async def add_support_access(self, access):
        self.support_access[access.access_id] = access.model_copy(deep=True)
        return access

    async def get_support_access(self, access_id):
        a = self.support_access.get(access_id)
        return a.model_copy(deep=True) if a else None

    async def list_support_access(self, tenant_id=None, operator_uid=None):
        items = [a for a in self.support_access.values() if (tenant_id is None or a.tenant_id == tenant_id)
                 and (operator_uid is None or a.operator_uid == operator_uid)]
        return [a.model_copy(deep=True) for a in sorted(items, key=lambda a: a.opened_at, reverse=True)]

    async def update_support_access(self, access_id, fields):
        a = self.support_access.get(access_id)
        if a is None:
            return None
        self.support_access[access_id] = a.model_copy(update=fields, deep=True)
        return self.support_access[access_id].model_copy(deep=True)

    async def close_support_access(self, access_id, closed_at, by):
        a = self.support_access.get(access_id)
        if a is None or a.closed_at is not None:
            return False
        self.support_access[access_id] = a.model_copy(update={"closed_at": closed_at, "closed_by": by})
        return True

    # platform managers (P-36)
    async def get_platform_member(self, email):
        m = self.platform_members.get(normalize_email(email))
        return m.model_copy(deep=True) if m else None

    async def list_platform_members(self):
        return [m.model_copy(deep=True) for _, m in sorted(self.platform_members.items())]

    async def add_platform_member(self, member):
        member.email = normalize_email(member.email)
        self.platform_members[member.email] = member.model_copy(deep=True)
        return member

    async def remove_platform_member(self, email):
        return self.platform_members.pop(normalize_email(email), None) is not None

    # atomic claims (P-36)
    async def create_user_if_absent(self, user):
        if user.uid in self.users:
            return False
        self.users[user.uid] = user.model_copy(deep=True)
        return True

    async def claim_tenant_name(self, name_key, tenant_id):
        owner = self.tenant_names.setdefault(name_key, tenant_id)
        return None if owner == tenant_id else owner

    async def release_tenant_name(self, name_key, tenant_id):
        if self.tenant_names.get(name_key) == tenant_id:
            del self.tenant_names[name_key]

    async def reserve_apartment_id(self, apartment_id):
        if apartment_id in self.used_apartment_ids:
            return False
        self.used_apartment_ids.add(apartment_id)
        return True

    # P-36 point 14: no await between the check and the write, so atomic within the (single) process
    def _other_admins(self, tenant_id, uid):
        return [u for u in self.users.values() if u.tenant_id == tenant_id and u.role == "admin" and u.uid != uid]

    async def upsert_user_keeping_an_admin(self, user):
        current = self.users.get(user.uid)
        if current and current.role == "admin" and user.role != "admin" and not self._other_admins(user.tenant_id, user.uid):
            return False
        self.users[user.uid] = user.model_copy(deep=True)
        return True

    async def delete_user_keeping_an_admin(self, uid):
        current = self.users.get(uid)
        if current is None:
            return "not_found"
        if current.role == "admin" and not self._other_admins(current.tenant_id, uid):
            return "last_admin"
        del self.users[uid]
        return "deleted"

    async def remove_platform_member_keeping_one(self, email):
        email = normalize_email(email)
        if email not in self.platform_members:
            return "not_found"
        if len(self.platform_members) <= 1:
            return "last"
        del self.platform_members[email]
        return "removed"

    async def claim_external_id(self, source, code, apartment_id):
        owner = self.external_id_owners.setdefault(f"{source}:{code}", apartment_id)
        return None if owner == apartment_id else owner

    async def release_external_id(self, source, code, apartment_id):
        if self.external_id_owners.get(f"{source}:{code}") == apartment_id:
            del self.external_id_owners[f"{source}:{code}"]
