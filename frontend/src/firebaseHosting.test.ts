import firebaseJson from "../firebase.json?raw";

// P-67 (D-136): firebase.json has one Hosting configuration per target, prod and staging, otherwise identical, so
// the test site never differs from production in headers, rewrites or caching. deploy.sh maps each target to its site.
const hosting = JSON.parse(firebaseJson).hosting as Record<string, unknown>[];

describe("firebase.json: un sito per ambiente", () => {
  it("due configurazioni, target prod e staging", () => {
    expect(Array.isArray(hosting)).toBe(true);
    expect(hosting.map((h) => h.target)).toEqual(["prod", "staging"]);
  });

  it("identiche a parte il target, con le intestazioni di sicurezza e la pagina unica", () => {
    const [prod, staging] = hosting.map(({ target: _target, ...rest }) => rest);
    expect(staging).toEqual(prod);
    expect(prod.public).toBe("dist");
    expect(prod.rewrites).toEqual([{ source: "**", destination: "/index.html" }]);
    expect(JSON.stringify(prod.headers)).toContain("X-Frame-Options");
  });
});

// P-92 / E-29: every opening takes index.html from the network. The service worker only does web push: no fetch
// handler (Chrome no longer starts it for navigations, so a stuck worker cannot hold the site, E-29) and no copy of
// the site in Cache Storage. The browser keeps the files under /assets/ (named by content) for a year, as before.
import swSource from "./sw.ts?raw";
import viteConfig from "../vite.config.ts?raw";

describe("P-92: index.html sempre dalla rete", () => {
  const headers = (hosting[0].headers as { source: string; headers: { key: string; value: string }[] }[]);
  const cacheOf = (source: string) => headers.find((h) => h.source === source)?.headers.find((x) => x.key === "Cache-Control")?.value;

  it("intestazioni di oggi: index.html e sw.js no-cache, /assets/** un anno immutable", () => {
    expect(cacheOf("/index.html")).toBe("no-cache");
    expect(cacheOf("/sw.js")).toBe("no-cache");
    expect(cacheOf("/assets/**")).toBe("public, max-age=31536000, immutable");
  });

  it("il service worker non risponde alle richieste e non tiene il sito in cache", () => {
    expect(swSource).not.toMatch(/addEventListener\(\s*["']fetch["']/);
    expect(swSource).not.toMatch(/workbox-precaching|workbox-routing|__WB_MANIFEST|registerRoute/);
    expect(viteConfig).toMatch(/injectionPoint:\s*undefined/);
  });

  it("le copie lasciate dai worker di prima si cancellano", () => {
    expect(swSource).toMatch(/addEventListener\(\s*["']activate["']/);
    expect(swSource).toMatch(/caches\.delete/);
  });

  it("le notifiche restano: push e clic sulla notifica", () => {
    expect(swSource).toMatch(/addEventListener\(\s*["']push["']/);
    expect(swSource).toMatch(/addEventListener\(\s*["']notificationclick["']/);
  });
});
