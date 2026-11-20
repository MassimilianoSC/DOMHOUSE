import { render } from "@testing-library/react";
import { BreakableCode } from "./breakableCode";

// The values to copy into the Shelly (A3) are long codes: on a phone they went to a new line after «lab-» («lab-» /
// «prova.shellyplugmg3-…»). A line may now also break after «/» and «.», where a reader expects it; the text is the
// same, character by character, so «Copia» and a hand copy give the same value.
describe("BreakableCode", () => {
  it("lo stesso testo, con un punto di a capo dopo «/» e «.»", () => {
    const { container } = render(<BreakableCode value="lab-prova/shellyplugmg3-5e6f.x" />);
    expect(container.textContent).toBe("lab-prova/shellyplugmg3-5e6f.x");
    expect(container.querySelectorAll("wbr")).toHaveLength(2);
    expect(container.innerHTML).toBe("lab-prova/<wbr>shellyplugmg3-5e6f.<wbr>x");
  });

  it("senza «/» né «.» non aggiunge niente", () => {
    const { container } = render(<BreakableCode value="mqtt-8883" />);
    expect(container.innerHTML).toBe("mqtt-8883");
  });
});
