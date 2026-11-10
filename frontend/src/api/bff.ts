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
  /** How long this call may take; CALL_TIMEOUT_MS unless it is one of the known slow ones. */
  timeoutMs?: number;
}

/** D-198: a call with no answer ends in «Server non raggiungibile» instead of a page loading for ever. The stream does not come through here. */
export const CALL_TIMEOUT_MS = 30_000;
/** Calls the server itself may spend tens of seconds on: the model, the email of an invite, several engines, the Excel file. */
export const SLOW_CALL_TIMEOUT_MS = 90_000;

const networkError = (correlationId?: string) => new ApiError(0, "network", t("errors.network"), correlationId ?? null);

/** The token: an expired one that cannot be renewed for lack of network is the same «Server non raggiungibile» as a
 *  failed call, not «Operazione non riuscita». Any other refusal of the sign-in service goes on as it is. */
async function tokenHeaders(correlationId?: string): Promise<Record<string, string>> {
  try {
    return await resolveAuth();
  } catch (err) {
    if ((err as { code?: unknown } | null)?.code === "auth/network-request-failed") throw networkError(correlationId);
    throw err;
  }
}

/** The whole call, the token and the reading of the answer included, within `ms`; then the request is dropped. */
async function withinTime<T>(ms: number, correlationId: string | undefined, work: (signal: AbortSignal) => Promise<T>): Promise<T> {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const expired = new Promise<never>((_, reject) => {
    timer = setTimeout(() => {
      reject(networkError(correlationId));
      controller.abort();
    }, ms);
  });
  try {
    return await Promise.race([work(controller.signal), expired]);
  } finally {
    clearTimeout(timer);
  }
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

export function bffFetch<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  return withinTime(opts.timeoutMs ?? CALL_TIMEOUT_MS, opts.correlationId, async (signal) => {
    const headers: Record<string, string> = { Accept: "application/json", ...(await tokenHeaders(opts.correlationId)), ...supportHeader(path, opts.method) };
    if (opts.correlationId) headers["X-Correlation-Id"] = opts.correlationId;
    if (opts.body !== undefined) headers["Content-Type"] = "application/json";
    let resp: Response;
    let text: string;
    try {
      resp = await fetch(buildUrl(path, opts.query), {
        method: opts.method ?? "GET",
        headers,
        body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
        signal,
      });
      text = resp.status === 204 ? "" : await resp.text();
    } catch {
      throw networkError(opts.correlationId);
    }
    if (resp.status === 204) return undefined as T;
    const data = parseJson(text);
    if (!resp.ok) throw refusal(resp, data, path, opts.correlationId ?? null);
    return data as T;
  });
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
export function bffDownload(path: string, opts: { query?: RequestOptions["query"]; correlationId?: string; fallbackName: string }): Promise<{ blob: Blob; name: string }> {
  return withinTime(SLOW_CALL_TIMEOUT_MS, opts.correlationId, async (signal) => {
    const headers: Record<string, string> = { ...(await tokenHeaders(opts.correlationId)), ...supportHeader(path) };
    if (opts.correlationId) headers["X-Correlation-Id"] = opts.correlationId;
    let resp: Response;
    let blob: Blob | null = null;
    let text = "";
    try {
      resp = await fetch(buildUrl(path, opts.query), { headers, signal });
      if (resp.ok) blob = await resp.blob();
      else text = await resp.text();
    } catch {
      throw networkError(opts.correlationId);
    }
    if (!blob) throw refusal(resp, parseJson(text), path, opts.correlationId ?? null);
    return { blob, name: fileNameFrom(resp.headers.get("Content-Disposition")) ?? opts.fallbackName };
  });
}
