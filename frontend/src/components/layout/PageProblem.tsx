import { Component, useEffect, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { browser } from "@/lib/lazyPage";

/** Why the profile could not be read (D-211): no answer at all (no network, or none in time), or the server answered 5xx. */
export type ProblemCause = "network" | "server";

/** After the network comes back, a moment before reloading, so the connection is really up when the page asks again. */
export const ONLINE_RELOAD_DELAY_MS = 1_500;

/**
 * The device says it is offline. `navigator.onLine` false is reliable (no network interface up); true is not (a Wi-Fi
 * without internet still says true), so it is never taken as proof that the network is there.
 */
function useOffline() {
  const [offline, setOffline] = useState(() => navigator.onLine === false);
  useEffect(() => {
    const on = () => setOffline(false);
    const off = () => setOffline(true);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);
  return offline;
}

/** D-211: when the network comes back, the page reloads by itself. The browser says «online» only on a change from
 *  offline, so a server that stays silent cannot make the page reload in a loop. */
function useReloadWhenOnline() {
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const back = () => {
      clearTimeout(timer);
      timer = setTimeout(() => browser.reload(), ONLINE_RELOAD_DELAY_MS);
    };
    const gone = () => clearTimeout(timer);
    window.addEventListener("online", back);
    window.addEventListener("offline", gone);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("online", back);
      window.removeEventListener("offline", gone);
    };
  }, []);
}

/**
 * E-29, D-211: what the person sees instead of an endless loading state, a white page or the sign-in page, with the one
 * thing they can do. The text says what the app knows for sure: the device is offline; the server answered with an
 * error; otherwise (no answer with the device online, a start that never ends, an error while drawing) the prudent one.
 */
export function PageProblem({ cause }: { cause?: ProblemCause }) {
  const offline = useOffline();
  useReloadWhenOnline();
  const kind = offline ? "offline" : cause === "server" ? "server" : "unknown";
  const [title, hint] = {
    offline: [t("errors.offline"), t("errors.offlineHint")],
    server: [t("errors.serverDown"), t("errors.serverDownHint")],
    unknown: [t("errors.pageProblem"), t("errors.pageProblemHint")],
  }[kind];
  return (
    <div className="flex min-h-screen items-center justify-center p-5" role="alert" data-testid="page-problem" data-kind={kind}>
      <Card className="w-full max-w-md p-5 sm:p-8">
        <h1 className="text-2xl font-bold">{title}</h1>
        <p className="mb-6 mt-1 text-sm text-muted-foreground">{hint}</p>
        <Button onClick={() => browser.reload()} data-testid="page-problem-reload">{t("errors.reload")}</Button>
      </Card>
    </div>
  );
}

/** Around the whole app: an error while drawing a screen would otherwise leave the page white. React logs the error. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? <PageProblem /> : this.props.children;
  }
}
