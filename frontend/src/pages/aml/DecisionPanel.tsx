import { Check, Hand, Loader2, RotateCw, TriangleAlert } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { dateTime, verdictLabel } from "../../api/format";
import { useApi } from "../../api/runtime";
import type { Interrupt, LeadAction } from "../../api/types";
import { Banner, Button, cx } from "../../ui/kit";
import { ACTION_ORDER, ACTIONS, isLeadAction, recommendedAction, type DecisionInfo, type LeadStatusInfo } from "./aml";

const MIN_NOTE = 5;

const DECIDED: Partial<Record<NonNullable<LeadStatusInfo["key"]>, { title: string; body: string }>> = {
  RTS_DEPUS: { title: "RTS marcat pentru depunere", body: "În demo depunerea e simulată. Raportul îl trimite un om, pe canalele ONPCSB." },
  INCHIS: { title: "Pistă închisă", body: "Fără raport. Motivarea ta e în jurnalul de audit." },
  INFORMATII: { title: "Ai cerut informații suplimentare", body: "Pista rămâne deschisă; nimic nu a plecat spre zona client." },
  HOLD_EMIS: { title: "HOLD emis spre zona client", body: "Zona client a primit doar un semnal da/nu, fără detalii." },
};

function ConfirmStep({ action, leadId, onCancel, onSent }: { action: LeadAction; leadId: string; onCancel: () => void; onSent: () => void }) {
  const api = useApi();
  const info = ACTIONS[action];
  const id = useId();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    ref.current?.focus();
  }, [action]);
  const valid = note.trim().length >= MIN_NOTE;

  const submit = async () => {
    if (!valid || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = (await api.amlDecide(leadId, { action, note: note.trim() })) as { ok?: boolean; detail?: string } | null;
      if (res && res.ok === false) throw new Error(res.detail || "Serverul nu a acceptat decizia.");
      onSent();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  return (
    <div
      role="group"
      aria-labelledby={`${id}-t`}
      onKeyDown={(e) => {
        if (e.key === "Escape" && !busy) onCancel();
      }}
      className={cx("animate-enter rounded-lg border bg-paper p-4", info.danger ? "border-danger-line" : "border-ink")}
    >
      <p id={`${id}-t`} className={cx("font-semibold", info.danger && "text-danger")}>
        {info.label}: ce se întâmplă
      </p>
      <p className="mt-1 max-w-[75ch] text-ink-soft">{info.consequence}</p>
      <label htmlFor={`${id}-n`} className="mt-3 block text-[0.8667rem] font-semibold">
        Notă pentru jurnalul de audit
      </label>
      <textarea
        id={`${id}-n`}
        ref={ref}
        rows={2}
        maxLength={500}
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder={info.placeholder}
        aria-describedby={`${id}-h`}
        className="mt-1 w-full max-w-[75ch] rounded-md border border-line-strong bg-paper px-3 py-2"
      />
      <p id={`${id}-h`} className="mt-1 text-[0.8667rem] text-muted">
        {valid ? "Nota intră în jurnalul de audit, lângă numele tău." : `Scrie cel puțin ${MIN_NOTE} caractere.`}
      </p>
      {error && (
        <p role="alert" className="mt-2 flex items-center gap-2 text-[0.9333rem] font-semibold text-danger">
          <TriangleAlert aria-hidden className="size-4" />
          Decizia nu a fost trimisă: {error}
        </p>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant={info.danger ? "danger" : "primary"} busy={busy} disabled={!valid} onClick={() => void submit()}>
          {info.confirm}
        </Button>
        <Button variant="ghost" onClick={onCancel} disabled={busy}>
          Renunță
        </Button>
      </div>
    </div>
  );
}

function DecisionBanner({ leadId, interrupt, recommendation, applying, onSent }: {
  leadId: string;
  interrupt: Interrupt;
  recommendation: string | null;
  /** Decizia trimisă de aici (sau `interrupt.resuming`): butoanele rămân, dar inactive. */
  applying: LeadAction | "server" | null;
  onSent: (a: LeadAction) => void;
}) {
  const [choice, setChoice] = useState<LeadAction | null>(null);
  const offered = Array.isArray(interrupt.options) ? interrupt.options.filter(isLeadAction) : [];
  const options = offered.length ? ACTION_ORDER.filter((a) => offered.includes(a)) : ACTION_ORDER;
  const rec = interrupt.recommendation ?? recommendation;
  const primary = recommendedAction(rec);
  const disabled = applying !== null;

  return (
    <div className="mb-6 space-y-2">
      <Banner
        tone="now"
        icon={<Hand aria-hidden className="size-5" />}
        title="Decizia ta"
        actions={options.map((a) => {
          const danger = Boolean(ACTIONS[a].danger);
          const chosen = choice === a;
          const variant = danger ? "danger" : !choice && a === primary ? "primary" : "secondary";
          return (
            <Button
              key={a}
              variant={variant}
              aria-pressed={chosen}
              disabled={disabled}
              onClick={() => setChoice(chosen ? null : a)}
              className={cx(chosen && (danger ? "bg-danger-soft" : "border-ink bg-yellow-tint"))}
            >
              {ACTIONS[a].label}
            </Button>
          );
        })}
      >
        {applying ? (
          <span className="inline-flex items-center gap-2">
            <Loader2 aria-hidden className="size-4 animate-spin" />
            {applying === "server" ? "Se aplică decizia…" : `Se aplică decizia: ${ACTIONS[applying].label}.`} Agenții închid pasul „Analist” și sigilează dosarul.
          </span>
        ) : (
          <>
            Agenții au terminat. Nimic nu pleacă din bancă fără tine.
            {rec && (
              <>
                {" "}
                Regulile AML recomandă: <span className="font-semibold text-ink">{verdictLabel(rec)}</span>.
              </>
            )}
          </>
        )}
      </Banner>
      {choice && !disabled && (
        <ConfirmStep key={choice} action={choice} leadId={leadId} onCancel={() => setChoice(null)} onSent={() => onSent(choice)} />
      )}
    </div>
  );
}

/**
 * Locul deciziei, sub antet: bannerul „Decizia ta” cât timp agenții așteaptă un om,
 * apoi starea aplicării și, la final, ce s-a decis. O eroare de rulare apare tot aici.
 */
export function DecisionArea({ leadId, interrupt, status, recommendation, decision, runError, onChanged, onRerun, rerunBusy }: {
  leadId: string;
  interrupt: Interrupt | null;
  status: LeadStatusInfo | null;
  recommendation: string | null;
  decision: DecisionInfo | null;
  runError: string | null;
  onChanged: () => void;
  onRerun?: () => void;
  rerunBusy?: boolean;
}) {
  const [sent, setSent] = useState<LeadAction | null>(null);
  const pending = Boolean(interrupt?.pending);
  const resuming = Boolean(interrupt?.resuming);
  // serverul a preluat decizia (nu mai e nimic în așteptare): steagul local nu mai trebuie
  useEffect(() => {
    if (sent && !pending && !resuming) setSent(null);
  }, [sent, pending, resuming]);
  // plasă de siguranță: dacă serverul nu confirmă în 20 s, butoanele revin
  useEffect(() => {
    if (!sent) return;
    const t = window.setTimeout(() => setSent(null), 20_000);
    return () => window.clearTimeout(t);
  }, [sent]);

  if (pending && interrupt) {
    return (
      <DecisionBanner
        leadId={leadId}
        interrupt={interrupt}
        recommendation={recommendation}
        applying={sent ?? (resuming ? "server" : null)}
        onSent={(a) => {
          setSent(a);
          onChanged();
        }}
      />
    );
  }
  if (sent) {
    return (
      <div className="mb-6">
        <Banner tone="neutral" icon={<Loader2 aria-hidden className="size-5 animate-spin" />} title={`Se aplică decizia: ${ACTIONS[sent].label}`}>
          Agenții închid pasul „Analist” și sigilează dosarul.
        </Banner>
      </div>
    );
  }
  if (status?.key === "EROARE") {
    return (
      <div className="mb-6">
        <Banner
          tone="danger"
          icon={<TriangleAlert aria-hidden className="size-5 text-danger" />}
          title="Investigația s-a oprit cu o eroare."
          actions={
            onRerun && (
              <Button size="sm" icon={<RotateCw aria-hidden className="size-3.5" />} busy={rerunBusy} onClick={onRerun}>
                Rulează din nou
              </Button>
            )
          }
        >
          {runError ?? "Agenții nu au putut termina pista."} Probele strânse până acum rămân în registru.
        </Banner>
      </div>
    );
  }
  const done = status?.key ? DECIDED[status.key] : undefined;
  if (done) {
    const who = [decision?.analyst, decision?.at ? dateTime(decision.at) : null].filter(Boolean).join(", ");
    return (
      <div className="mb-6">
        <Banner tone="neutral" icon={<Check aria-hidden className="size-5" />} title={done.title}>
          {done.body}
          {decision?.note && (
            <>
              {" "}
              Nota{who ? ` (${who})` : ""}: „{decision.note}”
            </>
          )}
        </Banner>
      </div>
    );
  }
  return null;
}
