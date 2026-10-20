"""Guard against Cloud Run's reserved URL paths (E-12): its front end answers 404 itself, without reaching the container,
for paths starting with /_ah/ and for some paths ending in "z" (https://cloud.google.com/run/docs/known-issues,
"Reserved URL paths"). /healthz is kept only for Cloud Run's internal probes; every other route must avoid both."""
from fastapi.routing import APIRoute

from bff.main import app

PROBE_ONLY = {"/healthz"}  # internal startup/liveness probes (cloudrun*.yaml), never called from outside


def _paths() -> set[str]:
    return {r.path for r in app.routes if isinstance(r, APIRoute)}


def test_no_public_route_on_a_reserved_path():
    bad = sorted(p for p in _paths() - PROBE_ONLY if p.rstrip("/").endswith("z") or p.startswith("/_ah/"))
    assert bad == [], f"percorsi riservati da Cloud Run, irraggiungibili da fuori: {bad}"


def test_public_health_twin_exists():
    assert {"/health", "/healthz"} <= _paths()


# -------- platform separation (P-36): structural, so a future route cannot forget it --------
def _depends_on(route: APIRoute, fn) -> bool:
    return any(d.dependency is fn for d in route.dependencies) or any(d.call is fn for d in route.dependant.dependencies)


def test_every_platform_route_requires_the_platform_role():
    from bff.auth import require_platform

    platform = [r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/app/platform")]
    assert platform, "nessuna rotta di piattaforma registrata"
    missing = [f"{sorted(r.methods)} {r.path}" for r in platform if not _depends_on(r, require_platform)]
    assert missing == [], f"rotte di piattaforma senza require_platform: {missing}"
    leaking = [r.path for r in platform if any(w in r.path for w in ("instance", "stream", "bookings", "/users"))]
    assert leaking == [], f"la piattaforma non deve raggiungere dati interni: {leaking}"


def test_organisation_routes_never_use_the_platform_role():
    from bff.auth import require_platform

    org = [r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/app/") and not r.path.startswith("/app/platform")]
    assert [r.path for r in org if _depends_on(r, require_platform)] == []


def test_platform_module_has_no_way_into_organisation_data():
    from pathlib import Path

    import ast

    tree = ast.parse((Path(__file__).resolve().parent.parent / "bff" / "routes" / "platform.py").read_text(encoding="utf-8"))
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    used |= {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    forbidden = {"get_tenant_apartment", "resolve_user", "call", "list_users", "list_bookings", "get_booking", "proxy"}
    assert used & forbidden == set(), f"platform.py usa {sorted(used & forbidden)}"


def test_no_organisation_route_takes_a_tenant_from_the_client():
    """P-36 point 1: the organisation always comes from the token (claims) or the user's record, never from the request.
    Only /app/platform/* (require_platform) names a tenant, in its path."""
    def names(route):
        d = route.dependant
        out = {p.name for p in d.path_params + d.query_params + d.header_params}
        for b in d.body_params:
            model = getattr(b, "type_", None) or getattr(getattr(b, "field_info", None), "annotation", None)
            out |= set(getattr(model, "model_fields", {}) or {})
            out.add(b.name)
        return out

    org = [r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/app/") and not r.path.startswith("/app/platform")]
    bad = [f"{r.path} {sorted(names(r) & {'tenant_id', 'tenant'})}" for r in org if names(r) & {"tenant_id", "tenant"}]
    assert bad == [], f"rotte di organizzazione che accettano un tenant dal client: {bad}"
    assert any(names(r) for r in org)                                        # the inspection does see parameters


# -------- D-88 (Fable): the person's own account never follows X-Support-Tenant --------
def test_own_account_and_push_routes_ignore_the_support_header():
    from bff.auth import resolve_own_user, resolve_user

    def calls(route):
        stack, found = list(route.dependant.dependencies), set()
        while stack:
            d = stack.pop()
            found.add(d.call)
            stack.extend(d.dependencies)
        return found

    own = [r for r in app.routes if isinstance(r, APIRoute) and (
        r.path.startswith("/app/push") or r.path in ("/app/me/revoke-sessions", "/app/me/notification-prefs")
        or (r.path == "/app/me" and r.methods & {"PATCH", "DELETE"}))]
    assert len(own) >= 7, [r.path for r in own]
    wrong = [f"{sorted(r.methods)} {r.path}" for r in own
             if resolve_user in calls(r) or not ({resolve_own_user} & calls(r) or _own_identity(calls(r)))]
    assert wrong == [], f"rotte del proprio account che seguirebbero l'assistenza: {wrong}"


def _own_identity(found) -> bool:
    import bff.auth as auth

    return getattr(auth, "resolve_own_identity", None) in found
