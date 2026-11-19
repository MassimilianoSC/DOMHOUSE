/**
 * The first wait for a page that the app loads on demand (lazyPage, App.tsx). Testing Library waits 1 s by default; in
 * a full run the dynamic import of the page can take longer, and «Unable to find …-header» came from that, not from the
 * page (PlatformAccess.test.tsx, 19 November). Only the first appearance waits longer: what the tests check is the same.
 */
export const LAZY_PAGE = { timeout: 10_000 };
