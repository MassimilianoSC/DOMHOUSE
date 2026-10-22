import { useInfiniteQuery } from "@tanstack/react-query";
import { ErrorNotice } from "@/components/apartment/ErrorNotice";
import { Button } from "@/components/ui/button";
import { Card, Skeleton } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { describeEntry, type AuditPage } from "@/lib/auditLog";
import { fmtDateTime } from "@/lib/format";

/**
 * «Registro attività» (P-47): one sentence per action, newest first, with «Carica altri». The same list for the admin
 * (their organization) and for the platform (one organization, or the platform's own actions).
 */
export function AuditLog({ load, queryKey, hint, title }: { load: (before?: string) => Promise<AuditPage>; queryKey: unknown[]; hint: string; title?: string }) {
  const q = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam }) => load(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next ?? undefined,
    staleTime: 30_000,
  });
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <div className="space-y-4">
      {title && <h2 className="text-base font-bold md:text-lg" data-testid="audit-title">{title}</h2>}
      <p className="text-sm text-muted-foreground" data-testid="audit-hint">{hint}</p>
      {q.error && <ErrorNotice error={q.error} onRetry={() => void q.refetch()} testId="audit-error" />}
      {q.isLoading ? <Skeleton className="h-48 rounded-2xl" /> : q.data && items.length === 0 ? (
        <Card className="p-10 text-center text-sm text-muted-foreground" data-testid="audit-empty">{t("audit.empty")}</Card>
      ) : items.length > 0 && (
        <Card className="px-5">
          <ul className="divide-y" data-testid="audit-list">
            {items.map((e) => {
              const { sentence, note } = describeEntry(e);
              return (
                <li key={e.audit_id} className="py-3" data-testid={`audit-${e.audit_id}`} data-action={e.action}>
                  <p className="text-sm font-semibold" data-testid={`audit-sentence-${e.audit_id}`}>{sentence}</p>
                  {note && <p className="text-sm text-muted-foreground" data-testid={`audit-note-${e.audit_id}`}>{note}</p>}
                  <p className="text-xs tabular text-muted-foreground">{fmtDateTime(e.at)}</p>
                </li>
              );
            })}
          </ul>
        </Card>
      )}
      {q.hasNextPage && (
        <div className="flex justify-center">
          <Button variant="outline" onClick={() => void q.fetchNextPage()} disabled={q.isFetchingNextPage} data-testid="audit-more">
            {q.isFetchingNextPage ? t("common.loading") : t("common.loadMore")}
          </Button>
        </div>
      )}
    </div>
  );
}
