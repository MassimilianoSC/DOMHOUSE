import { Component, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { browser } from "@/lib/lazyPage";

/** E-29: what the person sees instead of an endless loading state or a white page, with the one thing they can do. */
export function PageProblem() {
  return (
    <div className="flex min-h-screen items-center justify-center p-5" role="alert" data-testid="page-problem">
      <Card className="w-full max-w-md p-5 sm:p-8">
        <h1 className="text-2xl font-bold">{t("errors.pageProblem")}</h1>
        <p className="mb-6 mt-1 text-sm text-muted-foreground">{t("errors.pageProblemHint")}</p>
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
