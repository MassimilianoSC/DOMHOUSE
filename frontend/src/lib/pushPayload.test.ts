// @vitest-environment node
import { deliverInApp, isOpenMessage, isPushMessage, isWebKitSafari, safeLink, toNotice, toastWanted } from "./pushPayload";

// Format S2 (D-31): FCM web push, data-only, delivered by the browser as { data: {...}, from, fcmMessageId }.
const approval = {
  from: "444239063209",
  fcmMessageId: "m-1",
  data: {
    title: "Milano Centro: approvazione richiesta",
    body: "Accendere il clima del soggiorno a 22 °C",
    link: "/a/apt-001/approvazioni",
    tag: "approval:ap-7",
    kind: "approval",
    apartment_id: "apt-001",
    approval_id: "ap-7",
    ts: "2026-10-16T08:00:00Z",
  },
};

describe("push: lettura del messaggio (formato S2)", () => {
  it("messaggio completo: titolo, testo, link, tag e appartamento", () => {
    expect(toNotice(approval, "DOMHOUSE")).toEqual({
      title: "Milano Centro: approvazione richiesta",
      body: "Accendere il clima del soggiorno a 22 °C",
      link: "/a/apt-001/approvazioni",
      tag: "approval:ap-7",
      apartmentId: "apt-001",
    });
  });

  it("mai una push muta: senza titolo, testo o link, o con un corpo illeggibile, notifica generica che apre /", () => {
    expect(toNotice({ data: { body: "x", link: "/a/apt-001" } }, "DOMHOUSE")).toEqual({ title: "DOMHOUSE", body: "x", link: "/" });
    expect(toNotice({ data: { title: "T", body: "B" } }, "DOMHOUSE")).toEqual({ title: "DOMHOUSE", body: "B", link: "/" });
    expect(toNotice(null, "DOMHOUSE")).toEqual({ title: "DOMHOUSE", body: "", link: "/" });
    expect(toNotice("non json", "DOMHOUSE")).toEqual({ title: "DOMHOUSE", body: "", link: "/" });
  });

  it("chiavi in più ignorate; un messaggio con il blocco «notification» non viene letto due volte", () => {
    const n = toNotice({ notification: { title: "X" }, data: { ...approval.data, extra: "1" } }, "D");
    expect(n.title).toBe(approval.data.title);
  });

  it("il link resta dentro l'app: niente altri siti, niente indirizzi con schema", () => {
    expect(safeLink("/a/apt-001")).toBe("/a/apt-001");
    for (const bad of ["https://altro.it", "//altro.it/x", "javascript:alert(1)", "a/apt-001", "/\\altro.it", 42, undefined]) expect(safeLink(bad)).toBe("/");
    expect(toNotice({ data: { ...approval.data, link: "https://altro.it" } }, "D").link).toBe("/");
  });
});

describe("push: dove compare l'avviso", () => {
  it("app aperta e in primo piano: dentro l'app, tranne su Safari che vuole sempre la notifica di sistema", () => {
    expect(deliverInApp(true, false)).toBe(true);
    expect(deliverInApp(true, true)).toBe(false);
    expect(deliverInApp(false, false)).toBe(false);
  });

  it("riconosce Safari (iPhone, Mac) e non Chrome, Edge o Firefox", () => {
    expect(isWebKitSafari("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1")).toBe(true);
    expect(isWebKitSafari("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15")).toBe(true);
    expect(isWebKitSafari("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Mobile Safari/537.36")).toBe(false);
    expect(isWebKitSafari("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36 Edg/129.0")).toBe(false);
  });

  it("niente avviso nell'app se si sta già guardando quell'appartamento (lo annuncia già il suo stream)", () => {
    const n = toNotice(approval, "D");
    expect(toastWanted(n, "/a/apt-001")).toBe(false);
    expect(toastWanted(n, "/a/apt-001/consumi")).toBe(false);
    expect(toastWanted(n, "/a/apt-0012")).toBe(true);
    expect(toastWanted(n, "/impostazioni")).toBe(true);
  });

  it("riconosce i messaggi del service worker alla pagina", () => {
    expect(isPushMessage({ type: "domotica-push", notice: toNotice(approval, "D") })).toBe(true);
    expect(isOpenMessage({ type: "domotica-open", link: "/a/apt-001" })).toBe(true);
    expect(isPushMessage({ type: "altro" })).toBe(false);
    expect(isOpenMessage({ type: "domotica-open" })).toBe(false);
  });
});
