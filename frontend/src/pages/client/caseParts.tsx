/**
 * Piesele paginii de caz: citări, reguli, scrisoarea și zidul, recuperarea, registrul, reclamația.
 * Pagina în sine e în CaseRoom.tsx. Piesele nu au chenar propriu: stau în secțiunile pliabile ale paginii.
 */
import { Check, ShieldAlert, ShieldCheck, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { normalizeRo, shortHash, verdictLabel } from "../../api/format";
import { useApi } from "../../api/runtime";
import type { CaseDetail, FilterResult, LedgerResponse, VerifyResult } from "../../api/types";
import { Badge, Button, cx, DeadlineText, EmptyState, IdTag, KeyValues } from "../../ui/kit";
import { exactTime } from "./caseUi";

// ---------------------------------------------------------------- citări

export function Cites({ ids, onCite }: { ids?: string[]; onCite: (id: string) => void }) {
  if (!ids?.length) return null;
  return (
    <span className="ml-1.5 inline-flex flex-wrap gap-1 align-middle">
      {ids.map((c) => <IdTag key={c} onClick={() => onCite(c)} title={`Arată proba ${c}`}>{c}</IdTag>)}
    </span>
  );
}

export function Arguments({ lines, onCite }: { lines?: Array<{ text: string; cites?: string[] }>; onCite: (id: string) => void }) {
  if (!lines?.length) return <p className="text-[0.9333rem] text-muted">Fără argumente.</p>;
  return (
    <ul className="flex flex-col gap-2.5">
      {lines.map((l, i) => <li key={i} className="text-[0.9333rem] text-ink-soft">{l.text}<Cites ids={l.cites} onCite={onCite} /></li>)}
    </ul>
  );
}

// ---------------------------------------------------------------- reguli și termene

export const CONFIDENCE: Record<string, string> = { P: "text oficial", S: "sursă secundară", U: "parametru neverificat", V: "verificat" };

export function RulesList({ d }: { d: CaseDetail }) {
  const hits = d.rules?.hits ?? [];
  const deadlines = d.rules?.deadlines ?? [];
  if (!hits.length && !deadlines.length) return <p className="text-[0.9333rem] text-muted">Regulile nu au rulat încă.</p>;
  return (
    <div className="flex flex-col gap-5">
      <ul className="divide-y divide-line rounded-md border border-line">
        {hits.map((h, i) => (
          <li key={`${h.rule_id}-${i}`} className="grid gap-x-4 gap-y-1 px-3 py-2.5 sm:grid-cols-[5.5rem_minmax(0,1fr)_auto]">
            <span><IdTag>{h.rule_id}</IdTag></span>
            <div className="min-w-0">
              <p className="text-[0.9333rem] font-medium">{h.title}</p>
              {h.explanation && <p className="mt-0.5 text-[0.8667rem] text-muted">{h.explanation}</p>}
              <p className="mt-0.5 text-[0.8rem] text-subtle">{h.basis}</p>
            </div>
            <span className="text-[0.8rem] whitespace-nowrap text-muted">{CONFIDENCE[String(h.confidence)] ?? h.confidence ?? ""}</span>
          </li>
        ))}
      </ul>
      {deadlines.length > 0 && (
        <div>
          <p className="mb-2 text-[0.8667rem] font-semibold text-muted">Termene legale</p>
          <ul className="divide-y divide-line rounded-md border border-line">
            {deadlines.map((dl, i) => (
              <li key={i} className="flex flex-wrap items-center justify-between gap-3 px-3 py-2.5 text-[0.9333rem]">
                <span className="min-w-0">{dl.name} <span className="font-mono text-[0.75rem] text-muted">{dl.rule_id}</span></span>
                <span className="flex items-center gap-3"><span className="tabular-nums text-muted">{exactTime(dl.due_at)}</span><DeadlineText deadline={dl.due_at} /></span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- scrisoarea + verificarea prin zid

export const ATTACK_TEXT = "Vă informăm că am raportat contul beneficiarului la ONPCSB pentru spălare de bani.";

/** Literă cu literă, fără diacritice și cu litere mici: pozițiile rămân aceleași ca în textul original. */
export function fold(s: string): string {
  return s.split("").map((ch) => {
    const f = ch.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
    return f.length === 1 ? f : ch;
  }).join("");
}

/** Rezervă când serverul nu trimite `term_spans`: caută singuri termenii blocați în text. */
export function spansFromTerms(text: string, terms: string[] | undefined): NonNullable<FilterResult["term_spans"]> {
  const hay = fold(text);
  const out: NonNullable<FilterResult["term_spans"]> = [];
  for (const term of terms ?? []) {
    const needle = fold(term.trim());
    if (!needle) continue;
    for (let i = hay.indexOf(needle); i !== -1; i = hay.indexOf(needle, i + needle.length)) {
      out.push({ start: i, end: i + needle.length, label: "termen interzis" });
    }
  }
  return out;
}

export function Highlighted({ text, spans }: { text: string; spans?: FilterResult["term_spans"] }) {
  if (!spans?.length) return <>{text}</>;
  const parts: ReactNode[] = [];
  let at = 0;
  [...spans].sort((a, b) => a.start - b.start).forEach((s, i) => {
    const start = Math.max(s.start, at);
    if (s.end <= start) return;
    if (start > at) parts.push(text.slice(at, start));
    parts.push(<mark key={i} className="rounded-sm bg-danger-soft px-0.5 text-danger underline decoration-danger-line decoration-2 underline-offset-2" title={s.label}>{text.slice(start, s.end)}</mark>);
    at = s.end;
  });
  parts.push(text.slice(at));
  return <>{parts}</>;
}

/** Rezultatul verificării unui text prin filtrul zidului. */
export function FilterVerdict({ result, text }: { result: FilterResult; text: string }) {
  return (
    <div className={cx("rounded-md border px-4 py-3", result.passed ? "border-ok-line bg-ok-soft" : "border-danger-line bg-danger-soft")} role="status">
      <p className="flex items-center gap-2 text-[0.9333rem] font-semibold">
        {result.passed
          ? <><ShieldCheck className="size-4 text-ok" /> Textul poate pleca.</>
          : <><ShieldAlert className="size-4 text-danger" /> Zidul oprește textul. Îl citește un om.</>}
      </p>
      {!result.passed && <p className="mt-2 text-[0.9333rem] leading-relaxed"><Highlighted text={text} spans={result.term_spans?.length ? result.term_spans : spansFromTerms(text, result.blocked_terms)} /></p>}
      {result.reasons?.length ? <ul className="mt-2 list-disc pl-5 text-[0.8667rem] text-ink-soft">{result.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul> : null}
    </div>
  );
}

export function LetterSection({ d, caseId, onCite }: { d: CaseDetail; caseId: string; onCite: (id: string) => void }) {
  const api = useApi();
  const letter = d.letter;
  const [draft, setDraft] = useState(ATTACK_TEXT);
  const [result, setResult] = useState<FilterResult | null>(null);
  const [checked, setChecked] = useState(ATTACK_TEXT);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const blocked = letter?.filter?.passed === false;
  const letterSpans = blocked && letter
    ? (letter.filter?.term_spans?.length ? letter.filter.term_spans : spansFromTerms(letter.body, letter.filter?.blocked_terms))
    : undefined;
  function editLetter() {
    if (!letter) return;
    setDraft(letter.body);
    setResult(null);
    window.setTimeout(() => {
      const box = document.getElementById("wall-test") as HTMLTextAreaElement | null;
      box?.scrollIntoView({ behavior: "smooth", block: "center" });
      box?.focus({ preventScroll: true });
    }, 60);
  }
  async function check() {
    setBusy(true);
    setError(null);
    try {
      const text = normalizeRo(draft);
      setResult(await api.letterCheck(caseId, { body: text }));
      setChecked(text);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Verificarea nu a răspuns.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex flex-col gap-6">
      {!letter ? (
        <p className="text-[0.9333rem] text-muted">Scrisoarea apare după decizie. Înainte să plece, trece prin filtrul zidului.</p>
      ) : (
        <div>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            {blocked
              ? <Badge tone="danger" icon={<ShieldAlert className="size-3.5" />}>Oprită de zid</Badge>
              : <Badge tone="ok" icon={<ShieldCheck className="size-3.5" />}>A trecut de zid</Badge>}
            {(letter.cmp_checks ?? []).map((c) => {
              const bad = /missing|unanswered/i.test(c.outcome);
              return (
                <span key={c.rule_id} className="inline-flex items-center gap-1 text-[0.8667rem] text-muted" title={c.explanation}>
                  {bad ? <X className="size-3.5 text-danger" /> : <Check className="size-3.5 text-ok" />}
                  {c.rule_id === "CMP-01" ? "răspunde la fiecare punct" : c.rule_id === "CMP-03" ? "include ANPC, ANAF, BNR, CSALB" : c.rule_id === "CMP-02" ? "termen de răspuns" : c.outcome}
                  <span className="font-mono text-[0.75rem]">{c.rule_id}</span>
                </span>
              );
            })}
          </div>
          {blocked && (
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-md border border-danger-line bg-danger-soft px-4 py-3">
              <p className="min-w-[14rem] flex-1 text-[0.9333rem]">
                <span className="font-semibold">Scrisoarea nu pleacă.</span> {letter.filter?.reasons?.[0] ?? "Fraza marcată e interzisă."}
              </p>
              <Button size="sm" onClick={editLetter}>Corectează</Button>
            </div>
          )}
          <article className="rounded-md border border-line bg-canvas px-5 py-4">
            <p className="font-semibold">{letter.subject}</p>
            <div className="mt-3 max-w-[70ch] text-[0.9333rem] leading-relaxed whitespace-pre-wrap text-ink-soft"><Highlighted text={letter.body} spans={letterSpans} /></div>
          </article>
          {letter.cites?.length ? <p className="mt-2 text-[0.8667rem] text-muted">Probe citate: <Cites ids={letter.cites.slice(0, 8)} onCite={onCite} /></p> : null}
        </div>
      )}

      <div>
        <p className="font-semibold">Testează zidul</p>
        <p className="mt-0.5 text-[0.9333rem] text-muted">Scrie o frază care pomenește investigația AML și vezi dacă trece.</p>
        <label htmlFor="wall-test" className="sr-only">Textul de verificat</label>
        <textarea id="wall-test" value={draft} onChange={(e) => setDraft(e.target.value)} rows={Math.min(14, Math.max(3, Math.ceil(draft.length / 90) + draft.split("\n").length - 1))}
          className="mt-3 w-full rounded-md border border-line-strong bg-paper px-3 py-2 text-[0.9333rem] focus:border-ink" />
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <Button size="sm" busy={busy} onClick={check} disabled={!draft.trim()}>Verifică textul</Button>
          {error && <span className="text-[0.9333rem] text-danger">{error}</span>}
        </div>
        {result && <div className="mt-3"><FilterVerdict result={result} text={checked} /></div>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- recuperarea

export const RECALL_KIND: Record<string, string> = {
  interna: "Rechemare internă: beneficiarul are cont la Banca Demo",
  "camt.056": "Rechemare SEPA camt.056, motiv FRAD",
  rechemare_ron: "Rechemare către banca beneficiarului (RON)",
};

export function RecoverySection({ d }: { d: CaseDetail }) {
  const r = d.recovery;
  const escroc = d.decisions?.find((x) => x.question === "recuperare_escroc");
  const client = d.decisions?.find((x) => x.question === "recuperare_client");
  if (!escroc && !r?.chargeback && !r?.recall && !r?.dnsc_report && !d.aml_referral?.status) {
    return <p className="text-[0.9333rem] text-muted">Recuperarea pornește după rambursare.</p>;
  }
  const cb = r?.chargeback;
  return (
    <div className="flex flex-col gap-4">
      <KeyValues rows={[
        escroc ? ["De la escroc", <span>{verdictLabel(escroc.decision)} <span className="font-mono text-[0.75rem] text-muted">{escroc.rule_ids?.join(" · ")}</span></span>] : null,
        client ? ["De la client", <span>{verdictLabel(client.decision)} <span className="font-mono text-[0.75rem] text-muted">{client.rule_ids?.join(" · ")}</span></span>] : null,
        ["Chargeback", cb ? (cb.eligible ? `posibil, cod ${cb.reason_code ?? "—"}` : "nu se aplică") : "nu se aplică"],
        r?.recall ? ["Rechemare", RECALL_KIND[String(r.recall.kind)] ?? String(r.recall.kind)] : null,
        r?.dnsc_report ? ["Raport DNSC", r.dnsc_report.status ?? "ciornă"] : null,
      ]} />
      {cb?.explanation && <p className="text-[0.8667rem] text-muted">{cb.explanation}</p>}
      {r?.recall?.note && <p className="text-[0.8667rem] text-muted">{r.recall.note}</p>}
      <div className="flex flex-col gap-2">
        {r?.recall?.xml && (
          <details className="rounded-md border border-line">
            <summary className="cursor-pointer px-3 py-2 text-[0.9333rem] font-medium">Mesajul camt.056 (ciornă)</summary>
            <pre className="max-h-56 overflow-auto border-t border-line bg-canvas p-3 text-[0.75rem] leading-snug">{r.recall.xml}</pre>
          </details>
        )}
        {r?.dnsc_report && (
          <details className="rounded-md border border-line">
            <summary className="cursor-pointer px-3 py-2 text-[0.9333rem] font-medium">Raportul de phishing pentru DNSC (ciornă)</summary>
            <div className="border-t border-line px-3 py-3">
              <p className="font-semibold">{r.dnsc_report.title}</p>
              <p className="mt-1 text-[0.9333rem] whitespace-pre-wrap text-ink-soft">{r.dnsc_report.text}</p>
            </div>
          </details>
        )}
      </div>
      {d.aml_referral?.status && (
        <p className="text-[0.8667rem] text-muted">
          Faptele despre beneficiar au plecat spre zona AML ({d.aml_referral.status}). Victima apare acolo doar ca <span className="font-mono">{d.aml_referral.victim_ref}</span>.
        </p>
      )}
      <p className="text-[0.8667rem] text-muted">Toate sunt ciorne. Le trimite un om.</p>
    </div>
  );
}

// ---------------------------------------------------------------- registrul

export function LedgerSection({ caseId, sealed, count, root }: { caseId: string; sealed: boolean; count: number; root?: string | null }) {
  const api = useApi();
  const [ledger, setLedger] = useState<LedgerResponse | null>(null);
  const [verify, setVerify] = useState<VerifyResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function check() {
    setBusy(true);
    setError(null);
    try {
      const l = await api.ledger(caseId);
      setLedger(l);
      setVerify(l.seal ? await api.verify({ case_id: caseId, facts: l.facts, seal: l.seal }) : l.verify);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Verificarea nu a răspuns.");
    } finally {
      setBusy(false);
    }
  }
  const qr = ledger?.seal?.qr_svg;
  const shownRoot = ledger?.seal?.root ?? root;
  return (
    <div className="flex flex-wrap items-start gap-6">
      <div className="min-w-[16rem] flex-1">
        <KeyValues rows={[
          ["Probe", <span className="tabular-nums">{count}</span>],
          ["Sigilat", sealed ? "da (Merkle + Ed25519)" : "încă nu; se sigilează la final"],
          shownRoot ? ["Rădăcina", <span className="font-mono text-[0.8rem]" title={shownRoot}>{shortHash(shownRoot, 16)}</span>] : null,
        ]} />
        <Button className="mt-4" size="sm" busy={busy} onClick={check}>Verifică dosarul</Button>
        {error && <p className="mt-2 text-[0.9333rem] text-danger">{error}</p>}
        {verify && (
          <div className="mt-4">
            <p className={cx("flex items-center gap-2 font-semibold", verify.valid ? "text-ok" : "text-danger")}>
              {verify.valid ? <><ShieldCheck className="size-4" /> Dosarul e intact.</> : <><ShieldAlert className="size-4" /> {sealed ? "Dosarul nu se verifică." : "Dosarul nu e sigilat încă."}</>}
            </p>
            <ul className="mt-2 flex flex-col gap-1 text-[0.8667rem] text-ink-soft">
              {verify.checks.map((c, i) => (
                <li key={i} className="flex items-start gap-1.5">{c.ok ? <Check className="mt-0.5 size-3.5 shrink-0 text-ok" /> : <X className="mt-0.5 size-3.5 shrink-0 text-danger" />}<span>{c.name}</span></li>
              ))}
            </ul>
          </div>
        )}
      </div>
      {qr && <img className="size-32 rounded-md border border-line p-2" alt="Cod QR cu rădăcina semnată a dosarului" src={`data:image/svg+xml;utf8,${encodeURIComponent(qr)}`} />}
    </div>
  );
}

// ---------------------------------------------------------------- reclamația

export function ComplaintBlock({ d }: { d: CaseDetail }) {
  const c = d.complaint;
  if (!c) return null;
  const injection = d.extracted?.injection_suspected;
  return (
    <div className="flex flex-col gap-3">
      {injection && (
        <p className="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-[0.9333rem] text-danger">
          <ShieldAlert className="mt-0.5 size-4 shrink-0" /> Reclamația conține instrucțiuni către sistem. Agenții le-au tratat ca text și le-au ignorat.
        </p>
      )}
      <blockquote className="border-l border-line-strong pl-4 text-[0.9333rem] whitespace-pre-wrap text-ink-soft">{c.text || <span className="text-muted">Fără text.</span>}</blockquote>
      {c.attachments?.map((a, i) => (
        <div key={i} className="rounded-md bg-canvas px-3 py-2 text-[0.9333rem]">
          <p className="text-[0.8rem] text-muted">{a.kind === "sms" ? "SMS primit" : a.kind}</p>
          <p className="whitespace-pre-wrap">{a.content}</p>
        </div>
      ))}
      {d.extracted?.points?.length ? (
        <div>
          <p className="text-[0.8667rem] text-muted">Ce întreabă clientul</p>
          <ul className="mt-1 list-disc pl-5 text-[0.9333rem]">{d.extracted.points.map((p, i) => <li key={i}>{p.text}</li>)}</ul>
        </div>
      ) : null}
    </div>
  );
}

export function NoData({ children }: { children: ReactNode }) {
  return <EmptyState title={children} />;
}
