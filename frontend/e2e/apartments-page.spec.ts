import { expect, test, type Page } from "@playwright/test";
import { NO_BROWSER_REASON } from "./environment";
import { overflowing, settle, signIn } from "./measure";

// The apartments page of PR #19 (Luca), retouched after the merge (1187): on a phone no text under 12 px in the band
// with the photo (the consumption box was at 9 px, the thought of the day at 11.2 px), the text on the photo not cut off
// by its rounded frame, and in the tiles of each apartment no word split in two («Occupazion/e» at 1280 px).

test.skip(Boolean(NO_BROWSER_REASON), NO_BROWSER_REASON ?? "");

/** The texts of the band with the photo smaller than 12 px, as «size: text». */
async function smallTexts(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const out: string[] = [];
    const band = document.querySelector('[data-testid="apartments-header"]')!;
    const walker = document.createTreeWalker(band, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const text = (n.textContent ?? "").trim();
      const el = n.parentElement!;
      if (!text || !el.getClientRects().length) continue;
      const size = parseFloat(getComputedStyle(el).fontSize);
      if (size < 12) out.push(`${size}px: ${text.slice(0, 40)}`);
    }
    return out;
  });
}

/** Words of the tiles' labels drawn on two lines (a Range over a word with more than one box). */
async function splitWords(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const out: string[] = [];
    for (const tile of document.querySelectorAll('[data-testid^="apartment-mode-"], [data-testid^="apartment-occupancy-"], [data-testid^="apartment-kwh-"], [data-testid^="apartment-checkin-"], [data-testid^="apartment-checkout-"]')) {
      const walker = document.createTreeWalker(tile, NodeFilter.SHOW_TEXT);
      for (let n = walker.nextNode(); n; n = walker.nextNode()) {
        const text = n.textContent ?? "";
        for (const m of text.matchAll(/\S+/g)) {
          const r = document.createRange();
          r.setStart(n, m.index!);
          r.setEnd(n, m.index! + m[0].length);
          const lines = new Set([...r.getClientRects()].map((b) => Math.round(b.top)));
          if (lines.size > 1) out.push(`${tile.getAttribute("data-testid")}: «${m[0]}»`);
        }
      }
    }
    return out;
  });
}

/** The thought of the day and the title inside the photo, not cut off by its frame. */
async function copyInsidePhoto(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const photo = document.querySelector(".apartments-hero-photo")!.getBoundingClientRect();
    const copy = document.querySelector(".apartments-hero-copy-content")!.getBoundingClientRect();
    return copy.top >= photo.top - 1 && copy.bottom <= photo.bottom + 1 && copy.right <= photo.right + 1;
  });
}

/** The consumption box either inside the photo or below it, never across its lower edge onto the cards. */
async function energyBoxFits(page: Page): Promise<string | null> {
  return page.evaluate(() => {
    const photo = document.querySelector(".apartments-hero-photo")!.getBoundingClientRect();
    const box = document.querySelector('[data-testid="home-energy-summary"]')!.getBoundingClientRect();
    if (box.top >= photo.bottom - 1) return null; // below the photo
    return box.bottom <= photo.bottom + 1 ? null : `il riquadro del consumo esce dalla foto: ${Math.round(box.bottom)} px contro ${Math.round(photo.bottom)}`;
  });
}

for (const width of [360, 390, 1280]) {
  test(`elenco degli appartamenti a ${width} px: testi da 12 px in su, niente tagliato, nessuna parola spezzata`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await signIn(page);
    await settle(page);
    await expect(page.getByTestId("home-energy-summary")).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[data-testid^="apartment-card-"]').first()).toBeVisible();
    expect(await smallTexts(page)).toEqual([]);
    expect(await copyInsidePhoto(page)).toBe(true);
    expect(await energyBoxFits(page)).toBeNull();
    expect(await splitWords(page)).toEqual([]);
    expect(await overflowing(page)).toEqual([]);
  });
}
