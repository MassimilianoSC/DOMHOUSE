import { expect, test, type Page } from "@playwright/test";
import { NO_BROWSER_REASON } from "./environment";

// P-73: on a 360 px phone nothing may stick out to the right, so nobody has to pinch the page to read it (the list of
// the apartments was 418 px wide). Every page of an apartment, the general ones, and the panels of lots 21-25
// (weekly summary with consumption, the assistant's proposal, the preview of the copy, the «Ambiente di prova» band).

test.skip(Boolean(NO_BROWSER_REASON), NO_BROWSER_REASON ?? "");
test.use({ viewport: { width: 360, height: 780 } });

/** The innermost elements whose box goes beyond the screen, outside the containers that scroll on purpose. */
async function overflowing(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const W = document.documentElement.clientWidth;
    const inScroller = (el: Element) => {
      for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) if (/(auto|scroll|hidden)/.test(getComputedStyle(p).overflowX)) return true;
      return false;
    };
    const out: string[] = [];
    for (const el of document.querySelectorAll("body *")) {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height || getComputedStyle(el).position === "fixed") continue;
      if ((r.right > W + 1 || r.left < -1) && !inScroller(el) && ![...el.children].some((c) => c.getBoundingClientRect().right > W + 1)) {
        out.push(`${el.closest("[data-testid]")?.getAttribute("data-testid") ?? el.tagName.toLowerCase()} «${(el.textContent ?? "").trim().slice(0, 40)}» fino a ${Math.round(r.right)} px`);
      }
    }
    if (document.documentElement.scrollWidth > W + 1) out.unshift(`pagina larga ${document.documentElement.scrollWidth} px su ${W}`);
    return out;
  });
}

async function signIn(page: Page, who = /Amministratore demo/) {
  await page.goto("/login");
  await page.getByRole("button", { name: who }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
}

/** The page has its data: a heading, no loading skeleton left, the entry animations over. Never «network idle»: the
 *  pages of an apartment keep the live stream open. */
async function settle(page: Page) {
  await expect(page.locator("main h1").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("main .animate-pulse.bg-muted")).toHaveCount(0, { timeout: 15_000 });
  await page.waitForTimeout(600);
}

async function firstApartment(page: Page): Promise<string> {
  const card = page.locator('[data-testid^="apartment-card-"]').first();
  await expect(card).toBeVisible({ timeout: 15_000 });
  return (await card.getAttribute("data-testid"))!.replace("apartment-card-", "");
}

const APARTMENT_PAGES = ["", "/approvazioni", "/decisioni", "/consumi", "/riepiloghi", "/programmazione", "/regole", "/assistente", "/simulatore"];

test.describe("la misura stessa (D-155): se smette di vedere uno sbordo, questa prova è rossa", () => {
  test("un elemento largo 419 px, come l'elenco degli appartamenti prima della correzione, viene segnalato", async ({ page }) => {
    await signIn(page);
    await page.goto("/impostazioni");
    await settle(page);
    expect(await overflowing(page)).toEqual([]);
    await page.evaluate(() => {
      const wide = document.createElement("div");
      wide.setAttribute("data-testid", "sbordo-di-prova");
      wide.style.width = "419px";
      wide.style.height = "20px";
      document.querySelector("main")!.appendChild(wide);
    });
    const found = await overflowing(page);
    expect(found[0]).toMatch(/^pagina larga \d+ px su 360$/);
    expect(found.some((line) => line.startsWith("sbordo-di-prova"))).toBe(true);
  });
});

test.describe("telefono a 360 px: niente fuori dallo schermo (P-73)", () => {
  test("elenco degli appartamenti, la prima pagina dopo l'accesso", async ({ page }) => {
    await signIn(page);
    await firstApartment(page);
    await settle(page);
    expect(await overflowing(page)).toEqual([]);
  });

  for (const sub of APARTMENT_PAGES) {
    test(`appartamento${sub || " (panoramica)"}`, async ({ page }) => {
      await signIn(page);
      await page.goto(`/a/${await firstApartment(page)}${sub}`);
      await settle(page);
      expect(await overflowing(page)).toEqual([]);
    });
  }

  for (const path of ["/admin", "/impostazioni"]) {
    test(`pagina ${path}`, async ({ page }) => {
      await signIn(page);
      await page.goto(path);
      await settle(page);
      expect(await overflowing(page)).toEqual([]);
    });
  }

  test("organizzazioni, come gestore della piattaforma", async ({ page }) => {
    await signIn(page, /Gestore della piattaforma/);
    await page.goto("/organizzazioni");
    await settle(page);
    expect(await overflowing(page)).toEqual([]);
  });

  test("riepilogo della settimana con i consumi, e la fascia «Ambiente di prova»", async ({ page }) => {
    const week = { week: "2026-W42", from: "2026-10-11T22:00:00.000Z", to: "2026-10-18T22:00:00.000Z", notable: true, items: 2 };
    const device = "Misuratore climatizzatore soggiorno principale";
    await page.route("**/app/apartments/*/summaries", (r) => r.fulfill({ json: [week] }));
    await page.route("**/app/apartments/*/summaries/2026-W42", (r) => r.fulfill({ json: {
      apartment_id: "x", ...week, generated_at: "2026-10-19T06:05:00.000Z",
      energy: { available: true, occupied: { nights: 3, kwh_per_night: 16, median_before: 10, status: "anomalous" }, vacant: { nights: 4, kwh_per_night: 2, median_before: null, status: "not_comparable" },
        devices: [{ device_id: "m1", label: device, occupied: { nights: 3, kwh_per_night: 8, median_before: 5, status: "anomalous" }, vacant: { nights: 0, kwh_per_night: null, median_before: 1, status: "no_nights" } }] },
      offline: { now: [], episodes: [] }, approvals_expired: [], windows: [],
      items: ["Consumi alti per notte con ospiti: 16 kWh contro una mediana di 10 kWh nelle 4 settimane prima.", `${device}: consumi alti per notte con ospiti, 8 kWh contro 5 kWh.`], notable: true,
    } }));
    await page.route("**/app/me", async (r) => {
      const res = await r.fetch();
      const me = await res.json();
      await r.fulfill({ response: res, json: { ...me, env: { ...me.env, app_env: "staging" } } });
    });
    await signIn(page);
    await page.goto(`/a/${await firstApartment(page)}/riepiloghi/2026-W42`);
    await expect(page.getByTestId("summary-energy")).toBeVisible();
    await expect(page.getByTestId("env-banner-mobile")).toBeVisible();
    await settle(page);
    expect(await overflowing(page)).toEqual([]);
  });

  test("regole: proposta dell'assistente e anteprima della copia", async ({ page }) => {
    await signIn(page);
    await page.goto(`/a/${await firstApartment(page)}/regole`);
    await settle(page);
    await page.getByTestId("rule-proposal-text").fill("finestra 10 minuti");
    await page.getByTestId("rule-proposal-ask").click();
    await expect(page.getByTestId("rule-proposal-result").or(page.getByTestId("rule-proposal-none"))).toBeVisible();
    expect(await overflowing(page)).toEqual([]);
    await page.getByTestId("rules-copy-all").click();
    await page.getByTestId("rules-copy-preview").click();
    await expect(page.getByTestId("rules-copy-preview-result")).toBeVisible();
    expect(await overflowing(page)).toEqual([]);
  });
});
