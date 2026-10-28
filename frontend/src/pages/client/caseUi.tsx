import { useMemo } from "react";
import { money, scenarioLabel as baseScenarioLabel } from "../../api/format";
import type { AgentEvent, CaseDetail, Decision, Money, PipelineNode } from "../../api/types";
import { matchNode, normalizeStatus, STAGE_BY_ID } from "../../lib/pipeline";
import { Badge, cx, Dot, dueText, StepIcon, STEP_STATUS_LABEL, type Tone } from "../../ui/kit";

// ---------------------------------------------------------------- un singur set de stări, în toată aplicația

export interface StatusView {
  label: string;
  tone: Tone;
  live?: boolean;
  group: "you" | "running" | "closed";
}

export function caseStatus(status: string | null | undefined, requiresHuman = false): StatusView {
  switch (status) {
    case "ASTEAPTA_APROBARE":
      return { label: "Așteaptă semnătura ta", tone: "now", group: "you" };
    case "NOU":
      return { label: "Nou", tone: "neutral", group: "running" };
    case "IN_ANALIZA":
      return { label: "Agenții lucrează", tone: "neutral", live: true, group: "running" };
    case "RAMBURSAT":
      return { label: "Rambursat", tone: "ok", group: "closed" };
    case "TRASEU_APP":
      // plata a fost autorizată de client: nu e nimic de semnat aici, dar rechemarea o trimite un om
      return requiresHuman
        ? { label: "Rechemare de trimis", tone: "neutral", group: "running" }
        : { label: "Recuperare pornită", tone: "neutral", group: "closed" };
    case "RESPINS":
      return { label: "Respins", tone: "neutral", group: "closed" };
    case "EXCEPTIE":
      return { label: "Excepție semnată", tone: "danger", group: "closed" };
    case "INCHIS":
      return { label: "Închis", tone: "neutral", group: "closed" };
    case "EROARE":
      return { label: "Eroare", tone: "danger", group: "you" };
    default:
      return { label: status ?? "—", tone: "neutral", group: "running" };
  }
}

/** Starea ca pastilă: un cuvânt și o culoare. */
export function StatusPill({ status, requiresHuman }: { status?: string | null; requiresHuman?: boolean }) {
  const s = caseStatus(status, requiresHuman);
  return (
    <Badge tone={s.tone}>
      {s.live && <Dot tone="now" live />}
      {s.label}
    </Badge>
  );
}

export function StatusLine({ status, requiresHuman }: { status?: string | null; requiresHuman?: boolean }) {
  const s = caseStatus(status, requiresHuman);
  return (
    <span className="inline-flex items-center gap-2 whitespace-nowrap">
      <Dot tone={s.tone} live={s.live} />
      {s.label}
    </span>
  );
}

/** Ce s-a întâmplat, într-o expresie scurtă, cum ar spune-o un operator. */
const WHAT: Record<string, string> = {
  demo_t1: "Link fals de curier",
  demo_t1_victima2: "Transfer într-un „cont sigur”",
  phishing_link: "Link fals de curier",
  card_ecom_fara_3ds: "Card folosit online, fără 3DS",
  card_visa_secure: "Plată online cu Visa Secure",
  vishing_securitate: "Apel fals „de la securitate”",
  cont_sigur: "Transfer într-un „cont sigur”",
  sim_swap: "SIM schimbat de escroc",
  frauda_client: "Posibilă fraudă a clientului",
  reclamatie_tardiva: "Contestație după 13 luni",
  plata_dubla: "Plată dublă",
  inel_carausi: "Inel de cărăuși",
  injectie_document: "Reclamație cu instrucțiuni ascunse",
  marfa_nelivrata: "Marfă nelivrată",
};

export function scenarioLabel(s: string | null | undefined): string {
  if (!s) return "—";
  return WHAT[s] ?? baseScenarioLabel(s);
}

export function exactTime(v: string | null | undefined): string {
  if (!v) return "—";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat("ro-RO", { timeZone: "Europe/Bucharest", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }).format(d);
}

/** Păstrat pentru paginile vechi: „azi 23:59”, „mâine 23:59”. */
export function whenPhrase(v: string | null | undefined, now = Date.now()): string {
  return dueText(v, now);
}

// ---------------------------------------------------------------- decizia, într-o propoziție

export interface VerdictView {
  /** Propoziția principală: ce se întâmplă cu banii. */
  title: string;
  /** Cine a decis sau ce se așteaptă. */
  who: string;
  tone: Tone;
}

export function verdictSentence(
  d: Decision | undefined,
  amount: Money | null | undefined,
  after?: { status?: string; action?: string; approver?: string; pending?: boolean },
): VerdictView {
  const sum = money(amount ?? d?.amount ?? null);
  const due = d?.deadline ? ` Termen: ${dueText(d.deadline)}.` : "";
  const who = after?.approver ?? "un operator";
  if (d && after?.status === "RAMBURSAT") {
    return {
      title: `Am rambursat ${sum}, în termen.`,
      who: d.decision === "RAMBURSEAZA" ? "Regulile, automat" : `Semnat de ${who}`,
      tone: "ok",
    };
  }
  if (after?.pending) {
    switch (d?.decision) {
      case "RAMBURSEAZA_CU_APROBARE":
        return { title: `Rambursăm ${sum} după semnătura ta.${due}`, who: "Așteaptă semnătura ta", tone: "now" };
      case "RESPINGE_TARDIV":
        return { title: "Respingem contestația: a venit după 13 luni.", who: "Așteaptă semnătura ta", tone: "now" };
      case "EXCEPTIE_FRAUDA_CLIENT":
        return { title: "Nu rambursăm acum: suspiciune de fraudă a clientului.", who: "Așteaptă semnătura ta", tone: "now" };
      default:
        break;
    }
  }
  if (d?.decision === "RAMBURSEAZA_CU_APROBARE" && after?.action === "reject") {
    return { title: "Nu ai aprobat rambursarea. Termenul T+1 curge în continuare.", who: `Respins de ${who}`, tone: "danger" };
  }
  if (d?.decision === "RESPINGE_TARDIV" && after?.status === "RESPINS") {
    return { title: "Am respins contestația: a venit după 13 luni.", who: `Semnat de ${who}`, tone: "neutral" };
  }
  if (d?.decision === "EXCEPTIE_FRAUDA_CLIENT" && after?.status === "EXCEPTIE") {
    return { title: "Nu rambursăm: excepție de fraudă a clientului.", who: `Semnat de ${who}`, tone: "danger" };
  }
  switch (d?.decision) {
    case "RAMBURSEAZA":
      return { title: `Rambursăm ${sum}.${due}`, who: "Regulile, automat", tone: "ok" };
    case "RAMBURSEAZA_CU_APROBARE":
      return { title: `Rambursăm ${sum} după semnătura ta.${due}`, who: "Așteaptă semnătura ta", tone: "now" };
    case "NU_SE_APLICA_T1":
      return { title: "Clientul a autorizat plata. Nu rambursăm la T+1; cerem banii înapoi de la banca beneficiarului.", who: d.requires_human ? "Regulile. Rechemarea o trimiți tu." : "Regulile, automat", tone: "neutral" };
    case "RESPINGE_TARDIV":
      return { title: "Respingem contestația: a venit după 13 luni.", who: "Semnează un operator", tone: "danger" };
    case "EXCEPTIE_FRAUDA_CLIENT":
      return { title: "Nu rambursăm acum: suspiciune de fraudă a clientului.", who: "Semnează un operator", tone: "danger" };
    case "INFORMATII_SUPLIMENTARE":
      return { title: `Cerem clientului informațiile care lipsesc.${due}`, who: "Regulile, automat", tone: "neutral" };
    default:
      return { title: "Agenții strâng probele. Decizia apare aici.", who: "În lucru", tone: "neutral" };
  }
}

// ---------------------------------------------------------------- motivele, în cuvinte simple

export interface Reason {
  text: string;
  rule?: string;
  cites?: string[];
}

const ctxNum = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : null);

function minutes(sec: number): string {
  if (sec < 90) return `${Math.round(sec)} secunde`;
  const m = Math.round(sec / 60);
  return m === 1 ? "un minut" : `${m} minute`;
}

/**
 * Cel mult trei motive scurte, scrise din faptele pe care le-au folosit regulile (rule_context și rezultatele regulilor).
 * Nu inventăm nimic: fiecare frază corespunde unui câmp sau unui rezultat de regulă, cu ID-ul lui.
 */
export function plainReasons(d: CaseDetail): Reason[] {
  const t1 = d.decisions?.find((x) => x.question === "rambursare_t1");
  if (!t1) return [];
  const ctx = (d.rule_context ?? {}) as Record<string, unknown>;
  const ids = (ctx.fact_ids ?? {}) as Record<string, string>;
  const hits = new Map((d.rules?.hits ?? []).map((h) => [h.rule_id, h]));
  const out: Reason[] = [];
  const cite = (...keys: string[]) => keys.map((k) => ids[k]).filter(Boolean);

  if (t1.decision === "RESPINGE_TARDIV") {
    out.push({ text: "Clientul a contestat după termenul legal de 13 luni.", rule: "PAY-01", cites: cite("notified_at", "executed_at") });
  }
  if (t1.decision === "NU_SE_APLICA_T1" || ctx.client_admits_approving_in_app === true) {
    out.push({ text: "Clientul spune că a aprobat singur plata în aplicație.", cites: cite("client_admits_approving_in_app") });
  }
  if (t1.decision === "EXCEPTIE_FRAUDA_CLIENT") {
    out.push({ text: "Regulile au găsit semnale de fraudă a clientului.", cites: cite("client_fraud_score", "prior_disputes_12m") });
  }
  if (ctx.device_known === false) {
    const sec = ctxNum(ctx.seconds_after_click);
    out.push({
      text: sec !== null ? `Plata a pornit de pe un telefon nou, la ${minutes(sec)} după click pe link.` : "Plata a pornit de pe un telefon nou.",
      cites: cite("device_known"),
    });
  }
  const sim = ctxNum(ctx.sim_swap_hours_before);
  if (sim !== null) out.push({ text: `Cartela SIM a fost schimbată cu ${sim} h înainte de plată.` });
  if (ctx.screen_showed_amount_and_payee === false) {
    out.push({ text: "Ecranul de autentificare nu a arătat suma și beneficiarul.", rule: hits.has("PAY-08") ? "PAY-08" : undefined, cites: cite("screen_showed_amount_and_payee") });
  }
  const cap = hits.get("DSP-59");
  if (cap) {
    const over = cap.outcome === "DSP_AMOUNT_REVIEW";
    out.push({ text: over ? "Suma trece de plafonul de rambursare automată: semnează un om." : "Suma e sub plafonul de rambursare automată.", rule: "DSP-59", cites: cite("amount") });
  }
  const risk = hits.get("URM-03");
  if (risk?.outcome === "fara_semnale") out.push({ text: "Clientul nu are semnale de risc.", rule: "URM-03", cites: cite("client_fraud_score") });
  if (risk?.outcome === "semnale_de_risc") out.push({ text: "Clientul are semnale de risc: decide un om, tot în termen.", rule: "URM-03", cites: cite("client_fraud_score", "prior_disputes_12m") });
  const inTime = hits.get("PAY-01");
  if (inTime && /in_termen/i.test(inTime.outcome) && t1.decision !== "RESPINGE_TARDIV") out.push({ text: "Clientul a contestat în termenul de 13 luni.", rule: "PAY-01", cites: cite("notified_at") });

  if (!out.length) {
    for (const r of t1.rationale ?? []) {
      const first = r.text.split(/(?<=[.:])\s/)[0];
      out.push({ text: first.length > 140 ? `${first.slice(0, 137)}…` : first, cites: r.cites });
    }
  }
  // întâi motivul care schimbă ce faci tu (semnale de risc, plafon depășit), apoi restul
  const weight = (r: Reason) => (/semnale de risc:|trece de plafon|aprobat singur|după termenul|fraudă/.test(r.text) ? 0 : 1);
  return out.map((r, i) => ({ r, i })).sort((a, b) => weight(a.r) - weight(b.r) || a.i - b.i).map((x) => x.r).slice(0, 3);
}

// ---------------------------------------------------------------- pașii agenților

export function modelName(m: string | null | undefined): string {
  const s = (m ?? "").toLowerCase();
  if (s.includes("opus")) return "Opus";
  if (s.includes("sonnet")) return "Sonnet";
  if (s.includes("haiku")) return "Haiku";
  if (s === "ml") return "ML";
  return "Reguli";
}

export interface StepRow {
  id: string;
  label: string;
  model: string;
  status: string;
  summary?: string;
  hint?: string;
  start?: number;
  end?: number;
}

function ms(v: string | null | undefined): number | undefined {
  if (!v) return undefined;
  const t = new Date(v).getTime();
  return Number.isNaN(t) ? undefined : t;
}

/** Starea fiecărui pas: întâi ce a salvat serverul, apoi ce au adus evenimentele live. */
export function useStepRows(nodes: PipelineNode[] | undefined, events: AgentEvent[]): StepRow[] {
  return useMemo(() => {
    const rows = new Map<string, StepRow>();
    for (const n of nodes ?? []) {
      rows.set(n.id, {
        id: n.id, label: STAGE_BY_ID[n.id]?.label ?? n.label, model: modelName(n.model), status: normalizeStatus(n.status),
        summary: n.summary, hint: n.hint, start: ms(n.started_at), end: ms(n.finished_at),
      });
    }
    for (const e of events) {
      if (e.type === "RUN_STARTED") {
        for (const r of rows.values()) Object.assign(r, { status: "idle", start: undefined, end: undefined, summary: undefined });
        continue;
      }
      const id = matchNode([...rows.values()].map((r) => ({ id: r.id, label: r.label, agent: undefined })), e);
      if (!id) continue;
      const r = rows.get(id)!;
      const t = ms(e.ts);
      if (e.type === "STEP_STARTED") {
        r.status = r.status === "done" ? r.status : "running";
        r.start = r.start ?? t;
      } else if (e.type === "STEP_FINISHED") {
        const declared = typeof e.data?.status === "string" ? normalizeStatus(e.data.status as string) : "done";
        r.status = declared === "idle" ? "done" : declared;
        r.end = t;
        if (e.message) r.summary = e.message;
      } else if (e.type === "CUSTOM" && e.name === "interrupt") {
        r.status = "waiting";
      } else if (e.type === "CUSTOM" && (e.name === "policy_denied" || e.name === "wall_block")) {
        r.status = "blocked";
      }
    }
    return [...rows.values()];
  }, [nodes, events]);
}

function secondsText(ms0: number): string {
  const s = ms0 / 1000;
  return s < 10 ? `${s.toFixed(1).replace(".", ",")} s` : `${Math.round(s)} s`;
}

/** Lista compactă a pașilor, sub graful din sertar. */
export function StepList({ rows: input, settled = false }: { rows: StepRow[]; settled?: boolean }) {
  const rows = settled ? input.map((r) => (r.status === "idle" ? { ...r, status: "skipped" } : r)) : input;
  return (
    <ol className="flex flex-col">
      {rows.map((r) => (
        <li key={r.id} className="grid grid-cols-[1rem_minmax(0,1fr)_auto] items-start gap-x-3 border-b border-line py-2 last:border-b-0" title={r.hint}>
          <span className="mt-0.5"><StepIcon status={r.status} /></span>
          <div className="min-w-0">
            <p className="flex items-baseline gap-2 text-[0.9333rem]">
              <span className={cx("font-medium", r.status === "idle" && "text-muted")}>{r.label}</span>
              <span className="text-[0.8rem] text-muted">{r.model}</span>
            </p>
            {r.summary && r.status !== "idle" && <p className="mt-0.5 line-clamp-2 text-[0.8667rem] text-muted">{r.summary}</p>}
          </div>
          <span className="pt-0.5 text-right text-[0.8rem] tabular-nums text-muted">
            {r.start && r.end ? secondsText(r.end - r.start) : STEP_STATUS_LABEL[r.status] ?? ""}
          </span>
        </li>
      ))}
    </ol>
  );
}
