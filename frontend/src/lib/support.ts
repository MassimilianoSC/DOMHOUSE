// Assistance access (P-50, D-86): a platform manager works inside another organization for a limited time, with an
// operator's permissions. The mode lives in this tab only (sessionStorage): it survives a reload, never reaches other
// tabs, and ends with the tab. While it is on, every organization call carries X-Support-Tenant.

const KEY = "domotica.support";

export interface SupportSession {
  tenant_id: string;
  tenant_name: string;
  access_id: string;
  expires_at: string;
}

export function supportSession(): SupportSession | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const s = JSON.parse(raw) as Partial<SupportSession>;
    return s.tenant_id && s.access_id && s.expires_at ? { tenant_id: s.tenant_id, tenant_name: s.tenant_name ?? "", access_id: s.access_id, expires_at: s.expires_at } : null;
  } catch {
    return null;
  }
}

export function startSupportSession(s: SupportSession) {
  sessionStorage.setItem(KEY, JSON.stringify(s));
}

export function endSupportSession() {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: nothing was stored either */
  }
}

/**
 * White list (D-89): the header goes on the organization's data (apartments, and admin calls, so that a stray one is
 * refused by the server instead of reading the manager's own organization) and on the profile read. Never on the
 * person's own account (PATCH/DELETE /app/me, its preferences, revoke-sessions), on platform, push or dev routes.
 */
export function supportHeader(path: string, method = "GET"): Record<string, string> {
  const s = supportSession();
  if (!s) return {};
  const organization = path === "/app/apartments" || path.startsWith("/app/apartments/") || path.startsWith("/app/admin/");
  const profileRead = path === "/app/me" && method.toUpperCase() === "GET";
  return organization || profileRead ? { "X-Support-Tenant": s.tenant_id } : {};
}
