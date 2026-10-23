import os
import secrets
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=False)


def _bool(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class Settings:
    app_env: str
    auth_mode: str
    instance_mode: str
    repository: str
    fcm_enabled: bool
    gcp_project_id: str
    gcp_region: str
    firebase_project_id: str
    secret_manager_prefix: str
    instance_api_key_fallback: str
    instance_timeout_s: float
    italianway_webhook_secret: str
    italianway_signature_header: str
    port: int
    root_path: str
    cors_origins: tuple[str, ...]
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    mail_from_name: str
    app_public_url: str
    # P-60 step 9 (D-132, D-143): the assistant's way to the model (POST /internal/ai/chat, bff/ai_gateway.py)
    ai_model: str = "google/gemini-3.8-flash"
    ai_location: str = "eu"                   # Agent Platform: the models are not in europe-west8
    ai_monthly_cap_eur: float = 20.0          # for the whole project: at the cap the assistant stops until next month
    ai_alert_percent: float = 80.0            # one email to the platform managers, once a month
    # euro per million tokens (1 $ = 1 € on purpose). Introductory price of the EU endpoint until 31 December 2026: to be
    # raised on 1 January 2027 to 1.65 (in) and 8.25 (out) (D-143, C-8). Reasoning tokens are paid as output.
    ai_price_in_eur_per_m: float = 0.83
    ai_price_out_eur_per_m: float = 4.13
    ai_price_cached_eur_per_m: float = 0.08
    ai_max_tokens: int = 4096                 # the most a call may ask (the flash model spends tokens on reasoning)
    ai_timeout_s: float = 25.0                # inside the contract's 30 s for an answer (reading the answer)
    ai_connect_timeout_s: float = 5.0         # DNS, TCP and TLS each (lot 30, the committente's instruction)
    ai_reasoning_effort: str = ""             # C-10: «low»… for the OpenAI-compatible endpoint; "" sends nothing
    ai_api: str = "nativo"                    # D-182: Vertex's own generateContent («openai» = the compatible endpoint)
    ai_thinking_budget: int = 0               # D-182: reasoning off on the native endpoint (-1 = not sent)
    ai_hedge_after_s: float = 6.0             # C-10: a second identical request when the first is still silent
    # D-187: the twin on a different model ("" = the same model), with its own prices (empty = the main ones)
    ai_twin_model: str = ""
    ai_twin_price_in_eur_per_m: float | None = None
    ai_twin_price_out_eur_per_m: float | None = None
    ai_twin_price_cached_eur_per_m: float | None = None
    ai_demos: bool = False                    # the demonstration apartments with the real model (AI_DEMOS=true)
    # P-67 (D-136): the Firestore database of this environment, "(default)" in production, "staging" in staging
    firestore_database: str = "(default)"
    summary_job: bool = True                  # P-60 step 11: the weekly summary's hourly round (off in the test runs)

    @property
    def mail_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)

    @property
    def is_dev(self) -> bool:
        return self.app_env == "dev"


def european_location(location: str) -> bool:
    """D-180: the model runs in the European Union: the multi-region eu or a European region (europe-…); never global
    nor us, for any model and any environment."""
    v = (location or "").strip().lower()
    return v == "eu" or v.startswith("europe-")


def _float_or_none(raw: str) -> float | None:
    return float(raw) if raw.strip() else None


@lru_cache
def get_settings() -> Settings:
    e = os.environ.get
    return Settings(
        app_env=e("APP_ENV", "dev"),
        auth_mode=e("AUTH_MODE", "dev"),
        instance_mode=e("INSTANCE_MODE", "mock"),
        repository=e("REPOSITORY", "memory"),
        fcm_enabled=_bool("FCM_ENABLED"),
        gcp_project_id=e("GCP_PROJECT_ID", ""),
        gcp_region=e("GCP_REGION", "europe-west8"),
        firebase_project_id=e("FIREBASE_PROJECT_ID", ""),
        secret_manager_prefix=e("SECRET_MANAGER_PREFIX", "langbrain-api-key-"),
        # key of the built-in mock (F2, D-70): when not configured, a random one per process, never a fixed placeholder
        instance_api_key_fallback=e("INSTANCE_API_KEY_FALLBACK") or secrets.token_urlsafe(24),
        instance_timeout_s=float(e("INSTANCE_TIMEOUT_S", "10")),
        italianway_webhook_secret=e("ITALIANWAY_WEBHOOK_SECRET", ""),
        italianway_signature_header=e("ITALIANWAY_SIGNATURE_HEADER", "X-Signature"),
        port=int(e("PORT", "8000")),
        root_path=e("BFF_ROOT_PATH", ""),
        # Origini della PWA ammesse dal BFF fuori da dev (es. https://<progetto>.web.app), separate da virgola.
        cors_origins=tuple(o.strip() for o in e("CORS_ORIGINS", "").split(",") if o.strip()),
        # Invitation emails (SMTP over SSL). SMTP_PASSWORD comes from Secret Manager on Cloud Run; without
        # SMTP_USER/SMTP_PASSWORD the invite is only recorded and the admin is told to notify the user.
        smtp_host=e("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=int(e("SMTP_PORT", "465")),
        smtp_user=e("SMTP_USER", "").strip(),
        smtp_password=e("SMTP_PASSWORD", "").replace(" ", "").strip(),  # Gmail shows app passwords in groups of 4
        mail_from_name=e("MAIL_FROM_NAME", "DOMHOUSE"),
        # Public URL of the PWA, used in invitation emails and as continue URL of the password setup link.
        app_public_url=e("APP_PUBLIC_URL", "").rstrip("/"),
        ai_model=e("AI_MODEL", "google/gemini-3.8-flash"),
        ai_location=e("AI_LOCATION", "eu"),
        ai_monthly_cap_eur=float(e("AI_MONTHLY_CAP_EUR", "20")),
        ai_alert_percent=float(e("AI_ALERT_PERCENT", "80")),
        ai_price_in_eur_per_m=float(e("AI_PRICE_IN_EUR_PER_M", "0.83")),
        ai_price_out_eur_per_m=float(e("AI_PRICE_OUT_EUR_PER_M", "4.13")),
        ai_price_cached_eur_per_m=float(e("AI_PRICE_CACHED_EUR_PER_M", "0.08")),
        ai_max_tokens=int(e("AI_MAX_TOKENS", "4096")),
        ai_timeout_s=float(e("AI_TIMEOUT_S", "25")),
        ai_connect_timeout_s=float(e("AI_CONNECT_TIMEOUT_S", "5")),
        ai_reasoning_effort=e("AI_REASONING_EFFORT", "").strip().lower(),
        ai_api=e("AI_API", "nativo").strip().lower(),
        ai_thinking_budget=int(e("AI_THINKING_BUDGET", "0")),
        ai_hedge_after_s=float(e("AI_HEDGE_AFTER_S", "6")),
        ai_twin_model=e("AI_TWIN_MODEL", "").strip(),
        ai_twin_price_in_eur_per_m=_float_or_none(e("AI_TWIN_PRICE_IN_EUR_PER_M", "")),
        ai_twin_price_out_eur_per_m=_float_or_none(e("AI_TWIN_PRICE_OUT_EUR_PER_M", "")),
        ai_twin_price_cached_eur_per_m=_float_or_none(e("AI_TWIN_PRICE_CACHED_EUR_PER_M", "")),
        ai_demos=_bool("AI_DEMOS"),
        firestore_database=e("FIRESTORE_DATABASE", "(default)").strip() or "(default)",
        summary_job=_bool("SUMMARY_JOB", "true"),
    )
