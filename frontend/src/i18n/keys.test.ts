// @vitest-environment node
import type { NotificationPrefs, Role, SimBookingInput } from "@/api/admin";
import { APP_FEATURES, type ApartmentMode, type Approval, type AskStatus, type CommandReason, type Decision, type Health, type Occupancy, type Rule, type ScheduleItem } from "@/api/types";
import type { ClimateState } from "@/components/devices/capabilities/types";
import { apartmentNav, globalNav } from "@/components/layout/navItems";
import { AUDIT_ACTIONS } from "@/lib/auditLog";
import { BOOKING_TYPES, type OutcomeKind } from "@/lib/bookingLog";
import type { SummaryStatus } from "@/api/summaries";
import * as ts from "typescript";
import italian from "./it.json";

/**
 * Every t()/tOr() key the code asks for must exist in it.json.
 * - Keys written in full ("nav.overview") are checked one by one.
 * - Keys built at runtime (`mode.${m}`) must be declared in FORMS below with every value they can take: a new form
 *   that is not declared fails the test, so its values get listed (from the contract enums where they exist).
 */

type Dict = { [k: string]: string | Dict };

function leaves(node: Dict, prefix = ""): string[] {
  return Object.entries(node).flatMap(([k, v]) => (typeof v === "string" ? [`${prefix}${k}`] : leaves(v, `${prefix}${k}.`)));
}

/** All values of a string union, checked by the compiler: a value missing from or extra to the union is a type error. */
const all = <T extends string>(o: Record<T, true>) => Object.keys(o) as T[];

const form = (tpl: string, values: readonly string[]): [string, string[]] => [tpl, values.map((v) => tpl.replace("${}", v))];

const MODES = all<ApartmentMode>({ comfort: true, eco: true, empty: true });
const NAV_KEYS = [...apartmentNav("x", true), ...globalNav(true, { platform: true })].map((i) => i.key);
const FEATURE_NAV = APP_FEATURES.map((f) => (f === "ask" ? "assistant" : f === "apartment" ? "overview" : f));
const NOTIFY = all<keyof NotificationPrefs>({ approvals: true, offline: true, decisions: true, bookings: true, summary: true });

/** Runtime-built forms (placeholders written as ${}) → every key they can produce. */
const FORMS: Record<string, string[]> = Object.fromEntries([
  form("admin.bookingsReceived.events.${}", BOOKING_TYPES),
  form("audit.actions.${}", AUDIT_ACTIONS),
  form("admin.bookingsReceived.outcomes.${}", all<OutcomeKind>({ forwarded: true, signature: true, engine: true, unknownApartment: true, disabled: true, unreadable: true, other: true })),
  ["${}.${}", [
    ...all<ClimateState["mode"]>({ heat: true, cool: true, dry: true, fan: true }).map((m) => `cap.climateModes.${m}`),
    ...all<ClimateState["fan"]>({ auto: true, low: true, mid: true, high: true }).map((f) => `cap.fans.${f}`),
  ]],
  form("account.errors.${}", ["wrongPassword", "weakPassword", "emailInUse", "invalidEmail", "tooManyRequests", "recentLogin", "network", "generic"]),
  form("actor.${}", ["brain", "rule", "user", "assistant", "system"]),
  form("approvals.onExpiry.${}", all<Approval["expires_action"]>({ reject: true, approve: true, wait: true })),
  form("approvals.source.${}", all<Approval["source"]>({ brain: true, organ: true, rule: true, assistant: true })),
  form("approvals.status.${}", all<Approval["status"]>({ pending: true, approved: true, rejected: true, expired: true })),
  form("assistant.status.${}", all<AskStatus["status"]>({ pending: true, answered: true, needs_approval: true, failed: true })),
  form("assistant.suggestions.${}", ["off", "temp", "at", "boiler"]),
  form("command.${}", ["timeout", "failed"]),
  form("command.reason.${}", all<CommandReason & string>({ device_offline: true, device_rejected: true, blocked_by_rule: true, blocked_by_priority: true, out_of_limits: true, no_confirmation: true, internal_error: true })),
  form("decisions.outcome.${}", all<Decision["outcome"]>({ applied: true, rejected: true, pending_approval: true, failed: true, informational: true })),
  form("decisions.target.${}", all<Decision["target"]["type"]>({ device: true, apartment: true, rules: true, schedule: true })),
  form("energy.${}", ["hour", "day"]),
  form("hold.${}", ["m30", "h2", "h6"]),
  form("instance.status.${}", all<Health["status"]>({ ok: true, degraded: true, down: true })),
  form("mode.${}", MODES),
  form("nav.${}", [...new Set([...NAV_KEYS, ...FEATURE_NAV])]),
  form("occupancy.${}", all<Occupancy>({ vacant: true, occupied: true, reserved: true })),
  form("roles.${}", all<Role>({ admin: true, operator: true, viewer: true })),
  form("rules.desc.${}", all<Rule["rule_id"]>({ window_open_off: true, setpoint_limits: true, frost_protection: true, mold_protection: true, prearrival: true, checkout_eco: true, compressor_min_off: true, offline_alert: true })),
  form("schedule.cmd${}", ["TurnOff", "TurnOn", "Setpoint"]),
  form("schedule.kind.${}", all<ScheduleItem["kind"]>({ prearrival: true, checkout: true, empty: true, manual: true })),
  form("schedule.source.${}", all<ScheduleItem["source"]>({ booking: true, manual: true, assistant: true })),
  form("schedule.status.${}", all<ScheduleItem["status"]>({ planned: true, done: true, cancelled: true, failed: true })),
  form("settings.notifications.${}", NOTIFY),
  form("settings.notifications.${}Hint", NOTIFY),
  form("summaries.status.${}", all<SummaryStatus>({ normal: true, anomalous: true, not_comparable: true, no_nights: true })),
  form("simulator.types.${}", all<SimBookingInput["type"]>({ booking_created: true, booking_changed: true, booking_cancelled: true, checkin: true, checkout: true })),
]);

/** Forms whose values are not a closed set (parameter names chosen by the engine): allowed only through tOr, which
 *  falls back to a readable text when the key is missing. */
const OPEN_FORMS = new Set(["rules.params.${}", "decisions.actions.${}"]);

interface Use {
  file: string;
  fn: "t" | "tOr";
  statics: string[];
  forms: string[];
}

/** Blanks // and /* comments, keeping strings and template literals intact. */
function stripComments(src: string): string {
  let out = "";
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    if (c === "/" && src[i + 1] === "/") {
      while (i < src.length && src[i] !== "\n") i++;
    } else if (c === "/" && src[i + 1] === "*") {
      const end = src.indexOf("*/", i + 2);
      i = end < 0 ? src.length : end + 2;
    } else if (c === '"' || c === "'" || c === "`") {
      const start = i++;
      while (i < src.length && src[i] !== c) i += src[i] === "\\" ? 2 : 1;
      out += src.slice(start, ++i);
    } else {
      out += c;
      i++;
    }
  }
  return out;
}

/** Reads a template literal starting at src[i] === "`": returns its text with every ${...} written as ${}. */
function readTemplate(src: string, i: number): [string, number] {
  let text = "";
  i++;
  while (i < src.length && src[i] !== "`") {
    if (src[i] === "\\") {
      text += src.slice(i, i + 2);
      i += 2;
    } else if (src[i] === "$" && src[i + 1] === "{") {
      let depth = 1;
      i += 2;
      while (i < src.length && depth > 0) {
        if (src[i] === "`") i = readTemplate(src, i)[1];
        else if (src[i] === '"' || src[i] === "'") i = readString(src, i)[1];
        else {
          if (src[i] === "{") depth++;
          if (src[i] === "}") depth--;
          i++;
        }
      }
      text += "${}";
    } else text += src[i++];
  }
  return [text, i + 1];
}

function readString(src: string, i: number): [string, number] {
  const q = src[i];
  let j = i + 1;
  while (j < src.length && src[j] !== q) j += src[j] === "\\" ? 2 : 1;
  return [src.slice(i + 1, j), j + 1];
}

/** Every t(...) / tOr(...) call: the literal keys and runtime forms in its first argument. */
export function scan(file: string, source: string): Use[] {
  const src = stripComments(source);
  const uses: Use[] = [];
  for (const m of src.matchAll(/(?<![\w$.])(tOr|t)\(/g)) {
    const use: Use = { file, fn: m[1] as Use["fn"], statics: [], forms: [] };
    let i = m.index! + m[0].length;
    let depth = 0;
    while (i < src.length) {
      const c = src[i];
      if (depth === 0 && (c === "," || c === ")")) break;
      if (c === '"' || c === "'") {
        const [s, next] = readString(src, i);
        if (depth === 0) use.statics.push(s);
        i = next;
      } else if (c === "`") {
        const [tpl, next] = readTemplate(src, i);
        if (depth === 0) use.forms.push(tpl.includes("${}") ? tpl : "");
        if (depth === 0 && !tpl.includes("${}")) use.statics.push(tpl);
        i = next;
      } else {
        if ("([{".includes(c)) depth++;
        if (")]}".includes(c)) depth--;
        i++;
      }
    }
    use.forms = use.forms.filter(Boolean);
    uses.push(use);
  }
  return uses;
}

interface Report {
  missing: string[];
  undeclared: string[];
  noLiteral: string[];
  formKeysMissing: string[];
}

export function check(uses: Use[], keys: Set<string>): Report {
  const r: Report = { missing: [], undeclared: [], noLiteral: [], formKeysMissing: [] };
  for (const u of uses) {
    if (!u.statics.length && !u.forms.length) r.noLiteral.push(`${u.file}: ${u.fn}(...) senza chiave scritta nel codice`);
    for (const k of u.statics) if (!keys.has(k)) r.missing.push(`${u.file}: "${k}"`);
    for (const f of u.forms) {
      if (OPEN_FORMS.has(f)) {
        if (u.fn !== "tOr") r.undeclared.push(`${u.file}: \`${f}\` ha valori aperti, va usata con tOr`);
      } else if (!FORMS[f]) r.undeclared.push(`${u.file}: \`${f}\` non è in FORMS: dichiara i valori che può prendere`);
    }
  }
  for (const [f, list] of Object.entries(FORMS)) for (const k of list) if (!keys.has(k)) r.formKeysMissing.push(`${f} → "${k}"`);
  return r;
}

/** Attributes whose string value reaches the user's eyes (or a screen reader). */
const VISIBLE_ATTRS = new Set(["label", "placeholder", "title", "aria-label", "alt", "hint", "subtitle", "description", "text"]);

/** Hand-written texts that are technical identifiers, not language: they stay as they are in every language. */
const TECHNICAL: Record<string, string[]> = {
  "/src/components/admin/apartmentForm.tsx": ["/health:", "/version:"], // endpoint names of the verification
  "/src/components/admin/AdminApartments.tsx": [" · IW "], // IW = Italianway id
  "/src/components/platform/PlatformApartments.tsx": [" · IW "], // IW = Italianway id
  "/src/pages/SettingsPage.tsx": ["· auth"], // environment row: "<app_env> · auth <auth_mode> · <instance_mode>"
};

const hasWord = (s: string) => /[A-Za-zÀ-ÿ]{2,}/.test(s);

/** User-visible texts written by hand in a .tsx file (JSX text, string branches of {...}, visible attributes). */
export function handwritten(file: string, source: string): string[] {
  const sf = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const found: string[] = [];
  const strings = (e: ts.Expression | undefined, acc: string[] = []): string[] => {
    if (!e) return acc;
    if (ts.isStringLiteral(e) || ts.isNoSubstitutionTemplateLiteral(e)) acc.push(e.text);
    else if (ts.isConditionalExpression(e)) strings(e.whenFalse, strings(e.whenTrue, acc));
    else if (ts.isParenthesizedExpression(e)) strings(e.expression, acc);
    else if (ts.isBinaryExpression(e) && [ts.SyntaxKind.BarBarToken, ts.SyntaxKind.QuestionQuestionToken, ts.SyntaxKind.AmpersandAmpersandToken].includes(e.operatorToken.kind)) strings(e.right, acc);
    else if (ts.isTemplateExpression(e)) acc.push(e.head.text, ...e.templateSpans.map((s) => s.literal.text));
    return acc;
  };
  const visit = (n: ts.Node) => {
    if (ts.isJsxText(n)) found.push(n.text.trim());
    if (ts.isJsxExpression(n) && !ts.isJsxAttribute(n.parent)) found.push(...strings(n.expression));
    if (ts.isJsxAttribute(n) && VISIBLE_ATTRS.has(n.name.getText(sf)) && n.initializer) {
      if (ts.isStringLiteral(n.initializer)) found.push(n.initializer.text);
      else if (ts.isJsxExpression(n.initializer)) found.push(...strings(n.initializer.expression));
    }
    ts.forEachChild(n, visit);
  };
  visit(sf);
  return found.filter(hasWord).filter((s) => !(TECHNICAL[file] ?? []).includes(s));
}

const SOURCES = import.meta.glob<string>(["/src/**/*.{ts,tsx}", "!/src/**/*.test.{ts,tsx}", "!/src/i18n/**", "!/src/api/schema.ts"], {
  query: "?raw",
  import: "default",
  eager: true,
});
const KEYS = new Set(leaves(italian as Dict));
const USES = Object.entries(SOURCES).flatMap(([file, src]) => scan(file, src));

describe("chiavi di traduzione", () => {
  it("il lettore trova le chiamate del codice", () => {
    // Measured on 2026-10-16: 351 literal keys and 35 runtime forms. Far fewer means the reader is broken.
    expect(Object.keys(SOURCES).length).toBeGreaterThan(50);
    expect(USES.flatMap((u) => u.statics).length).toBeGreaterThan(300);
    expect(USES.flatMap((u) => u.forms).length).toBeGreaterThan(30);
  });

  it("il lettore riconosce chiavi mancanti, forme non dichiarate e commenti", () => {
    const fake = [
      't("nav.overview"); tOr("non.esiste", "x"); t(ok ? "nav.rules" : "manca.anche")',
      "t(`mode.${m}`, { a: 1 }); t(`nuova.forma.${x}`); t(`rules.params.${k}`)",
      "// t(\"commento.ignorato\")\n/* t(\"anche.questo\") */ const url = \"https://x.it\"; t(chiave)",
      't(`command.${s === "timeout" ? "timeout" : "failed"}`)',
    ].join("\n");
    const r = check(scan("finto.tsx", fake), KEYS);
    expect(r.missing).toEqual(['finto.tsx: "non.esiste"', 'finto.tsx: "manca.anche"']);
    expect(r.undeclared).toEqual([
      "finto.tsx: `nuova.forma.${}` non è in FORMS: dichiara i valori che può prendere",
      "finto.tsx: `rules.params.${}` ha valori aperti, va usata con tOr",
    ]);
    expect(r.noLiteral).toEqual(["finto.tsx: t(...) senza chiave scritta nel codice"]);
  });

  it("ogni chiave scritta per esteso esiste in it.json", () => {
    expect(check(USES, KEYS).missing).toEqual([]);
  });

  it("ogni chiave composta a runtime è dichiarata e ogni suo valore esiste in it.json", () => {
    const r = check(USES, KEYS);
    expect(r.undeclared).toEqual([]);
    expect(r.formKeysMissing).toEqual([]);
  });

  it("ogni chiamata ha la chiave scritta nel codice", () => {
    expect(check(USES, KEYS).noLiteral).toEqual([]);
  });

  it("nessun testo per l'utente scritto a mano nei componenti: tutto passa da it.json", () => {
    const found = Object.entries(SOURCES)
      .filter(([file]) => file.endsWith(".tsx"))
      .flatMap(([file, src]) => handwritten(file, src).map((s) => `${file}: ${JSON.stringify(s)}`));
    expect(found).toEqual([]);
  });

  it("il lettore dei componenti riconosce i testi scritti a mano", () => {
    const fake = [
      "const A = () => <div title=\"Titolo\" className=\"p-2\" data-testid=\"x\">",
      "  Ciao {ok ? \"acceso\" : t(\"cap.off\")} {n} kWh {`${n} ore`}",
      "  <Input placeholder={t(\"login.email\")} aria-label=\"Chiudi\" type=\"email\" />",
      "  {/* commento */} {list.map((i) => <b key={i}>{i}</b>)} {\"—\"} {cond && \"vuoto\"}",
      "</div>;",
    ].join("\n");
    expect(handwritten("/src/finto.tsx", fake)).toEqual(["Titolo", "Ciao", "acceso", "kWh", " ore", "Chiudi", "vuoto"]);
  });

  it("conta i testi di it.json che il codice non usa (solo informazione)", () => {
    const used = new Set([...USES.flatMap((u) => u.statics), ...Object.values(FORMS).flat()]);
    const open = [...OPEN_FORMS].map((f) => f.split("${}")[0]);
    const unused = [...KEYS].filter((k) => !used.has(k) && !open.some((p) => k.startsWith(p)));
    console.info(`it.json: ${unused.length} testi non usati su ${KEYS.size}: ${unused.join(", ")}`);
    expect(unused.length).toBeLessThan(KEYS.size);
  });
});
