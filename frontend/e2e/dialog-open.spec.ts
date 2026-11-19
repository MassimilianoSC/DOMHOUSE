import { expect, test, type Page } from "@playwright/test";
import { NO_BROWSER_REASON } from "./environment";
import { signIn } from "./measure";

// D-198 (19 November): every window of the site (DialogContent in src/components/ui/primitives.tsx) is centred with
// translate(-50%, -50%), and its opening animation replaced that transform: for ~150 ms the window started from the
// lower right and slid in, on a 360 px phone partly off the screen. Here the animation is stopped at its start and in
// its middle and the window must already be where it ends: inside the screen, centred.

test.skip(Boolean(NO_BROWSER_REASON), NO_BROWSER_REASON ?? "");
test.use({ viewport: { width: 360, height: 780 } });

/** The window's box with its animations held at `fraction` of their duration (0 = the first frame). */
async function boxAt(page: Page, testId: string, fraction: number) {
  return page.evaluate(([id, f]) => {
    const el = document.querySelector(`[data-testid="${id}"]`) as HTMLElement;
    for (const a of el.getAnimations()) {
      a.pause();
      const d = Number(a.effect?.getComputedTiming().duration ?? 0);
      a.currentTime = d * (f as number);
    }
    const r = el.getBoundingClientRect();
    return { left: r.left, right: r.right, center: (r.left + r.right) / 2, width: document.documentElement.clientWidth };
  }, [testId, fraction] as const);
}

test("una finestra che si apre parte già al suo posto, dentro lo schermo", async ({ page }) => {
  await signIn(page);
  const card = page.locator('[data-testid^="apartment-card-"]').first();
  await expect(card).toBeVisible({ timeout: 15_000 });
  const apt = (await card.getAttribute("data-testid"))!.replace("apartment-card-", "");
  await page.goto(`/a/${apt}/credenziali`);
  await page.getByTestId("credentials-register-btn").click({ timeout: 15_000 });
  await page.getByTestId("credential-register-dialog").waitFor({ state: "attached" });
  for (const fraction of [0, 0.5]) {
    const box = await boxAt(page, "credential-register-dialog", fraction);
    expect(box.left, `inizio a ${fraction}`).toBeGreaterThanOrEqual(0);
    expect(box.right, `fine a ${fraction}`).toBeLessThanOrEqual(box.width + 1);
    expect(Math.abs(box.center - box.width / 2), `centro a ${fraction}`).toBeLessThanOrEqual(2);
  }
});
