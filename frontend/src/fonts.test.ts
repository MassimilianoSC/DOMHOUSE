// @vitest-environment node
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// P-83, D55: the site sent every user's IP address to Google at each opening (fonts.googleapis.com, fonts.gstatic.com),
// and the privacy notice does not say so. The fonts are now part of the site (@fontsource, OFL-1.1).
const read = (p: string) => readFileSync(resolve(process.cwd(), p), "utf-8"); // vitest runs in frontend/

describe("caratteri ospitati nel sito (P-83, D55)", () => {
  it("la pagina non chiama i server dei caratteri di Google", () => {
    for (const file of ["index.html", "src/index.css"]) {
      expect(read(file)).not.toMatch(/googleapis\.com|gstatic\.com/);
    }
  });

  it("i caratteri arrivano dal sito: Manrope (variabile) e JetBrains Mono importati all'avvio", () => {
    const main = read("src/main.tsx");
    expect(main).toContain('import "@fontsource-variable/manrope"');
    for (const w of [400, 500, 600]) expect(main).toContain(`import "@fontsource/jetbrains-mono/latin-${w}.css"`);
    expect(read("tailwind.config.cjs")).toContain('"Manrope Variable"');
  });

  it("versioni fisse dei pacchetti dei caratteri (approvate dal committente, 1071)", () => {
    const pkg = JSON.parse(read("package.json")) as { dependencies: Record<string, string> };
    expect(pkg.dependencies["@fontsource-variable/manrope"]).toBe("5.3.0");
    expect(pkg.dependencies["@fontsource/jetbrains-mono"]).toBe("5.3.0");
  });
});
