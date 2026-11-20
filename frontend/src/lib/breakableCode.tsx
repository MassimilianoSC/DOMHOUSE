import { Fragment } from "react";

/**
 * A long code (topic prefix, client id, user) that may go to a new line after «/» and «.» too, where a reader expects
 * it, not only after a «-» («lab-» / «prova.shelly…»). The text stays the same character by character: <wbr> adds
 * nothing to what is selected or copied.
 */
export function BreakableCode({ value }: { value: string }) {
  const parts = value.split(/(?<=[/.])/);
  return (
    <>
      {parts.map((part, i) => (
        <Fragment key={i}>
          {i > 0 && <wbr />}
          {part}
        </Fragment>
      ))}
    </>
  );
}
