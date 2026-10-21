"""Firestore implementation of the Repository protocol (REPOSITORY=firestore).

Collections: tenants/{tenant_id}, users/{uid}, apartments/{apartment_id}, bookings/{apartment_id}__{booking_id},
webhook_logs, platform_members/{email}, tenant_names/{sha256 of the name key}, apartment_ids_used/{apartment_id}.
Uses the async client; credentials come from ADC (Cloud Run service account) or FIRESTORE_EMULATOR_HOST in tests.
"""
import asyncio
import hashlib

from google.api_core.exceptions import AlreadyExists, NotFound
from google.cloud import firestore

from .. import retention

from .base import (EMPTY_AI_USAGE, WEBHOOK_LOG_LIMIT, ActorRecord, Apartment, AuditEntry, AuditPerson, BookingRecord, PlatformMember, SupportAccess,
                   Tenant, User, WebhookLog, normalize_email, now_iso)


class FirestoreRepository:
    def __init__(self, project_id: str | None = None, client: "firestore.AsyncClient | None" = None, prefix: str = ""):
        self.db = client or firestore.AsyncClient(project=project_id or None)
        self.prefix = prefix
        self._locks: dict[tuple[int, str], asyncio.Lock] = {}

    def _lock(self, key: str) -> asyncio.Lock:
        """In-process serialisation of the "keep one in charge" transactions: with maxScale 1 (D-35) every request goes
        through one process, so two crossed transactions never wait on each other's read locks (the emulator, unlike
        Firestore, has no deadlock resolution). Across instances the transactions alone keep the rule."""
        k = (id(asyncio.get_running_loop()), key)
        if k not in self._locks:
            self._locks[k] = asyncio.Lock()
        return self._locks[k]

    def _col(self, name: str):
        return self.db.collection(f"{self.prefix}{name}")

    async def _get(self, col: str, key: str, model):
        snap = await self._col(col).document(key).get()
        return model(**snap.to_dict()) if snap.exists else None

    async def _put(self, col: str, key: str, obj, expire_at=None):
        data = obj.model_dump()
        if expire_at is not None:   # P-54: a Firestore-only TIMESTAMP read by the collection's TTL policy
            data[retention.FIELD] = expire_at
        await self._col(col).document(key).set(data)
        return obj

    async def _delete(self, col: str, key: str) -> bool:
        ref = self._col(col).document(key)
        if not (await ref.get()).exists:
            return False
        await ref.delete()
        return True

    async def _query(self, col: str, model, field: str | None = None, value=None):
        q = self._col(col)
        if field is not None:
            q = q.where(filter=firestore.FieldFilter(field, "==", value))
        return [model(**d.to_dict()) async for d in q.stream()]

    # tenants
    async def get_tenant(self, tenant_id):
        return await self._get("tenants", tenant_id, Tenant)

    async def list_tenants(self):
        return sorted(await self._query("tenants", Tenant), key=lambda t: t.tenant_id)

    async def upsert_tenant(self, tenant):
        return await self._put("tenants", tenant.tenant_id, tenant)

    async def update_tenant(self, tenant_id, fields):
        try:
            await self._col("tenants").document(tenant_id).update(fields)
        except NotFound:
            return None
        return await self.get_tenant(tenant_id)

    # users
    async def get_user(self, uid):
        return await self._get("users", uid, User)

    async def get_user_by_email(self, email):
        found = await self._query("users", User, "email", email.lower())
        return found[0] if found else None

    async def users_with_push_token(self, token):
        q = self._col("users").where(filter=firestore.FieldFilter("push_tokens", "array_contains", token))
        return [User(**d.to_dict()) async for d in q.stream()]

    async def list_users(self, tenant_id):
        return sorted(await self._query("users", User, "tenant_id", tenant_id), key=lambda u: u.email)

    async def upsert_user(self, user):
        user.email = user.email.lower()
        return await self._put("users", user.uid, user)

    async def delete_user(self, uid):
        return await self._delete("users", uid)

    # apartments
    async def get_apartment(self, apartment_id):
        return await self._get("apartments", apartment_id, Apartment)

    async def list_apartments(self, tenant_id=None):
        items = await self._query("apartments", Apartment, "tenant_id" if tenant_id else None, tenant_id)
        return sorted(items, key=lambda a: a.name)

    async def find_apartments_by_external_id(self, source, external_id):
        found = await self._query("apartments", Apartment, f"external_ids.{source}", external_id)
        return sorted(found, key=lambda a: a.apartment_id)

    async def upsert_apartment(self, apartment):
        return await self._put("apartments", apartment.apartment_id, apartment)

    async def delete_apartment(self, apartment_id):
        return await self._delete("apartments", apartment_id)

    # bookings
    async def get_booking(self, apartment_id, booking_id):
        return await self._get("bookings", f"{apartment_id}__{booking_id}", BookingRecord)

    async def list_bookings(self, apartment_id):
        return sorted(await self._query("bookings", BookingRecord, "apartment_id", apartment_id), key=lambda b: b.checkin_at)

    async def delete_bookings(self, apartment_id):
        q = self._col("bookings").where(filter=firestore.FieldFilter("apartment_id", "==", apartment_id))
        n = 0
        async for d in q.stream():
            await d.reference.delete()
            n += 1
        return n

    async def upsert_booking(self, booking):
        return await self._put("bookings", booking.key, booking, retention.booking(booking.model_dump()))

    # webhook logs (last WEBHOOK_LOG_LIMIT overall; older documents are deleted on insert)
    async def _tenant_logs(self, tenant_id):
        # equality filter only (automatic single-field index, no composite index to deploy); at most
        # WEBHOOK_LOG_LIMIT+1 documents per tenant, sorted here
        q = self._col("webhook_logs").where(filter=firestore.FieldFilter("tenant_id", "==", tenant_id))
        docs = [d async for d in q.stream()]
        return sorted(docs, key=lambda d: d.get("received_at"), reverse=True)

    async def add_webhook_log(self, log):
        await self._put("webhook_logs", log.log_id, log, retention.webhook(log.model_dump()))
        for stale in (await self._tenant_logs(log.tenant_id))[WEBHOOK_LOG_LIMIT:]:
            await stale.reference.delete()
        return log

    async def list_webhook_logs(self, tenant_id, limit=WEBHOOK_LOG_LIMIT):
        return [WebhookLog(**d.to_dict()) for d in (await self._tenant_logs(tenant_id))[:limit]]

    # administrative log (P-47): tenants/{tid}/audit/{audit_id} and platform_audit/{audit_id}, ordered by audit_id only
    # (time-sortable): the automatic single-field index is enough, no composite index to deploy
    def _audit_col(self, tenant_id):
        if tenant_id is None:
            return self._col("platform_audit")
        return self._col("tenants").document(tenant_id).collection("audit")

    async def add_audit(self, entry):
        data = {**entry.model_dump(), retention.FIELD: retention.audit(entry.model_dump())}
        await self._audit_col(entry.tenant_id).document(entry.audit_id).set(data)
        return entry

    async def list_audit(self, tenant_id, limit, before=None):
        q = self._audit_col(tenant_id)
        if before is not None:
            q = q.where(filter=firestore.FieldFilter("audit_id", "<", before))
        q = q.order_by("audit_id", direction=firestore.Query.DESCENDING).limit(limit)
        return [AuditEntry(**d.to_dict()) async for d in q.stream()]

    async def put_audit_person(self, person):
        # every entry rewrites the person: they live 24 months past the last entry that cites them (P-54)
        return await self._put("audit_people", person.ref, person, retention.person())

    async def get_audit_people(self, refs):
        refs = sorted(set(refs))
        if not refs:
            return {}
        snaps = self.db.get_all([self._col("audit_people").document(r) for r in refs])
        return {snap.id: AuditPerson(**snap.to_dict()) async for snap in snaps if snap.exists}

    async def delete_audit_person(self, ref):
        return await self._delete("audit_people", ref)

    # invitation email limits (P-49): mail_limits/{bucket} = {count}; one transaction reads every bucket, then raises
    # all of them or none
    async def take_mail_quota(self, buckets):
        refs = [(self._col("mail_limits").document(key), limit) for key, limit in buckets]

        @firestore.async_transactional
        async def txn(tx):
            counts = []
            for ref, limit in refs:
                snap = await ref.get(transaction=tx)
                count = (snap.to_dict() or {}).get("count", 0) if snap.exists else 0
                if count >= limit:
                    return False
                counts.append(count)
            for (ref, _), count in zip(refs, counts):
                at = now_iso()
                tx.set(ref, {"count": count + 1, "updated_at": at, retention.FIELD: retention.mail({"updated_at": at})})
            return True
        async with self._lock("mail_limits"):
            return await txn(self.db.transaction())

    # the assistant's spending (P-60 step 9): ai_usage/{YYYY-MM}, raised in a transaction
    async def get_ai_usage(self, month):
        snap = await self._col("ai_usage").document(month).get()
        return {**EMPTY_AI_USAGE, **(snap.to_dict() or {})} if snap.exists else dict(EMPTY_AI_USAGE)

    async def add_ai_usage(self, month, cost_eur, input_tokens, output_tokens):
        ref = self._col("ai_usage").document(month)

        @firestore.async_transactional
        async def txn(tx):
            snap = await ref.get(transaction=tx)
            u = {**EMPTY_AI_USAGE, **(snap.to_dict() or {})} if snap.exists else dict(EMPTY_AI_USAGE)
            u.update(cost_eur=u["cost_eur"] + cost_eur, calls=u["calls"] + 1, input_tokens=u["input_tokens"] + input_tokens,
                     output_tokens=u["output_tokens"] + output_tokens, updated_at=now_iso())
            tx.set(ref, u)
            return {k: u[k] for k in EMPTY_AI_USAGE}
        async with self._lock("ai_usage"):
            return await txn(self.db.transaction())

    async def mark_ai_alert(self, month):
        ref = self._col("ai_usage").document(month)

        @firestore.async_transactional
        async def txn(tx):
            snap = await ref.get(transaction=tx)
            u = {**EMPTY_AI_USAGE, **(snap.to_dict() or {})} if snap.exists else dict(EMPTY_AI_USAGE)
            if u["alerted"]:
                return False
            tx.set(ref, {**u, "alerted": True, "updated_at": now_iso()})
            return True
        async with self._lock("ai_usage"):
            return await txn(self.db.transaction())

    # pseudonyms towards the engine (P-48): actor_refs/{uid} = {ref}, claimed with create(); actors/{ref} = who
    async def claim_actor_ref(self, uid, candidate):
        ref = self._col("actor_refs").document(uid)
        try:
            await ref.create({"ref": candidate})
            return candidate
        except AlreadyExists:
            return (await ref.get()).get("ref")

    async def put_actor(self, record):
        # both directions get the same expiry, renewed on use (P-54): 24 months after the person last acted
        until = retention.pseudonym()
        await self._col("actor_refs").document(record.uid).set({"ref": record.ref, retention.FIELD: until})
        return await self._put("actors", record.ref, record, until)

    async def get_actors(self, refs):
        refs = sorted(set(refs))
        if not refs:
            return {}
        snaps = self.db.get_all([self._col("actors").document(r) for r in refs])
        return {snap.id: ActorRecord(**snap.to_dict()) async for snap in snaps if snap.exists}

    async def forget_actor(self, uid):
        ref = self._col("actor_refs").document(uid)
        snap = await ref.get()
        if not snap.exists:
            return False
        await self._col("actors").document(snap.get("ref")).delete()
        await ref.delete()
        return True

    # support access (P-50): support_access/{access_id}; equality filters only (automatic indexes), sorted here
    async def add_support_access(self, access):
        return await self._put("support_access", access.access_id, access, retention.support(access.model_dump()))

    async def get_support_access(self, access_id):
        return await self._get("support_access", access_id, SupportAccess)

    async def list_support_access(self, tenant_id=None, operator_uid=None):
        # D-91 (F1): with no filter at all, every access (a filter on None would mean "field IS NULL": nothing)
        if tenant_id is not None:
            items = await self._query("support_access", SupportAccess, "tenant_id", tenant_id)
        elif operator_uid is not None:
            items = await self._query("support_access", SupportAccess, "operator_uid", operator_uid)
        else:
            items = await self._query("support_access", SupportAccess)
        items = [a for a in items if (tenant_id is None or a.tenant_id == tenant_id)
                 and (operator_uid is None or a.operator_uid == operator_uid)]
        return sorted(items, key=lambda a: a.opened_at, reverse=True)

    async def update_support_access(self, access_id, fields):
        try:
            await self._col("support_access").document(access_id).update(fields)
        except NotFound:
            return None
        return await self.get_support_access(access_id)

    async def close_support_access(self, access_id, closed_at, by):
        ref = self._col("support_access").document(access_id)

        @firestore.async_transactional
        async def txn(tx):
            snap = await ref.get(transaction=tx)
            if not snap.exists or snap.get("closed_at") is not None:
                return False
            tx.update(ref, {"closed_at": closed_at, "closed_by": by})
            return True
        async with self._lock(f"support:{access_id}"):
            return await txn(self.db.transaction())

    # platform managers (P-36): document id = normalised email
    async def get_platform_member(self, email):
        return await self._get("platform_members", normalize_email(email), PlatformMember)

    async def list_platform_members(self):
        return sorted(await self._query("platform_members", PlatformMember), key=lambda m: m.email)

    async def add_platform_member(self, member):
        member.email = normalize_email(member.email)
        return await self._put("platform_members", member.email, member)

    async def remove_platform_member(self, email):
        return await self._delete("platform_members", normalize_email(email))

    # atomic claims (P-36): document.create() fails if the document exists, also across instances
    async def create_user_if_absent(self, user):
        user.email = user.email.lower()
        try:
            await self._col("users").document(user.uid).create(user.model_dump())
            return True
        except AlreadyExists:
            return False

    def _name_ref(self, name_key):
        return self._col("tenant_names").document(hashlib.sha256(name_key.encode()).hexdigest())

    async def claim_tenant_name(self, name_key, tenant_id):
        ref = self._name_ref(name_key)
        try:
            await ref.create({"name_key": name_key, "tenant_id": tenant_id})
            return None
        except AlreadyExists:
            owner = (await ref.get()).get("tenant_id")
            return None if owner == tenant_id else owner

    async def release_tenant_name(self, name_key, tenant_id):
        ref = self._name_ref(name_key)
        snap = await ref.get()
        if snap.exists and snap.get("tenant_id") == tenant_id:
            await ref.delete()

    async def reserve_apartment_id(self, apartment_id):
        try:
            await self._col("apartment_ids_used").document(apartment_id).create({"reserved_at": now_iso()})
            return True
        except AlreadyExists:
            return False

    # P-36 point 14: read and write in one transaction; Firestore serialises transactions that touch the same documents,
    # so of two people demoting or removing each other the second one sees the first change and is refused
    def _admins_query(self, tenant_id):
        return (self._col("users").where(filter=firestore.FieldFilter("tenant_id", "==", tenant_id))
                .where(filter=firestore.FieldFilter("role", "==", "admin")))

    async def upsert_user_keeping_an_admin(self, user):
        user.email = user.email.lower()
        ref = self._col("users").document(user.uid)

        @firestore.async_transactional
        async def txn(tx):
            admins = [d.id async for d in self._admins_query(user.tenant_id).stream(transaction=tx)]
            if user.role != "admin" and user.uid in admins and len(admins) == 1:
                return False
            tx.set(ref, user.model_dump())
            return True
        async with self._lock(f"admins:{user.tenant_id}"):
            return await txn(self.db.transaction())

    async def delete_user_keeping_an_admin(self, uid):
        ref = self._col("users").document(uid)
        first = await ref.get()  # only to know which organisation to lock: a user never changes organisation
        if not first.exists:
            return "not_found"

        @firestore.async_transactional
        async def txn(tx):
            snap = await ref.get(transaction=tx)
            if not snap.exists:
                return "not_found"
            if snap.get("role") == "admin":
                admins = [d.id async for d in self._admins_query(snap.get("tenant_id")).stream(transaction=tx)]
                if admins == [uid]:
                    return "last_admin"
            tx.delete(ref)
            return "deleted"
        async with self._lock(f"admins:{first.get('tenant_id')}"):
            return await txn(self.db.transaction())

    async def remove_platform_member_keeping_one(self, email):
        email = normalize_email(email)

        @firestore.async_transactional
        async def txn(tx):
            members = [d.id async for d in self._col("platform_members").stream(transaction=tx)]
            if email not in members:
                return "not_found"
            if len(members) <= 1:
                return "last"
            tx.delete(self._col("platform_members").document(email))
            return "removed"
        async with self._lock("platform_members"):
            return await txn(self.db.transaction())

    def _external_ref(self, source, code):
        return self._col("external_ids").document(hashlib.sha256(f"{source}:{code}".encode()).hexdigest())

    async def claim_external_id(self, source, code, apartment_id):
        ref = self._external_ref(source, code)
        try:
            await ref.create({"source": source, "code": code, "apartment_id": apartment_id})
            return None
        except AlreadyExists:
            owner = (await ref.get()).get("apartment_id")
            return None if owner == apartment_id else owner

    async def release_external_id(self, source, code, apartment_id):
        ref = self._external_ref(source, code)
        snap = await ref.get()
        if snap.exists and snap.get("apartment_id") == apartment_id:
            await ref.delete()
