import { expect, test } from "@playwright/test";
import { NO_BROWSER_REASON } from "./environment";

// E-29: an app start that gets no answer ends with a message and a way out, not with a loading state for ever. In a real
// browser, with the real 15 s and the real reload, on a 360 px phone.

test.skip(Boolean(NO_BROWSER_REASON), NO_BROWSER_REASON ?? "");
test.use({ viewport: { width: 360, height: 780 } });

test("il profilo non risponde: dopo il tempo massimo il messaggio; Ricarica riporta dentro", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: /Amministratore demo/ }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));

  let blocked = true;
  await page.route("**/app/me", (route) => (blocked ? undefined : route.continue())); // blocked: never answered
  await page.goto("/impostazioni");
  await expect(page.getByTestId("page-problem")).toBeVisible({ timeout: 20_000 });
  const widths = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
  expect(widths[0]).toBeLessThanOrEqual(widths[1] + 1);

  blocked = false;
  await page.getByTestId("page-problem-reload").click();
  await expect(page.locator("main h1").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("page-problem")).toHaveCount(0);
});

// D-211: no network or a 5xx is not the end of the session: the same message, with what the app knows, instead of the
// sign-in page; when the network comes back the page reopens by itself.
async function signIn(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.getByRole("button", { name: /Amministratore demo/ }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
}

test("il server risponde 503: «Il servizio non risponde», non la pagina di accesso", async ({ page }) => {
  await signIn(page);
  await page.route("**/app/me", (route) => route.fulfill({ status: 503, contentType: "application/json", body: '{"error":"unavailable","message":"Servizio non disponibile"}' }));
  await page.goto("/impostazioni");
  await expect(page.getByTestId("page-problem")).toHaveAttribute("data-kind", "server");
  await expect(page.getByRole("heading", { name: "Il servizio non risponde, riprova fra poco" })).toBeVisible();
  expect(new URL(page.url()).pathname).toBe("/impostazioni");
});

test("la rete cade e torna: «Sei senza connessione», poi la pagina si riapre da sola, senza premere nulla", async ({ page, context }) => {
  await signIn(page);
  let down = true;
  await page.route("**/app/me", (route) => (down ? route.abort("internetdisconnected") : route.continue()));
  await page.goto("/impostazioni");
  // the browser still says it is online: the prudent text, since the network may be missing all the same
  await expect(page.getByTestId("page-problem")).toHaveAttribute("data-kind", "unknown");

  await context.setOffline(true);
  await expect(page.getByTestId("page-problem")).toHaveAttribute("data-kind", "offline");
  await expect(page.getByRole("heading", { name: "Sei senza connessione" })).toBeVisible();

  down = false;
  await context.setOffline(false);
  await expect(page.locator("main h1").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("page-problem")).toHaveCount(0);
  expect(new URL(page.url()).pathname).toBe("/impostazioni");
});
