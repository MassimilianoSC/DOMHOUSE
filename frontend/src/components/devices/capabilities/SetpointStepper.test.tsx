import { fireEvent, render, screen } from "@testing-library/react";
import { SetpointStepper } from "./SetpointStepper";

// «−» and «+» always propose a value inside the limits (D-174): the engine refuses anything outside them (422).
function stepper(value: number, min = 16, max = 23) {
  const onChange = vi.fn();
  render(<SetpointStepper value={value} min={min} max={max} disabled={false} onChange={onChange} testId="sp" />);
  return onChange;
}

describe("temperatura: «−» e «+» restano nei limiti (D-174)", () => {
  it("dentro i limiti: mezzo grado per volta", () => {
    const onChange = stepper(20);
    fireEvent.click(screen.getByTestId("sp-inc"));
    fireEvent.click(screen.getByTestId("sp-dec"));
    expect(onChange.mock.calls).toEqual([[20.5], [19.5]]);
  });

  it("sotto il minimo (l'antigelo a 8 °C con minimo 16): «+» porta al minimo, non a 8,5; «−» è disattivato", () => {
    const onChange = stepper(8);
    expect(screen.getByTestId("sp-dec")).toBeDisabled();
    fireEvent.click(screen.getByTestId("sp-inc"));
    expect(onChange).toHaveBeenCalledWith(16);
  });

  it("sopra il massimo: «−» porta al massimo; «+» è disattivato", () => {
    const onChange = stepper(25);
    expect(screen.getByTestId("sp-inc")).toBeDisabled();
    fireEvent.click(screen.getByTestId("sp-dec"));
    expect(onChange).toHaveBeenCalledWith(23);
  });
});
