// @vitest-environment node
import { deliverInApp, isOpenMessage, isPushMessage, isWebKitSafari, notificationOptions, safeLink, toNotice, toastWanted } from "./pushPayload";

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
      kind: "approval",
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

describe("push: prenotazioni (D-123)", () => {
  it("kind «booking»: notifica con il suo titolo, apre le decisioni dell'appartamento, raggruppata per decisione", () => {
    const booking = { data: { kind: "booking", title: "Milano Centro: prenotazione annullata, appartamento rimesso a vuoto", body: "La prenotazione RES-7 è stata annullata dopo il pre-arrivo", link: "/a/apt-001/decisioni", tag: "booking:d-42", apartment_id: "apt-001" } };
    expect(toNotice(booking, "DOMHOUSE")).toEqual({
      title: "Milano Centro: prenotazione annullata, appartamento rimesso a vuoto",
      body: "La prenotazione RES-7 è stata annullata dopo il pre-arrivo",
      link: "/a/apt-001/decisioni",
      tag: "booking:d-42",
      apartmentId: "apt-001",
      kind: "booking",
    });
  });
});

describe("push: riepilogo settimanale (D-150)", () => {
  it("kind «summary»: apre la pagina di quella settimana, raggruppata per appartamento e settimana", () => {
    const summary = { data: { kind: "summary", title: "Milano Centro: riepilogo della settimana", body: "Consumi alti per notte con ospiti", link: "/a/apt-001/riepiloghi/2026-W42", tag: "summary:apt-001:2026-W42", apartment_id: "apt-001" } };
    expect(toNotice(summary, "DOMHOUSE")).toEqual({
      title: "Milano Centro: riepilogo della settimana",
      body: "Consumi alti per notte con ospiti",
      link: "/a/apt-001/riepiloghi/2026-W42",
      tag: "summary:apt-001:2026-W42",
      apartmentId: "apt-001",
      kind: "summary",
    });
  });
});

describe("push: antigelo non attivo (lotto 30)", () => {
  it("kind «frost_inactive»: apre le Decisioni dell'appartamento, raggruppata per caldaia", () => {
    const frost = { data: { kind: "frost_inactive", title: "Milano Centro: antigelo non attivo", body: "Caldaia: sensore di temperatura mancante, antigelo non attivo (nessun sensore di temperatura collegato)", link: "/a/apt-001/decisioni", tag: "frost:apt-001:dev-caldaia", apartment_id: "apt-001", device_id: "dev-caldaia" } };
    expect(toNotice(frost, "DOMHOUSE")).toEqual({
      title: "Milano Centro: antigelo non attivo",
      body: "Caldaia: sensore di temperatura mancante, antigelo non attivo (nessun sensore di temperatura collegato)",
      link: "/a/apt-001/decisioni",
      tag: "frost:apt-001:dev-caldaia",
      apartmentId: "apt-001",
      kind: "frost_inactive",
    });
  });
});

describe("push: revisione P-83", () => {
  const on = (kind: string) => toNotice({ data: { ...approval.data, kind } }, "D");

  it("D24: il tipo del messaggio arriva fino alla pagina", () => {
    expect(toNotice(approval, "D").kind).toBe("approval");
  });

  it("D24: sulla pagina dell'appartamento si tace solo per ciò che lo stream annuncia (approvazione, dispositivo offline)", () => {
    expect(toastWanted(on("approval"), "/a/apt-001")).toBe(false);
    expect(toastWanted(on("device_offline"), "/a/apt-001/dispositivi")).toBe(false);
    for (const kind of ["frost_inactive", "schedule_failed", "booking", "summary", "instance_down"]) {
      expect(toastWanted(on(kind), "/a/apt-001")).toBe(true);
    }
    expect(toastWanted({ ...on("approval"), kind: undefined }, "/a/apt-001")).toBe(true); // tipo sconosciuto: meglio due che nessuno
  });

  it("D49: una notifica con lo stesso tag della precedente la sostituisce E suona di nuovo", () => {
    const n = toNotice(approval, "D");
    expect(notificationOptions(n)).toEqual({ body: n.body, icon: "/icons/icon-192.png", tag: "approval:ap-7", renotify: true, data: { link: n.link } });
    expect(notificationOptions(toNotice(null, "D"))).not.toHaveProperty("renotify"); // senza tag il browser rifiuta renotify
  });

  it("D78: caratteri di controllo nel link (tab, a capo) non portano fuori dall'app", () => {
    for (const bad of ["/\t/evil.example", "/\n/evil.example", "/\r/evil.example", "/\u0000x", "/a\u007f"]) expect(safeLink(bad)).toBe("/");
    expect(safeLink("/a/apt-001/decisioni")).toBe("/a/apt-001/decisioni");
  });
});
