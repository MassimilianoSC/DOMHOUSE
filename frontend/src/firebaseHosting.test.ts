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
