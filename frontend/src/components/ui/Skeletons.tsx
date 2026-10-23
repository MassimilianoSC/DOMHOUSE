import { Card, Skeleton } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

/**
 * Placeholders with the final layout of the page (design lot 2), so nothing jumps when the data arrive: the title
 * where the title will be, a strip where the strip will be, rows where the rows will be.
 */

/** The page's title and subtitle, then one block: the fallback while a page block loads. */
export function PageSkeleton({ testId = "page-skeleton" }: { testId?: string }) {
  return (
    <div className="mx-auto max-w-6xl space-y-6" data-testid={testId}>
      <div className="space-y-2">
        <Skeleton className="h-8 w-56 rounded-md" />
        <Skeleton className="h-4 w-72 max-w-full rounded-md" />
      </div>
      <Skeleton className="h-40 rounded-lg" />
    </div>
  );
}

/** A strip of cells divided by 1 px lines (the Panoramica's band, the Consumi indicators). */
export function StripSkeleton({ cells, className, cellClassName = "h-[76px]" }: { cells: number; className?: string; cellClassName?: string }) {
  return (
    <div className={cn("grid gap-px overflow-hidden rounded-lg border bg-border", className)} data-testid="strip-skeleton">
      {Array.from({ length: cells }, (_, i) => (
        <div key={i} className={cn("space-y-2 bg-card px-4 py-3", cellClassName)}>
          <Skeleton className="h-3 w-20 rounded-sm" />
          <Skeleton className="h-5 w-24 rounded-sm" />
        </div>
      ))}
    </div>
  );
}

/** One card with rows divided by 1 px lines (Decisioni, Programmazione, Amministrazione). */
export function RowsSkeleton({ rows, lines = 2, className }: { rows: number; lines?: 2 | 3; className?: string }) {
  return (
    <Card className={cn("divide-y px-5", className)} data-testid="rows-skeleton">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="space-y-2 py-4">
          <Skeleton className="h-4 w-2/3 rounded-sm" />
          <Skeleton className="h-3 w-1/2 rounded-sm" />
          {lines === 3 && <Skeleton className="h-3 w-5/6 rounded-sm" />}
        </div>
      ))}
    </Card>
  );
}
