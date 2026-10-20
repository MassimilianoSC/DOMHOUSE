"""The contract's features as the BFF uses them; the x-features map itself lives in engine/features.py."""
from engine.features import FEATURE_MAP, feature_for  # noqa: F401  (re-exported for the BFF)

APP_FEATURES = ["apartment", "devices", "commands", "energy", "schedule", "rules", "approvals", "decisions", "ask"]


def configured_features(tenant_features: list[str] | None, apartment_features: list[str] | None) -> set[str]:
    """Features enabled in our own configuration; apartment overrides tenant, None = all."""
    chosen = apartment_features if apartment_features is not None else tenant_features
    return set(APP_FEATURES) if chosen is None else set(chosen) & set(APP_FEATURES)


def effective_features(instance_features: list[str] | None, tenant_features, apartment_features) -> list[str]:
    instance = set(instance_features or [])
    allowed = configured_features(tenant_features, apartment_features)
    return [f for f in APP_FEATURES if f in instance and f in allowed]
