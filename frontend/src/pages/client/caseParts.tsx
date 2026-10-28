/**
 * Piesele camerei de caz (semnătura, probe, reguli, scrisoarea și zidul, recuperarea, dosarul, reclamația).
 * Camera în sine e în CaseRoom.tsx.
 */
import { AlertTriangle, Check, Hand, ShieldAlert, ShieldCheck, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { shortHash, verdictLabel } from "../../api/format";
import { useApi } from "../../api/runtime";
import type { CaseDetail, Fact, FilterResult, LedgerResponse, VerifyResult } from "../../api/types";
import { Badge, Banner, Button, cx, DeadlineText, EmptyState, IdTag, KeyValues, Panel } from "../../ui/kit";
import { exactTime } from "./caseUi";

// ---------------------------------------------------------------- semnătura

const SIGN_COPY: Record<string, { yes: string; no: string; consequence: string }> = {
  RAMBURSEAZA_CU_APROBARE: { yes: "Aprobă rambursarea", no: "Nu aprob", consequence: "La aprobare, motorul de reguli emite imediat instrucțiunea de rambursare." },
  RESPINGE_TARDIV: { yes: "Confirm respingerea", no: "Nu confirm, rambursăm", consequence: "Clientul primește o scrisoare de respingere cu temeiul legal și căile de atac." },
  EXCEPTIE_FRAUDA_CLIENT: { yes: "Confirm excepția", no: "Nu confirm, rambursăm", consequence: "Nu rambursăm acum. Folosește excepția doar dacă autoritatea a fost notificată." },
};

export function SignatureBanner({ d, caseId, onDone }: { d: CaseDetail; caseId: string; onDone: () => Promise<void> }) {
  const api = useApi();
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const it = d.interrupt!;
  const copy = SIGN_COPY[String(it.verdict)] ?? { yes: "Aprobă", no: "Respinge", consequence: "Decizia se aplică imediat." };
  const locked = Boolean(it.resuming) || busy !== null;
  async function act(action: "approve" | "reject") {
    setBusy(action);
    setError(null);
    try {
      await api.approve(caseId, { action, approver: "OPERATOR-01" });
      await onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Semnătura nu a fost înregistrată.");
    } finally {
      setBusy(null);
    }
  }
  return (
    <Banner
      tone="now"
      icon={<Hand aria-hidden className="size-5" />}
      title={it.prompt ?? "Decizia cere semnătura ta."}
      actions={<>
        <Button variant="primary" busy={busy === "approve"} disabled={locked} onClick={() => act("approve")}>{copy.yes}</Button>
        <Button busy={busy === "reject"} disabled={locked} onClick={() => act("reject")}>{copy.no}</Button>
      </>}
    >
      {it.resuming ? "Semnătura a fost primită; aplic decizia…" : copy.consequence}
      {it.rule_ids?.length ? <span className="ml-1">Reguli: {it.rule_ids.join(", ")}.</span> : null}
      {error && <span className="mt-1 block font-semibold text-danger">{error}</span>}
    </Banner>
  );
}

// ---------------------------------------------------------------- decizia

export function Cites({ ids, onCite }: { ids?: string[]; onCite: (id: string) => void }) {
  if (!ids?.length) return null;
  return (
    <span className="ml-1 inline-flex flex-wrap gap-1 align-middle">
      {ids.map((c) => <IdTag key={c} onClick={() => onCite(c)} title={`Arată proba ${c}`}>{c}</IdTag>)}
    </span>
  );
}

export function Arguments({ title, model, lines, onCite }: { title: string; model?: string; lines?: Array<{ text: string; cites?: string[] }>; onCite: (id: string) => void }) {
  return (
    <div>
      <p className="font-semibold">{title}{model && <span className="ml-2 text-[0.8rem] font-normal text-muted">{model.replace("anthropic.", "")}</span>}</p>
      {lines?.length ? (
        <ul className="mt-2 flex flex-col gap-2">
          {lines.map((l, i) => <li key={i} className="text-ink-soft">{l.text}<Cites ids={l.cites} onCite={onCite} /></li>)}
        </ul>
      ) : <p className="mt-2 text-muted">Fără argumente.</p>}
    </div>
  );
}

// ---------------------------------------------------------------- probe

export function trustLabel(f: Fact): ReactNode {
  return f.labels?.trust === "untrusted"
    ? <span className="inline-flex items-center gap-1.5"><AlertTriangle className="size-3.5 text-danger" /> neîncrezut</span>
    : <span className="inline-flex items-center gap-1.5"><ShieldCheck className="size-3.5 text-ok" /> sistemele băncii</span>;
}

export function EvidenceTab({ facts, flash }: { facts: Fact[]; flash: string | null }) {
  if (!facts.length) return <EmptyState title="Nicio probă încă.">Colectorii scriu probele aici pe măsură ce le găsesc, fiecare cu sursă, oră și hash.</EmptyState>;
  return (
    <div className="overflow-x-auto rounded-lg border border-line">
      <table className="w-full table-fixed border-collapse text-left sm:min-w-[36rem]">
        <thead>
          <tr className="border-b border-line bg-canvas text-[0.8667rem] text-muted">
            <th scope="col" className="w-24 px-3 py-2.5 font-semibold">ID</th>
            <th scope="col" className="px-3 py-2.5 font-semibold">Ce arată și de unde vine</th>
            <th scope="col" className="hidden w-40 px-3 py-2.5 font-semibold sm:table-cell">Încredere</th>
            <th scope="col" className="hidden w-28 px-3 py-2.5 font-semibold sm:table-cell">Hash</th>
          </tr>
        </thead>
        <tbody>
          {facts.map((f) => (
            <tr key={f.fact_id} id={`fact-${f.fact_id}`} className={cx("border-b border-line align-top last:border-b-0", flash === f.fact_id && "animate-flash")}>
              <td className="px-3 py-2.5"><IdTag>{f.fact_id}</IdTag></td>
              <td className="px-3 py-2.5">
                <p>{f.summary || f.kind}</p>
                <p className="mt-0.5 truncate font-mono text-[0.8rem] text-muted" title={f.source_tool}>{f.source_tool}</p>
                <p className="mt-1 text-[0.8667rem] sm:hidden">{trustLabel(f)}</p>
              </td>
              <td className="hidden px-3 py-2.5 text-[0.8667rem] whitespace-nowrap sm:table-cell">{trustLabel(f)}</td>
              <td className="hidden px-3 py-2.5 font-mono text-[0.8rem] text-muted sm:table-cell" title={f.sha256}>{shortHash(f.sha256, 8)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------- reguli și termene

export const CONFIDENCE: Record<string, string> = { P: "text oficial", S: "sursă secundară", U: "parametru neverificat", V: "verificat" };

export function RulesTab({ d }: { d: CaseDetail }) {
  const hits = d.rules?.hits ?? [];
  const deadlines = d.rules?.deadlines ?? [];
  if (!hits.length && !deadlines.length) return <EmptyState title="Regulile nu au rulat încă.">Motorul de reguli pornește după ce colectorii termină.</EmptyState>;
  return (
    <div className="flex flex-col gap-5">
      {deadlines.length > 0 && (
        <Panel title="Termene legale" bodyClassName="p-0">
          <ul>
            {deadlines.map((dl, i) => (
              <li key={i} className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-2.5 last:border-b-0">
                <span className="min-w-0"><span className="font-medium">{dl.name}</span> <span className="text-[0.8667rem] text-muted">· {dl.basis}</span></span>
                <span className="flex items-center gap-3 text-[0.9333rem]"><span className="tabular-nums text-muted">{exactTime(dl.due_at)}</span><DeadlineText deadline={dl.due_at} /></span>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="w-full min-w-[44rem] border-collapse text-left">
          <thead>
            <tr className="border-b border-line bg-canvas text-[0.8667rem] text-muted">
              <th scope="col" className="px-3 py-2.5 font-semibold">Regula</th>
              <th scope="col" className="px-3 py-2.5 font-semibold">Ce a stabilit</th>
              <th scope="col" className="px-3 py-2.5 font-semibold">Temei</th>
              <th scope="col" className="px-3 py-2.5 font-semibold">Încredere</th>
            </tr>
          </thead>
          <tbody>
            {hits.map((h, i) => (
              <tr key={`${h.rule_id}-${i}`} className="border-b border-line align-top last:border-b-0">
                <td className="px-3 py-2.5"><IdTag>{h.rule_id}</IdTag></td>
                <td className="px-3 py-2.5"><p className="font-medium">{h.title}</p>{h.explanation && <p className="mt-0.5 text-[0.9333rem] text-ink-soft">{h.explanation}</p>}</td>
                <td className="px-3 py-2.5 text-[0.9333rem] text-muted">{h.basis}</td>
                <td className="px-3 py-2.5 text-[0.9333rem] whitespace-nowrap">{CONFIDENCE[String(h.confidence)] ?? h.confidence ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- scrisoarea + încercarea de a sparge zidul

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
    parts.push(<mark key={i} className="rounded-sm bg-danger-soft px-0.5 text-danger underline decoration-2" title={s.label}>{text.slice(start, s.end)}</mark>);
    at = s.end;
  });
  parts.push(text.slice(at));
  return <>{parts}</>;
}

export function LetterTab({ d, caseId, onCite }: { d: CaseDetail; caseId: string; onCite: (id: string) => void }) {
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
      const box = document.getElementById("attack") as HTMLTextAreaElement | null;
      box?.scrollIntoView({ behavior: "smooth", block: "center" });
      box?.focus({ preventScroll: true });
    }, 60);
  }
  async function check() {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.letterCheck(caseId, { body: draft }));
      setChecked(draft);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Verificarea nu a răspuns.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex flex-col gap-5">
      {!letter ? (
        <EmptyState title="Scrisoarea nu e gata.">Redactorul o scrie după decizie și după recuperare, apoi o trece prin filtrul zidului.</EmptyState>
      ) : (
        <Panel
          title={letter.subject}
          actions={blocked
            ? <Badge tone="danger" icon={<ShieldAlert className="size-3.5" />}>Blocată de zid</Badge>
            : <Badge tone="ok" icon={<ShieldCheck className="size-3.5" />}>A trecut filtrul zidului</Badge>}
        >
          {blocked && (
            <div className="mb-4 flex flex-wrap items-start justify-between gap-3 rounded-md border border-danger-line bg-danger-soft px-4 py-3">
              <div className="min-w-[16rem] flex-1">
                <p className="font-semibold">Scrisoarea nu pleacă: fraza marcată mai jos e interzisă.</p>
                {letter.filter?.reasons?.[0] && <p className="mt-1 text-[0.9333rem] text-ink-soft">{letter.filter.reasons[0]}</p>}
              </div>
              <Button onClick={editLetter}>Corectează și verifică din nou</Button>
            </div>
          )}
          <div className="max-w-[72ch] whitespace-pre-wrap leading-relaxed"><Highlighted text={letter.body} spans={letterSpans} /></div>
          <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 border-t border-line pt-3 text-[0.9333rem]">
            {(letter.cmp_checks ?? []).map((c) => (
              <span key={c.rule_id} className="inline-flex items-center gap-1.5">
                {c.outcome.toLowerCase().includes("missing") || c.outcome.toLowerCase().includes("unanswered")
                  ? <X className="size-4 text-danger" /> : <Check className="size-4 text-ok" />}
                <IdTag>{c.rule_id}</IdTag>
                {c.rule_id === "CMP-01" ? "răspunde la fiecare punct" : c.rule_id === "CMP-03" ? "include ANPC, ANAF, BNR și CSALB" : c.outcome}
              </span>
            ))}
            {letter.cites?.length ? <span className="inline-flex items-center gap-1.5 text-muted">Se sprijină pe <Cites ids={letter.cites.slice(0, 6)} onCite={onCite} /></span> : null}
          </div>
        </Panel>
      )}

      <Panel title="Verifică un text prin zid">
        <p className="text-ink-soft">Corectează scrisoarea aici sau încearcă să strecori o referire la o investigație AML. Filtrul verifică termenii interziși, tokenurile canary și datele personale.</p>
        <label htmlFor="attack" className="sr-only">Textul de verificat</label>
        <textarea id="attack" value={draft} onChange={(e) => setDraft(e.target.value)} rows={Math.min(16, Math.max(3, Math.ceil(draft.length / 90) + draft.split("\n").length - 1))}
          className="mt-3 w-full rounded-md border border-line-strong bg-paper px-3 py-2 focus:border-ink" />
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button variant="primary" busy={busy} onClick={check} disabled={!draft.trim()}>Verifică textul</Button>
          {error && <span className="text-danger">{error}</span>}
        </div>
        {result && (
          <div className={cx("mt-4 rounded-md border px-4 py-3", result.passed ? "border-ok-line bg-ok-soft" : "border-danger-line bg-danger-soft")} role="status">
            <p className="flex items-center gap-2 font-semibold">
              {result.passed ? <><ShieldCheck className="size-4 text-ok" /> Textul poate pleca: nimic interzis.</> : <><ShieldAlert className="size-4 text-danger" /> Blocat: textul nu pleacă, merge la un om.</>}
            </p>
            {!result.passed && <p className="mt-2 leading-relaxed"><Highlighted text={checked} spans={result.term_spans?.length ? result.term_spans : spansFromTerms(checked, result.blocked_terms)} /></p>}
            {result.reasons?.length ? <ul className="mt-2 list-disc pl-5 text-[0.9333rem]">{result.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul> : null}
          </div>
        )}
      </Panel>
    </div>
  );
}

// ---------------------------------------------------------------- coloana din dreapta

export const RECALL_KIND: Record<string, string> = {
  interna: "Rechemare internă (beneficiarul are cont la Banca Demo)",
  "camt.056": "Rechemare SEPA camt.056, motiv FRAD",
  rechemare_ron: "Rechemare către banca beneficiarului (RON)",
};

export function RecoveryPanel({ d }: { d: CaseDetail }) {
  const r = d.recovery;
  const escroc = d.decisions?.find((x) => x.question === "recuperare_escroc");
  if (!escroc && !r?.chargeback && !r?.recall && !r?.dnsc_report && !d.aml_referral?.status) return null;
  return (
    <Panel title="Recuperarea banilor">
      <div className="flex flex-col gap-3">
        {escroc && <p><span className="font-semibold">{verdictLabel(escroc.decision)}</span> <span className="font-mono text-[0.8rem] text-muted">{escroc.rule_ids?.join(" · ")}</span></p>}
        {r?.chargeback && (
          <p className="text-[0.9333rem]">
            <span className="font-medium">Chargeback: </span>
            {r.chargeback.eligible ? `posibil, cod ${r.chargeback.reason_code ?? "—"}` : "nu e posibil"}
            {r.chargeback.explanation && <span className="block text-muted">{r.chargeback.explanation}</span>}
          </p>
        )}
        {r?.recall && (
          <div className="text-[0.9333rem]">
            <p className="font-medium">{RECALL_KIND[String(r.recall.kind)] ?? r.recall.kind}</p>
            {r.recall.note && <p className="text-muted">{r.recall.note}</p>}
            {r.recall.xml && (
              <details className="mt-1.5">
                <summary className="cursor-pointer font-medium underline">Mesajul camt.056 (ciornă)</summary>
                <pre className="mt-2 max-h-56 overflow-auto rounded-md bg-canvas p-3 text-[0.75rem] leading-snug">{r.recall.xml}</pre>
              </details>
            )}
          </div>
        )}
        {r?.dnsc_report && (
          <details className="text-[0.9333rem]">
            <summary className="cursor-pointer font-medium underline">Raport de phishing pentru DNSC (ciornă)</summary>
            <p className="mt-2 font-semibold">{r.dnsc_report.title}</p>
            <p className="mt-1 whitespace-pre-wrap text-ink-soft">{r.dnsc_report.text}</p>
          </details>
        )}
        {d.aml_referral?.status && (
          <p className="border-t border-line pt-3 text-[0.9333rem] text-muted">
            Faptele despre atac au plecat spre zona AML, într-un singur sens ({d.aml_referral.status}). Victima apare acolo doar ca <span className="font-mono">{d.aml_referral.victim_ref}</span>.
          </p>
        )}
        <p className="text-[0.8667rem] text-muted">Toate sunt ciorne: le trimite un om.</p>
      </div>
    </Panel>
  );
}

export function LedgerPanel({ caseId, sealed, count }: { caseId: string; sealed: boolean; count: number }) {
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
  return (
    <Panel title="Dosarul de probe">
      <KeyValues rows={[
        ["Probe", <span className="tabular-nums">{count}</span>],
        ["Sigilat", sealed ? "da, Merkle + Ed25519" : "încă nu (la final)"],
        ledger?.seal ? ["Rădăcina", <span className="font-mono text-[0.8rem]" title={ledger.seal.root}>{shortHash(ledger.seal.root, 12)}</span>] : null,
      ]} />
      <Button className="mt-3" size="sm" busy={busy} onClick={check}>Verifică integritatea</Button>
      {error && <p className="mt-2 text-[0.9333rem] text-danger">{error}</p>}
      {verify && (
        <div className="mt-3">
          <p className={cx("flex items-center gap-2 font-semibold", verify.valid ? "text-ok" : "text-danger")}>
            {verify.valid ? <><ShieldCheck className="size-4" /> Dosar intact</> : <><ShieldAlert className="size-4" /> {sealed ? "Nu se verifică" : "Nesigilat încă"}</>}
          </p>
          <ul className="mt-1.5 flex flex-col gap-1 text-[0.8667rem]">
            {verify.checks.map((c, i) => (
              <li key={i} className="flex items-start gap-1.5">{c.ok ? <Check className="mt-0.5 size-3.5 shrink-0 text-ok" /> : <X className="mt-0.5 size-3.5 shrink-0 text-danger" />}<span>{c.name}</span></li>
            ))}
          </ul>
          {qr && <img className="mt-3 size-28" alt="Cod QR cu rădăcina semnată a dosarului" src={`data:image/svg+xml;utf8,${encodeURIComponent(qr)}`} />}
        </div>
      )}
    </Panel>
  );
}

export function ComplaintPanel({ d }: { d: CaseDetail }) {
  const c = d.complaint;
  if (!c) return null;
  const injection = d.extracted?.injection_suspected;
  return (
    <Panel title="Reclamația clientului">
      {injection && (
        <p className="mb-3 flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-[0.9333rem] text-danger">
          <ShieldAlert className="mt-0.5 size-4 shrink-0" /> Conține instrucțiuni către sistem. Au fost tratate ca date și ignorate.
        </p>
      )}
      <details>
        <summary className="cursor-pointer list-none">
          <p className="line-clamp-3 text-ink-soft">{c.text}</p>
          <span className="mt-1 inline-block text-[0.8667rem] font-medium underline">Arată tot</span>
        </summary>
        <p className="mt-2 whitespace-pre-wrap text-ink-soft">{c.text}</p>
        {c.attachments?.map((a, i) => (
          <div key={i} className="mt-3 rounded-md bg-canvas px-3 py-2 text-[0.9333rem]">
            <p className="text-[0.8rem] font-semibold text-muted">{a.kind === "sms" ? "SMS primit" : a.kind}</p>
            <p className="whitespace-pre-wrap">{a.content}</p>
          </div>
        ))}
      </details>
      {d.extracted?.points?.length ? (
        <div className="mt-3 border-t border-line pt-3">
          <p className="text-[0.8667rem] font-semibold text-muted">Ce cere clientul</p>
          <ul className="mt-1 list-disc pl-5 text-[0.9333rem]">{d.extracted.points.map((p, i) => <li key={i}>{p.text}</li>)}</ul>
        </div>
      ) : null}
    </Panel>
  );
}
