import { expect, type Page } from "@playwright/test";

// Shared by the checks at phone width (phone-width.spec.ts, credentials.spec.ts).

/** The innermost elements whose box goes beyond the screen, outside the containers that scroll on purpose. */
export async function overflowing(page: Page): Promise<string[]> {
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

export async function signIn(page: Page, who = /Amministratore demo/) {
  await page.goto("/login");
  await page.getByRole("button", { name: who }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
}

/** The page has its data: a heading, no loading skeleton left, the entry animations over. Never «network idle»: the
 *  pages of an apartment keep the live stream open. */
export async function settle(page: Page) {
  await expect(page.locator("main h1").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("main .animate-pulse.bg-muted")).toHaveCount(0, { timeout: 15_000 });
  await page.waitForTimeout(600);
}
