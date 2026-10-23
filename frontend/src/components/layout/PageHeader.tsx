import type { ReactNode } from "react";

/**
 * The title of every page (lotto 32, design review b.7): 24 px at 700, an app title, not a landing one. `badges`
 * sit beside the title (the apartment's state), `children` below it (the Panoramica's facts).
 */
export function PageHeader({ title, subtitle, actions, testId, titleTestId, badges, children }: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  testId: string;
  titleTestId?: string;
  badges?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="space-y-4" data-testid={testId}>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight [overflow-wrap:anywhere]" data-testid={titleTestId}>{title}</h1>
            {badges}
          </div>
          {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
        </div>
        {actions && <div className="flex min-w-0 max-w-full flex-wrap gap-2">{actions}</div>}
      </div>
      {children}
    </header>
  );
}

export function SegmentedControl<T extends string>({ value, options, onChange, testId }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; testId: string }) {
  return (
    // Scrolls inside itself when the tabs do not fit (phone width), never the whole page.
    <div role="tablist" className="inline-flex max-w-full overflow-x-auto rounded-full border bg-secondary/60 p-1" data-testid={testId}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="tab"
          aria-selected={value === o.value}
          onClick={() => onChange(o.value)}
          data-testid={`${testId}-${o.value}`}
          className={`min-h-[36px] shrink-0 whitespace-nowrap rounded-full px-4 text-sm font-bold transition-colors focus-ring ${value === o.value ? "bg-card text-primary shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
