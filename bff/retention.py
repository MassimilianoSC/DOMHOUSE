"""P-54 (D-94): how long each kind of record lives in Firestore.

The Firestore repository writes a TIMESTAMP field `expire_at` (FIELD) next to the record; a TTL policy per collection
group (created once with `gcloud firestore fields ttls update expire_at --collection-group=<name> --enable-ttl`, see
COLLECTIONS) deletes the document within about a day after that moment. Native TTL costs no reads and needs no
scheduler (C-2). The models and the API never see the field. Live data (users, organisations, apartments, managers,
claims) has no expiry.

Each rule takes the stored document (a dict) and returns its expiry; scripts/backfill_expire_at.py uses the same rules
for documents saved before lot 11.
"""
import calendar
from datetime import UTC, datetime, timedelta

FIELD = "expire_at"
BOOKING_MONTHS = 12        # after the check-out (D-94)
SUMMARY_MONTHS = 12        # the weekly summaries (D-150)
AI_STATS_MONTHS = 12       # the assistant's weekly counters (decision 120, D-183 point 129)
AUDIT_MONTHS = 24          # the administrative log
SUPPORT_MONTHS = 24        # closed support accesses: from the end of the window (at most 24 h after opening)
WEBHOOK_DAYS = 90          # received Italianway calls, besides the 100 per organisation
MAIL_DAYS = 3              # anti-abuse counters: their windows last at most a day
PEOPLE_MONTHS = 24         # audit_people: from the last entry that cites the person (every entry rewrites them)
ACTOR_MONTHS = 24          # pseudonyms: from the last use, renewed at most weekly (bff/actors.py)


def now() -> datetime:
    return datetime.now(UTC)


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def add_months(dt: datetime, months: int) -> datetime:
    """Same day and time `months` later; the last day of the month when that day does not exist (31 → 30, 29 Feb)."""
    y, m = divmod(dt.month - 1 + months, 12)
    year, month = dt.year + y, m + 1
    return dt.replace(year=year, month=month, day=min(dt.day, calendar.monthrange(year, month)[1]))


def booking(doc: dict) -> datetime:
    return add_months(parse(doc["checkout_at"]), BOOKING_MONTHS)


def audit(doc: dict) -> datetime:
    return add_months(parse(doc["at"]), AUDIT_MONTHS)


def support(doc: dict) -> datetime:
    return add_months(parse(doc["expires_at"]), SUPPORT_MONTHS)


def webhook(doc: dict) -> datetime:
    return parse(doc["received_at"]) + timedelta(days=WEBHOOK_DAYS)


def mail(doc: dict) -> datetime:
    when = parse(doc["updated_at"]) if doc.get("updated_at") else now()
    return when + timedelta(days=MAIL_DAYS)


def person(_doc: dict | None = None) -> datetime:
    return add_months(now(), PEOPLE_MONTHS)


def summary(doc: dict) -> datetime:
    """P-60 step 11 (D-150): a weekly summary is kept 12 months after it was made."""
    return add_months(parse(doc["generated_at"]), SUMMARY_MONTHS)


def ai_stats(doc: dict) -> datetime:
    """Decision 120: the assistant's counters of a week are kept 12 months after its Monday («from»)."""
    return add_months(datetime.fromisoformat(doc["from"]).replace(tzinfo=UTC), AI_STATS_MONTHS)


def pseudonym(_doc: dict | None = None) -> datetime:
    return add_months(now(), ACTOR_MONTHS)


# collection group -> rule; the TTL policies are created on exactly these names (also the subcollection "audit")
COLLECTIONS = {
    "bookings": booking,
    "audit": audit,
    "platform_audit": audit,
    "support_access": support,
    "webhook_logs": webhook,
    "mail_limits": mail,
    "audit_people": person,
    "actors": pseudonym,
    "actor_refs": pseudonym,
    "summaries": summary,
    "ai_stats": ai_stats,
}
