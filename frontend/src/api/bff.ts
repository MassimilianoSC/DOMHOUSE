import { t } from "@/i18n";
import { supportHeader } from "@/lib/support";
import { env } from "@/lib/utils";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public correlationId: string | null,
    public details?: Record<string, unknown>,
  ) {
    super(message);
  }
}

type AuthResolver = () => Promise<Record<string, string>>;
let resolveAuth: AuthResolver = async () => ({});

export function setAuthResolver(fn: AuthResolver) {
  resolveAuth = fn;
}

/** Answers that change who the user is, whatever the call (P-50): the auth layer re-reads the profile. */
const BLOCKING = new Set(["tenant_suspended", "support_expired"]);
let onBlocked: (code: string) => void = () => {};

export function setBlockedHandler(fn: (code: string) => void) {
  onBlocked = fn;
}

/** Auth travels only in headers (never in the URL, which ends up in server and browser logs); `path` adds the
 *  assistance header where it belongs (P-50). */
export async function authHeaders(path?: string): Promise<Record<string, string>> {
  return { ...(await resolveAuth()), ...(path ? supportHeader(path) : {}) };
}

export interface RequestOptions {
  method?: string;
  query?: Record<string, string | number | undefined | null>;
  body?: unknown;
  correlationId?: string;
}

export function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(env.bffUrl + path, window.location.origin);
  Object.entries(query ?? {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  });
  return url.toString();
}

/** The ApiError of a refused answer; a blocking one (suspension, assistance over) is also reported (P-50). */
function refusal(resp: Response, data: unknown, path: string, correlationId: string | null): ApiError {
  const body = (data ?? {}) as { error?: string; message?: string; details?: Record<string, unknown>; detail?: unknown };
  // FastAPI's own validation answer ({"detail": [...]}) has no Italian message: say it plainly instead of "Errore 422".
  const validation = !body.message && Array.isArray(body.detail);
  const message = body.message ?? (validation ? t("errors.invalidRequest") : t("errors.status", { status: resp.status }));
  // The profile read (/app/me) handles its own refusal: only the other calls report it, or a refused profile read would
  // report itself and start another one, forever.
  if (resp.status === 403 && body.error && BLOCKING.has(body.error) && path !== "/app/me") onBlocked(body.error);
  return new ApiError(resp.status, body.error ?? (validation ? "validation_error" : "error"), message, correlationId, body.details);
}

const parseJson = (text: string): unknown => {
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return null;
  }
};

export async function bffFetch<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...(await resolveAuth()), ...supportHeader(path, opts.method) };
  if (opts.correlationId) headers["X-Correlation-Id"] = opts.correlationId;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  let resp: Response;
  try {
    resp = await fetch(buildUrl(path, opts.query), {
      method: opts.method ?? "GET",
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  } catch {
    throw new ApiError(0, "network", t("errors.network"), opts.correlationId ?? null);
  }
  if (resp.status === 204) return undefined as T;
  const data = parseJson(await resp.text());
  if (!resp.ok) throw refusal(resp, data, path, opts.correlationId ?? null);
  return data as T;
}

/** File name from Content-Disposition: filename* (UTF-8) first, then filename; null when there is none. */
export function fileNameFrom(header: string | null): string | null {
  if (!header) return null;
  const star = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(header);
  if (star) {
    try {
      return decodeURIComponent(star[1].trim().replace(/^"|"$/g, ""));
    } catch {
      /* badly encoded: try the plain name */
    }
  }
  const plain = /filename\s*=\s*(?:"([^"]+)"|([^;]+))/i.exec(header);
  return plain ? (plain[1] ?? plain[2]).trim() : null;
}

/**
 * A file from the BFF (P-52): it needs the auth headers, so it is fetched (not a plain link) and named as the server
 * says in Content-Disposition. A refusal comes back as the usual ApiError, with the server's message.
 */
export async function bffDownload(path: string, opts: { query?: RequestOptions["query"]; correlationId?: string; fallbackName: string }): Promise<{ blob: Blob; name: string }> {
  const headers: Record<string, string> = { ...(await resolveAuth()), ...supportHeader(path) };
  if (opts.correlationId) headers["X-Correlation-Id"] = opts.correlationId;
  let resp: Response;
  try {
    resp = await fetch(buildUrl(path, opts.query), { headers });
  } catch {
    throw new ApiError(0, "network", t("errors.network"), opts.correlationId ?? null);
  }
  if (!resp.ok) throw refusal(resp, parseJson(await resp.text()), path, opts.correlationId ?? null);
  return { blob: await resp.blob(), name: fileNameFrom(resp.headers.get("Content-Disposition")) ?? opts.fallbackName };
}
