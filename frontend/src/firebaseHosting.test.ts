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

// P-92 / E-29: every opening takes index.html from the network. The service worker only does web push (src/sw.test.ts
// runs it). Review P6: Firebase matches each header rule against the address asked for, not the file the rewrite
// serves, so what counts for an opening is the rule of "/" and of every page of the app; "/index.html" is never asked.
import viteConfig from "../vite.config.ts?raw";

type Rule = { source: string; headers: { key: string; value: string }[] };

/** The globs of firebase.json, by hand: an unknown form fails the test, so a new rule is looked at here. */
function matches(source: string, path: string): boolean {
  if (source === "**") return true;
  if (source === "**/!(*.*)") return !(path.split("/").pop() ?? "").includes(".");
  if (source.endsWith("/**")) return path.startsWith(source.slice(0, -2));
  if (!/[*?!(){}[\]]/.test(source)) return path === source;
  throw new Error(`regola non prevista dalla prova: ${source}`);
}

describe("P-92: index.html sempre dalla rete", () => {
  const rules = hosting[0].headers as Rule[];
  const cacheFor = (path: string) =>
    rules.filter((r) => matches(r.source, path)).flatMap((r) => r.headers.filter((h) => h.key === "Cache-Control").map((h) => h.value));

  it.each(["/", "/login", "/impostazioni", "/organizzazioni", "/a/apt-001/regole", "/a/lab-01/panoramica"])(
    "apertura di %s: solo no-cache, la pagina arriva sempre dalla rete",
    (path) => {
      expect(cacheFor(path)).toEqual(["no-cache"]);
    },
  );

  it("sw.js no-cache; i file di /assets/ un anno immutable, come prima", () => {
    expect(cacheFor("/sw.js")).toEqual(["no-cache"]);
    expect(cacheFor("/assets/index-AbC123.js")).toEqual(["public, max-age=31536000, immutable"]);
  });

  it("al worker non si inietta più l'elenco della copia del sito", () => {
    expect(viteConfig).toMatch(/injectionPoint:\s*undefined/);
  });
});
