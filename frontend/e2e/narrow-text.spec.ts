import { expect, test, type Page } from "@playwright/test";
import { NO_BROWSER_REASON } from "./environment";

// Lot 35: in production, on a large phone, the «Rendiconto in Excel» card of Consumi put its title and caption one
// word per line. In a wrapping row a text column with flex-1 alone (zero basis) never makes the controls next to it go
// to the next line: between 412 and 430 px the select and the button fit on the same line and the text got 4–22 px.
// Here, at the widths of the large phones, no text of three words or more may be squeezed into a column that narrow.

test.skip(Boolean(NO_BROWSER_REASON), NO_BROWSER_REASON ?? "");

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByRole("button", { name: /Amministratore demo/ }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
}

/** The page has its data: a heading and no loading placeholder left. */
async function settle(page: Page) {
  await expect(page.locator("main h1").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("main .animate-pulse.bg-muted")).toHaveCount(0, { timeout: 15_000 });
  await page.waitForTimeout(400);
}

/** Texts of three words or more laid out in a column narrower than 80 px: one word per line. */
async function squeezed(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const out: string[] = [];
    for (const el of document.querySelectorAll<HTMLElement>("main h1, main h2, main h3, main p, main span, main label")) {
      const words = (el.textContent ?? "").trim().split(/\s+/).filter(Boolean);
      const r = el.getBoundingClientRect();
      if (words.length >= 3 && r.width > 0 && r.width < 80 && getComputedStyle(el).display !== "inline") {
        out.push(`${el.closest("[data-testid]")?.getAttribute("data-testid") ?? el.tagName.toLowerCase()} «${words.slice(0, 5).join(" ")}» largo ${Math.round(r.width)} px`);
      }
    }
    return out;
  });
}

for (const width of [375, 390, 400, 412, 430]) {
  test.describe(`telefono a ${width} px: nessun testo una parola per riga`, () => {
    test.use({ viewport: { width, height: 900 } });

    test("Consumi, con «Rendiconto in Excel»", async ({ page }) => {
      await signIn(page);
      await settle(page);
      const card = page.locator('[data-testid^="apartment-card-"]').first();
      const apt = (await card.getAttribute("data-testid"))!.replace("apartment-card-", "");
      await page.goto(`/a/${apt}/consumi`);
      await settle(page);
      const exp = page.getByTestId("energy-export");
      await expect(exp).toBeVisible();
      // the title on one line, the caption at least as wide as half the card
      const box = await exp.evaluate((el) => {
        const text = el.firstElementChild as HTMLElement;
        return { text: text.getBoundingClientRect().width, card: el.getBoundingClientRect().width, title: text.querySelector("h2")!.getBoundingClientRect().height };
      });
      expect(box.text).toBeGreaterThan(box.card / 2);
      expect(box.title).toBeLessThan(40);
      expect(await squeezed(page)).toEqual([]);
    });

    for (const path of ["/admin", "/impostazioni"]) {
      test(`pagina ${path}`, async ({ page }) => {
        await signIn(page);
        await page.goto(path);
        await settle(page);
        expect(await squeezed(page)).toEqual([]);
      });
    }
  });
}
