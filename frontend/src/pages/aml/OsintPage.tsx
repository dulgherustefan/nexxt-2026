import { Search, ShieldAlert, ShieldCheck } from "lucide-react";
import { useEffect, useId, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";
import { useApi } from "../../api/runtime";
import type { OsintKind, OsintResult } from "../../api/types";
import { Banner, Button, EmptyState, ErrorNote, Loading, PageHeader, SectionBoundary } from "../../ui/kit";
import { detectOsintKind, isOsintKind, OSINT_KINDS, osintLoadingLabel, privacyGuard, roCount, SIGNAL_INFO, SIGNAL_ORDER } from "./aml";
import { OsintGroups, signalCounts } from "./ui";

/** Identificatori sintetici din demo (aceiași în modul mock și în datele backend-ului). */
const EXAMPLES = ["livrare-bancademo.example", "bancademo.example"];

type State =
  | { status: "idle" }
  | { status: "blocked"; message: string }
  | { status: "loading"; target: string; kind: OsintKind }
  | { status: "done"; target: string; kind: OsintKind; result: OsintResult }
  | { status: "error"; target: string; error: unknown };

function kindName(kind: string | null | undefined): string | null {
  const k = OSINT_KINDS.find((x) => x.id === kind);
  return k && k.id !== "auto" ? k.label.toLowerCase() : null;
}

/** Tipul pe care l-a folosit serverul: `raw.kind` (mock) sau cheile din `artifacts` (backend). */
function usedKind(result: OsintResult, target: string, asked: OsintKind): string | null {
  if (asked !== "auto") return kindName(asked);
  const raw = result.raw?.kind;
  if (typeof raw === "string") return kindName(raw);
  const keys = Object.entries(result.artifacts ?? {}).filter(([, v]) => Array.isArray(v) && v.length).map(([k]) => k);
  const map: Record<string, string> = { domains: "domeniu", urls: "URL", phones: "telefon", cuis: "CUI", ibans: "IBAN", companies: "firmă" };
  if (keys.length) return keys.map((k) => map[k] ?? k).join(", ");
  return kindName(detectOsintKind(target));
}

export default function OsintPage() {
  const api = useApi();
  const [params, setParams] = useSearchParams();
  const q = (params.get("q") ?? "").trim();
  const kindParam = params.get("tip") ?? params.get("kind");
  const urlKind: OsintKind = isOsintKind(kindParam) ? kindParam : "auto";

  const [input, setInput] = useState(q);
  const [kind, setKind] = useState<OsintKind>(urlKind);
  const [formError, setFormError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const [state, setState] = useState<State>({ status: "idle" });
  const ids = useId();

  // linkurile din alte pagini (/osint?q=…) schimbă căutarea: câmpurile urmează adresa
  useEffect(() => {
    setInput(q);
    setKind(urlKind);
  }, [q, urlKind]);

  useEffect(() => {
    if (!q) {
      setState({ status: "idle" });
      return;
    }
    const guard = privacyGuard(q);
    if (guard) {
      setState({ status: "blocked", message: guard });
      return;
    }
    let alive = true;
    setState({ status: "loading", target: q, kind: urlKind });
    api.amlOsint({ target: q, kind: urlKind }).then(
      (result) => {
        if (alive) setState({ status: "done", target: q, kind: urlKind, result: result && Array.isArray(result.findings) ? result : { findings: [] } });
      },
      (error) => {
        if (alive) setState({ status: "error", target: q, error });
      },
    );
    return () => {
      alive = false;
    };
  }, [api, q, urlKind, nonce]);

  const run = (target: string, k: OsintKind) => {
    const t = target.trim();
    if (!t) {
      setFormError("Scrie un identificator: un domeniu, un URL, un telefon, un CUI, un IBAN sau o firmă.");
      return;
    }
    const guard = privacyGuard(t);
    if (guard) {
      setFormError(guard);
      return;
    }
    setFormError(null);
    if (t === q && k === urlKind) {
      setNonce((n) => n + 1);
      return;
    }
    const next = new URLSearchParams();
    next.set("q", t);
    if (k !== "auto") next.set("tip", k);
    setParams(next);
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    run(input, kind);
  };

  const busy = state.status === "loading";

  return (
    <div>
      <PageHeader
        title="Verificare OSINT"
        description="Verifici un identificator al beneficiarului în surse publice: registre, DNS, certificate, liste de sancțiuni, presă."
      />

      <form onSubmit={submit} role="search" aria-label="Verificare OSINT" className="rounded-lg border border-line bg-paper p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="min-w-0 flex-1">
            <label htmlFor={`${ids}-q`} className="mb-1 block text-[0.8667rem] font-semibold">
              Identificator
            </label>
            <div className="relative">
              <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" />
              <input
                id={`${ids}-q`}
                type="search"
                value={input}
                onChange={(e) => {
                  setInput(e.target.value);
                  if (formError) setFormError(null);
                }}
                placeholder="Domeniu, URL, telefon, CUI, IBAN sau firmă"
                autoComplete="off"
                spellCheck={false}
                aria-invalid={formError ? true : undefined}
                aria-describedby={formError ? `${ids}-err` : `${ids}-note`}
                className="h-10 w-full rounded-md border border-line-strong bg-paper pr-3 pl-9"
              />
            </div>
          </div>
          <div className="sm:w-44">
            <label htmlFor={`${ids}-k`} className="mb-1 block text-[0.8667rem] font-semibold">
              Tip
            </label>
            <select
              id={`${ids}-k`}
              value={kind}
              onChange={(e) => setKind(isOsintKind(e.target.value) ? e.target.value : "auto")}
              className="h-10 w-full rounded-md border border-line-strong bg-paper px-3"
            >
              {OSINT_KINDS.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.id === "auto" ? "Auto (detectez eu)" : k.label}
                </option>
              ))}
            </select>
          </div>
          <Button type="submit" variant="primary" busy={busy}>
            Verifică
          </Button>
        </div>
        {formError ? (
          <p id={`${ids}-err`} role="alert" className="mt-3 flex items-center gap-2 text-[0.9333rem] font-semibold text-danger">
            <ShieldAlert aria-hidden className="size-4" />
            {formError}
          </p>
        ) : (
          <p id={`${ids}-note`} className="mt-3 flex items-start gap-2 text-[0.8667rem] text-muted">
            <ShieldCheck aria-hidden className="mt-0.5 size-4 shrink-0" />
            Interoghez doar identificatori publici ai beneficiarului. Datele victimelor nu pleacă niciodată spre surse publice.
          </p>
        )}
      </form>

      <div className="mt-6">
        <SectionBoundary label="Rezultatele OSINT">
          {state.status === "idle" && (
            <EmptyState icon={<Search aria-hidden className="size-5" />} title="Scrie un identificator și apasă „Verifică”.">
              <span className="mt-1 flex flex-wrap items-center gap-2">
                Exemple din datele sintetice:
                {EXAMPLES.map((x) => (
                  <Button key={x} size="sm" variant="secondary" className="font-mono font-medium" onClick={() => run(x, "auto")}>
                    {x}
                  </Button>
                ))}
              </span>
            </EmptyState>
          )}

          {state.status === "blocked" && (
            <Banner tone="danger" icon={<ShieldAlert aria-hidden className="size-5 text-danger" />} title="Nu interoghez acest identificator.">
              {state.message}
            </Banner>
          )}

          {state.status === "loading" && <Loading label={osintLoadingLabel(state.target, state.kind)} />}

          {state.status === "error" && <ErrorNote error={state.error} what="rezultatele OSINT" onRetry={() => setNonce((n) => n + 1)} />}

          {state.status === "done" && <Results target={state.target} kind={state.kind} result={state.result} />}
        </SectionBoundary>
      </div>
    </div>
  );
}

function Results({ target, kind, result }: { target: string; kind: OsintKind; result: OsintResult }) {
  const findings = result.findings.filter((f) => f && typeof f.tool === "string");
  if (result.denied) {
    return (
      <Banner tone="danger" icon={<ShieldAlert aria-hidden className="size-5 text-danger" />} title="Politica de acces a refuzat interogarea.">
        {result.denied.reason || "Zona AML nu are voie să apeleze această sursă."}
      </Banner>
    );
  }
  if (!findings.length) {
    return (
      <EmptyState icon={<Search aria-hidden className="size-5" />} title={`Nicio sursă nu a întors ceva pentru „${target}”.`}>
        Verifică scrierea sau alege tipul de identificator din listă, în loc de „Auto”.
      </EmptyState>
    );
  }
  const counts = signalCounts(findings);
  const used = usedKind(result, target, kind);
  return (
    <div className="space-y-4">
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.9333rem]">
        <span className="font-semibold">
          {roCount(findings.length, "Un rezultat", "rezultate")} pentru <span className="font-mono">{target}</span>
        </span>
        {used && <span className="text-muted">tip: {used}</span>}
        <span className="text-muted">
          {SIGNAL_ORDER.filter((s) => counts[s])
            .map((s) => `${counts[s]} ${SIGNAL_INFO[s].label.toLowerCase()}`)
            .join(" · ")}
        </span>
      </p>
      <OsintGroups findings={findings} />
    </div>
  );
}
