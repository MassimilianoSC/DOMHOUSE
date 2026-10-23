import type { ReactNode } from "react";
import { Card } from "@/components/ui/primitives";

/**
 * One section of Impostazioni (design lot 2): on a wide screen the title on the left and the panel on the right; on a
 * phone the title above the panel. Sections are divided by a 1 px line, not by seven cards with seven icons.
 */
export function SettingsSection({ title, hint, children, testId }: { title: string; hint?: string; children: ReactNode; testId: string }) {
  return (
    <section className="grid gap-3 border-t pt-6 lg:grid-cols-[12rem_minmax(0,1fr)] lg:gap-8" data-testid={`${testId}-section`}>
      <div>
        <h2 className="text-base font-semibold">{title}</h2>
        {hint && <p className="mt-1 text-[13px] text-muted-foreground">{hint}</p>}
      </div>
      <Card className="min-w-0 p-5" data-testid={testId}>
        {children}
      </Card>
    </section>
  );
}
