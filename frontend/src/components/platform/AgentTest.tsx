import { useEffect, useRef, useState } from "react";
import { Bot } from "lucide-react";
import { ApiError } from "@/api/bff";
import { platformApi, type AgentOp } from "@/api/platform";
import { Button } from "@/components/ui/button";
import { CopyableId } from "@/components/ui/CopyableId";
import { t } from "@/i18n";
import { cn, newCorrelationId } from "@/lib/utils";

/** The apartments the agent accepts an order «stato» for: the staging ones (lab-…, test-…) and dev (bff/agent.py). */
export const agentTestable = (apartmentId: string) => apartmentId === "dev" || /^(lab|test)-/.test(apartmentId);

const POLL_MS = 4_000;
/** The server's own limit (bff/agent.py MAX_WAIT): after it, a read gives «fallito/tempo_scaduto»; the page stops too. */
const MAX_WAIT_MS = 20 * 60_000;

type View =
  | { kind: "idle" }
  | { kind: "sending" }
  | { kind: "op"; op: AgentOp }
  | { kind: "timeout"; opId: string }
  | { kind: "notConfigured" }
  | { kind: "error"; message: string; id: string | null };

/** «Agente raggiungibile. Motore: sano · collegamento ai dispositivi: attivo · versione: 247fda0», each part only if known. */
function successText(dati: AgentOp["dati"]): string {
  const parts = [t("platform.agent.engine", { state: dati?.health === 200 ? t("platform.agent.engineOk") : t("platform.agent.engineDown") })];
  if (dati?.connector) parts.push(t("platform.agent.connector", { state: dati.connector === "up" ? t("platform.agent.connectorUp") : t("platform.agent.connectorDown") }));
  if (dati?.immagine) parts.push(t("platform.agent.version", { version: dati.immagine.split(":").pop() ?? dati.immagine }));
  return `${t("platform.agent.ok")} ${parts.join(" · ")}`;
}

/**
 * «Prova l'agente» on the row of a staging apartment (strumento A, A1; o1 448a71a): sends the order, reads the
 * operation again every 4 s while it is «inviato», at most 20 minutes, and shows the server's sentence or the result.
 */
export function AgentTest({ apartmentId }: { apartmentId: string }) {
  const [view, setView] = useState<View>({ kind: "idle" });
  const started = useRef(0);
  // one more each time the operation is read: the next reading is scheduled even when the answer is the same object
  const [readCount, setReadCount] = useState(0);

  // the reading again: one timer at a time, none after the outcome or once the row is gone
  const opWaiting = view.kind === "op" && view.op.stato === "inviato" ? view.op.op_id : null;
  useEffect(() => {
    if (!opWaiting) return;
    let live = true;
    const timer = setTimeout(async () => {
      try {
        const op = await platformApi.agentOp(opWaiting);
        if (!live) return;
        setReadCount((n) => n + 1);
        if (op.stato === "inviato" && Date.now() - started.current >= MAX_WAIT_MS) setView({ kind: "timeout", opId: op.op_id });
        else setView({ kind: "op", op });
      } catch (err) {
        if (live) setView({ kind: "error", message: err instanceof Error ? err.message : String(err), id: err instanceof ApiError ? err.correlationId : null });
      }
    }, POLL_MS);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [opWaiting, readCount]);

  const send = async () => {
    setView({ kind: "sending" });
    started.current = Date.now();
    try {
      setView({ kind: "op", op: await platformApi.agentTest(apartmentId, newCorrelationId()) });
    } catch (err) {
      if (err instanceof ApiError && err.code === "agent_not_configured") setView({ kind: "notConfigured" });
      else setView({ kind: "error", message: err instanceof Error ? err.message : String(err), id: err instanceof ApiError ? err.correlationId : null });
    }
  };

  const busy = view.kind === "sending" || opWaiting !== null;
  const outcome = (() => {
    if (view.kind === "op" && view.op.stato === "inviato") return { state: "inviato", text: view.op.messaggio, bad: false, id: null };
    if (view.kind === "op" && view.op.stato === "riuscito") return { state: "riuscito", text: successText(view.op.dati), bad: false, id: null };
    if (view.kind === "op") return { state: view.op.stato, text: view.op.messaggio, bad: true, id: view.op.op_id };
    if (view.kind === "timeout") return { state: "fallito", text: t("platform.agent.timeout"), bad: true, id: view.opId };
    if (view.kind === "notConfigured") return { state: "not-configured", text: t("platform.agent.notConfigured"), bad: false, id: null };
    if (view.kind === "error") return { state: "error", text: view.message, bad: true, id: view.id };
    return null;
  })();

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => void send()} disabled={busy} data-testid={`agent-test-btn-${apartmentId}`}>
        <Bot /> {t("platform.agent.button")}
      </Button>
      {outcome && (
        <p
          role="status"
          className={cn("basis-full text-xs [overflow-wrap:anywhere]", outcome.bad ? "font-medium text-destructive" : outcome.state === "riuscito" ? "font-medium text-positive-fg" : "text-muted-foreground")}
          data-testid={`agent-test-${apartmentId}`}
          data-state={outcome.state}
        >
          {outcome.text}
          {outcome.id && <> <CopyableId id={outcome.id} testId={`agent-test-id-${apartmentId}`} /></>}
        </p>
      )}
    </>
  );
}
