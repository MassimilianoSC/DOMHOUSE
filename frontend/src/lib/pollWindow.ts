/**
 * How long a page keeps reading a list again while orders are on its way (A2 §3.3, A3 §3). `signature` names what is
 * in progress (for example «id:state:version» of each item, "" for nothing): the window opens when it changes and stays
 * shut once `maxMs` is over for the same signature, however many times it is asked. React Query asks again after every
 * reading and every render: a window that restarted when it closed would read for ever.
 */
export function pollWindow(maxMs: number): (signature: string, now: number) => boolean {
  let current = "";
  let start = 0;
  return (signature, now) => {
    if (signature !== current) {
      current = signature;
      start = now;
    }
    return signature !== "" && now - start < maxMs;
  };
}
