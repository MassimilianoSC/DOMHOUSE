import { expect, test, type Page } from "@playwright/test";
import { NO_BROWSER_REASON } from "./environment";
import { overflowing, settle, signIn } from "./measure";

// A2, a new apartment created from the app (docs/proposta-a2-sito.md §2-§4) in a real browser: the organization's card
// with the red line and «Vedi», the rows in their three states and the form with the limit reached, at phone widths,
// nothing sticking out. The development server has no agent (creazione_disponibile false, o1 cb3ee25): the answers of
// the creation are given in the browser. Invented names and codes only.

test.skip(Boolean(NO_BROWSER_REASON), NO_BROWSER_REASON ?? "");

const creazione = (over: object) => ({
  stato: "in_preparazione", passo: "motore", version: 3, porta: 8153, op: null, codice: null, messaggio: null, fatti: ["id", "porta", "segreti"], updated_at: "2026-11-19T16:21:00Z", updated_by: "Giulia Rossi", ...over,
});
const row = (apartment_id: string, name: string, c: object | null) => ({
  apartment_id, name, instance_url: c ? "" : "http://10.198.0.2:8151", port: null, enabled: true, timezone: "Europe/Rome", italianway_id: null, simulated: false, last_check: null, creazione: c,
});
const ROWS = [
  row("lab-corte", "Monolocale Corte", creazione({ stato: "pronto", passo: "collegamento" })),
  row("lab-giardino-panoramico-sul-lago", "Trilocale Giardino panoramico sul lago", creazione({})),
  row("lab-ponte", "Bilocale Ponte", creazione({
    stato: "non_creato", passo: "motore", porta: 8152, version: 7, updated_at: "2026-11-19T16:05:00Z", codice: "motore_non_sano", messaggio: "Motore non sano",
    op: { op_id: "3f9c2a71-0000-4000-8000-000000000001", operazione: "crea_motore", stato: "fallito", codice: "motore_non_sano", messaggio: "Motore non sano" },
  })),
  row("lab-via", "Bilocale Via", creazione({ stato: "annullamento_in_corso" })),
];

/** Staging with the agent, one organization with a creation stopped and one on its way, its apartments as above. */
async function prepare(page: Page, used = 2) {
  await page.route("**/app/me", async (r) => {
    const res = await r.fetch();
    const me = await res.json();
    await r.fulfill({ response: res, json: { ...me, env: { ...me.env, app_env: "staging", creazione_disponibile: true } } });
  });
  await page.route("**/app/platform/tenants", async (r) => {
    if (r.request().method() !== "GET") return r.continue();
    const res = await r.fetch();
    const list = (await res.json()) as object[];
    await r.fulfill({ response: res, json: list.map((tn, i) => ({ ...tn, appartamenti_non_creati: i === 0 ? 1 : 0, appartamenti_in_preparazione: 1 })) });
  });
  await page.route("**/app/platform/tenants/*", async (r) => {
    if (r.request().method() !== "GET") return r.continue();
    const res = await r.fetch();
    const tn = await res.json();
    await r.fulfill({ response: res, json: { ...tn, creazioni_ultima_ora: { usate: used, limite: 5, libera_dal: used >= 5 ? "2026-11-20T16:42:00Z" : null } } });
  });
  await page.route("**/app/platform/tenants/*/apartments", async (r) => {
    if (r.request().method() !== "GET") return r.continue();
    const res = await r.fetch();
    const list = (await res.json()) as object[];
    await r.fulfill({ response: res, json: [...list, ...ROWS] });
  });
  await page.route("**/app/platform/apartments/*/device-credentials", (r) => r.fulfill({ json: { items: [] } }));
  await signIn(page, /Gestore della piattaforma/);
  await page.goto("/organizzazioni");
  await settle(page);
}

const firstTenant = (page: Page) => page.locator('[data-testid^="tenant-creations-see-"]').first();

for (const width of [360, 390, 430]) {
  test(`a ${width} px: la riga rossa con «Vedi», le righe nei tre stati, niente fuori dallo schermo`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    await prepare(page);
    await expect(firstTenant(page)).toBeVisible();
    expect(await overflowing(page)).toEqual([]);
    await firstTenant(page).click();
    const stopped = page.getByTestId("platform-apt-lab-ponte");
    await expect(stopped).toBeVisible();
    await expect(stopped).toBeFocused();
    await expect(page.getByTestId("creation-what-lab-ponte")).toContainText("Il sistema domotico non è partito");
    await expect(page.getByTestId("creation-steps-lab-giardino-panoramico-sul-lago")).toBeVisible();
    await expect(page.getByTestId("creation-state-lab-via")).toHaveText(/Annullamento in corso/);
    await expect(page.getByTestId("creation-ready-lab-corte")).toBeVisible();
    // the stopped creation first, then the ones on their way
    const order = await page.locator("li[data-creation]").evaluateAll((els) => els.map((e) => e.getAttribute("data-creation")));
    expect(order.slice(0, 3)).toEqual(["non_creato", "in_preparazione", "annullamento_in_corso"]);
    expect(await overflowing(page)).toEqual([]);

    // the confirmation of «Annulla creazione», inside the screen
    await page.getByTestId("creation-cancel-lab-ponte").click();
    const dlg = page.getByTestId("creation-cancel-dialog");
    await expect(dlg).toContainText("L'ID lab-ponte non si potrà più usare");
    const box = await dlg.boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(width + 1);
    await page.getByTestId("creation-cancel-back").click();
    await expect(dlg).toHaveCount(0);
  });

  test(`a ${width} px: il modulo con il limite raggiunto, il riquadro giallo e «Crea» spento`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    await prepare(page, 5);
    await page.locator('[data-testid^="tenant-apartments-btn-"]').first().click();
    await page.locator('[data-testid^="platform-apt-new-btn-"]').first().click();
    const dlg = page.getByTestId("new-apt-dialog");
    await expect(page.getByTestId("new-apt-limit")).toHaveAttribute("data-reached", "true");
    await expect(page.getByTestId("new-apt-limit")).toContainText("Potrai crearne un altro");
    await page.getByTestId("apt-form-apartment_id").fill("lab-prova");
    await page.getByTestId("apt-form-name").fill("Laboratorio di prova");
    await expect(page.getByTestId("new-apt-save")).toBeDisabled();
    await page.waitForFunction(() => document.querySelector('[data-testid="new-apt-dialog"]')?.getAnimations().every((a) => a.playState === "finished") ?? false);
    for (const id of ["new-apt-dialog", "new-apt-limit", "apt-form-apartment_id", "new-apt-save"]) {
      const b = await page.getByTestId(id).boundingBox();
      expect(b, id).not.toBeNull();
      expect(b!.x, id).toBeGreaterThanOrEqual(0);
      expect(b!.x + b!.width, id).toBeLessThanOrEqual(width + 1);
    }
    await expect(dlg).toBeVisible();
  });
}

test("sul server di sviluppo, senza agente: «Nuovo appartamento» spento con la sua riga", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await signIn(page, /Gestore della piattaforma/);
  await page.goto("/organizzazioni");
  await settle(page);
  await page.locator('[data-testid^="tenant-apartments-btn-"]').first().click();
  await expect(page.locator('[data-testid^="platform-apt-new-btn-"]').first()).toBeDisabled();
  await expect(page.locator('[data-testid^="platform-apt-new-unavailable-"]').first()).toContainText("Non disponibile in questo ambiente");
  expect(await overflowing(page)).toEqual([]);
});
