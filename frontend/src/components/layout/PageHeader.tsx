import type { ReactNode } from "react";

export function PageHeader({ title, subtitle, actions, testId }: { title: string; subtitle?: string; actions?: ReactNode; testId: string }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4" data-testid={testId}>
      <div>
        <h1 className="text-3xl font-extrabold tracking-tight sm:text-4xl">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
      </div>
      {actions && <div className="flex min-w-0 max-w-full flex-wrap gap-2">{actions}</div>}
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
