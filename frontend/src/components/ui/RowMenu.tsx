import type { ReactNode } from "react";
import { MoreHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

/**
 * The «⋯» menu at the end of a row (design lot 2): the less frequent actions of a user or an organization, so the row
 * keeps one or two buttons and stays on two lines on a phone.
 */
export function RowMenu({ label, testId, children }: { label: string; testId: string; children: ReactNode }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="iconSm" aria-label={label} data-testid={testId}>
          <MoreHorizontal />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">{children}</DropdownMenuContent>
    </DropdownMenu>
  );
}

/** One entry of a RowMenu; `danger` writes it in red (delete, suspend). */
export function RowMenuItem({ onSelect, disabled, danger, testId, children }: { onSelect: () => void; disabled?: boolean; danger?: boolean; testId: string; children: ReactNode }) {
  return (
    <DropdownMenuItem onSelect={onSelect} disabled={disabled} className={cn("data-[disabled]:pointer-events-none data-[disabled]:opacity-50", danger && "text-negative")} data-testid={testId}>
      {children}
    </DropdownMenuItem>
  );
}
