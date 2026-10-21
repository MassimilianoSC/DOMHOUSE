from functools import lru_cache

from ..config import get_settings
from .base import (
    ActorRecord,
    Apartment,
    AuditActor,
    AuditEntry,
    AuditPerson,
    AuditTarget,
    BookingRecord,
    ExternalIds,
    NotificationPrefs,
    PlatformMember,
    Repository,
    SupportAccess,
    Tenant,
    User,
    WebhookLog,
    apply_booking_event,
    normalize_email,
)
from .memory import InMemoryRepository
from .seed import seed_demo

__all__ = ["ActorRecord", "Apartment", "AuditActor", "AuditEntry", "AuditPerson", "AuditTarget", "BookingRecord", "ExternalIds", "NotificationPrefs", "PlatformMember", "Repository", "SupportAccess", "Tenant", "User", "WebhookLog",
           "apply_booking_event", "get_repository", "normalize_email"]


@lru_cache
def get_repository() -> Repository:
    settings = get_settings()
    if settings.repository == "firestore":
        from .firestore import FirestoreRepository

        return FirestoreRepository(project_id=settings.gcp_project_id, database=settings.firestore_database)
    repo = InMemoryRepository()
    seed_demo(repo)
    return repo
