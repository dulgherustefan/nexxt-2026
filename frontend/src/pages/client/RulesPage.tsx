import { CircleAlert, CircleCheck, Lock, Search, X } from "lucide-react";
import { useEffect, useId, useMemo, useState } from "react";
import { clock } from "../../api/format";
import { useApi, useResource, type Resource } from "../../api/runtime";
import type { RuleCatalogEntry, RuleParams } from "../../api/types";
import { Button, cx, EmptyState, ErrorNote, IdTag, PageHeader, SectionBoundary, Skeleton, Tabs } from "../../ui/kit";
import { paramMeta } from "./paramMeta";
import { fold, ro, TABLE } from "./trustUi";

// ------------------------------------------------------------------ pachete și încredere

const PACK_ORDER = ["PAY", "DSP", "CMP", "DP", "REC", "URM", "AML"];

const PACK_CAPTION: Record<string, string> = {
  PAY: "Plăți: Legea 209/2019 (PSD2) și CJUE C-70/25.",
  DSP: "Dispute pe card și regulile schemelor Visa și Mastercard.",
  CMP: "Reclamații: termenele și conținutul răspunsului.",
  DP: "Protecția datelor și deciziile automate.",
  REC: "Rechemarea transferurilor (ghiduri EPC). Extensie: nu e în docs/context, deci neverificată acolo.",
  URM: "Reguli de produs VersoML. Extensie: nu e în docs/context.",
  AML: "AML: Legea 129/2019, art. 6–8. Se aplică doar în zona AML.",
};

const CONFIDENCE: Record<string, { word: string; explain: string }> = {
  P: { word: "Oficial", explain: "citit în textul oficial" },
  S: { word: "Secundar", explain: "sursă secundară" },
  U: { word: "Neverificat", explain: "parametru neverificat" },
  V: { word: "Verificat", explain: "verificat în research" },
};

function paramKeys(r: RuleCatalogEntry): string[] {
  if (!r.params) return [];
  if (Array.isArray(r.params)) return r.params.filter((p): p is string => typeof p === "string");
  return Object.keys(r.params);
}

function aliasesOf(r: RuleCatalogEntry): string[] {
  const a = (r as { aliases?: unknown }).aliases;
  return Array.isArray(a) ? a.filter((x): x is string => typeof x === "string") : [];
}

export default function RulesPage() {
  const api = useApi();
  const rules = useResource(() => api.rules(), [api]);
  const params = useResource(() => api.ruleParams(), [api]);
  return (
    <>
      <PageHeader
        title="Reguli"
        description="Motorul de reguli decide, nu LLM-ul: fiecare decizie poartă ID-ul regulii care a produs-o. Aici vezi temeiul fiecărei reguli și cât de sigur e."
        actions={
          <a href="#parametri" className="inline-flex h-10 items-center rounded-md border border-line-strong bg-paper px-4 font-semibold hover:bg-hover">
            Parametri configurabili
          </a>
        }
      />
      <SectionBoundary label="Catalogul regulilor">
        <Catalog res={rules} />
      </SectionBoundary>
      <SectionBoundary label="Parametri configurabili">
        <ParamsForm res={params} rules={rules.data} onSaved={() => void rules.reload()} />
      </SectionBoundary>
    </>
  );
}

// ------------------------------------------------------------------ catalogul

function Catalog({ res }: { res: Resource<RuleCatalogEntry[]> }) {
  const [query, setQuery] = useState("");
  const [pack, setPack] = useState("all");
  const all = useMemo(() => (Array.isArray(res.data) ? res.data : []), [res.data]);
  const q = fold(query.trim());
  const matches = useMemo(
    () =>
      q
        ? all.filter((r) => fold([r.rule_id, r.title, r.basis, r.pack, ...aliasesOf(r)].join(" ")).includes(q))
        : all,
    [all, q],
  );
  const packs = useMemo(() => {
    const found = Array.from(new Set(all.map((r) => r.pack).filter(Boolean)));
    return [...PACK_ORDER.filter((p) => found.includes(p)), ...found.filter((p) => !PACK_ORDER.includes(p)).sort()];
  }, [all]);
  const visible = pack === "all" ? matches : matches.filter((r) => r.pack === pack);
  const unverified = all.filter((r) => r.confidence === "U").length;

  if (res.error && !res.data) return <ErrorNote error={res.error} what="catalogul regulilor" onRetry={res.reload} />;
  if (!res.data) {
    return (
      <div className="flex flex-col gap-2">
        <Skeleton className="h-10 w-full max-w-md" />
        {[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-12" />)}
      </div>
    );
  }
  if (all.length === 0) {
    return <EmptyState title="Catalogul e gol.">Serverul nu a trimis nicio regulă. Repornește zona client și reîncarcă pagina.</EmptyState>;
  }

  return (
    <section aria-labelledby="rules-catalog">
      <h2 id="rules-catalog" className="sr-only">Catalogul regulilor</h2>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <label className="relative block w-full max-w-md">
          <span className="sr-only">Caută o regulă</span>
          <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Caută după ID, titlu sau temei (ex. PAY-03, art. 173)"
            className="h-10 w-full rounded-md border border-line-strong bg-paper pr-9 pl-9"
          />
          {query && (
            <button type="button" aria-label="Șterge căutarea" onClick={() => setQuery("")} className="absolute top-1/2 right-2 grid size-7 -translate-y-1/2 place-items-center rounded-md hover:bg-hover">
              <X aria-hidden className="size-4" />
            </button>
          )}
        </label>
        <p className="text-[0.9333rem] text-muted">
          {ro(all.length, "regulă", "reguli")} · {ro(unverified, "neverificată", "neverificate")}
        </p>
      </div>

      <div className="mt-4">
        <Tabs<string>
          label="Filtrează după pachet"
          value={pack}
          onChange={setPack}
          tabs={[
            { id: "all", label: "Toate", count: matches.length },
            ...packs.map((p) => ({ id: p, label: p, count: matches.filter((r) => r.pack === p).length })),
          ]}
        />
      </div>
      {pack !== "all" && PACK_CAPTION[pack] && <p className="mt-2 text-[0.9333rem] text-muted">{PACK_CAPTION[pack]}</p>}

      <div className="mt-3">
        {visible.length === 0 ? (
          <EmptyState
            title={q ? `Nicio regulă pentru „${query.trim()}”.` : "Nicio regulă în acest pachet."}
            action={q ? <Button size="sm" onClick={() => setQuery("")}>Șterge căutarea</Button> : undefined}
          >
            {q ? "Caută după ID (PAY-03), un cuvânt din titlu sau un articol de lege." : "Alege alt pachet."}
          </EmptyState>
        ) : (
          <div className={TABLE.wrap}>
            <table className={cx(TABLE.table, "min-w-[54rem]")}>
              <thead>
                <tr className={TABLE.headRow}>
                  <th scope="col" className={cx(TABLE.th, "w-32")}>ID</th>
                  <th scope="col" className={TABLE.th}>Titlu</th>
                  <th scope="col" className={TABLE.th}>Temei legal</th>
                  <th scope="col" className={cx(TABLE.th, "w-48")}>Încredere</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((r) => {
                  const conf = CONFIDENCE[String(r.confidence)] ?? { word: String(r.confidence || "—"), explain: "marcaj necunoscut" };
                  const keys = paramKeys(r);
                  const aliases = aliasesOf(r);
                  return (
                    <tr key={r.rule_id} className={TABLE.row}>
                      <td className={cx(TABLE.td, "whitespace-nowrap")}>
                        <IdTag>{r.rule_id}</IdTag>
                        {aliases.length > 0 && <span className="mt-1 block text-[0.8667rem] text-muted">și {aliases.join(", ")}</span>}
                      </td>
                      <td className={TABLE.td}>
                        <span className="font-medium">{r.title}</span>
                        {keys.length > 0 && (
                          <span className="mt-1 block text-[0.8667rem] text-muted">
                            {keys.length === 1 ? "Parametru: " : "Parametri: "}
                            {keys.map((k, i) => (
                              <span key={k}>
                                {i > 0 && ", "}
                                <a href={`#param-${k}`} className="underline hover:text-ink">{paramMeta(k).label}</a>
                              </span>
                            ))}
                          </span>
                        )}
                      </td>
                      <td className={cx(TABLE.td, "text-ink-soft")}>{r.basis || "—"}</td>
                      <td className={TABLE.td}>
                        <span className="block font-semibold">{conf.word}</span>
                        <span className="block text-[0.8667rem] text-muted">{conf.explain}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ parametrii

type Kind = "boolean" | "number" | "list" | "enum" | "text";
type Draft = string | boolean;

function kindOf(key: string, value: unknown): Kind {
  const m = paramMeta(key);
  if (m.choices) return "enum";
  if (typeof value === "boolean") return "boolean";
  if (typeof value === "number") return "number";
  if (Array.isArray(value)) return "list";
  if (value === null && m.type === "number") return "number";
  return "text";
}

function toDraft(value: unknown, kind: Kind): Draft {
  if (kind === "boolean") return value === true;
  if (value === null || value === undefined) return "";
  if (kind === "number") return String(value).replace(".", ",");
  if (kind === "list") return (Array.isArray(value) ? value : [value]).map(String).join(", ");
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

function parseDraft(d: Draft, kind: Kind, original: unknown, key: string): { ok: true; value: unknown } | { ok: false; error: string } {
  const meta = paramMeta(key);
  if (kind === "boolean") return { ok: true, value: d === true };
  const s = String(d);
  if (kind === "number") {
    const t = s.trim().replace(/\s/g, "").replace(",", ".");
    if (t === "") return original === null || meta.nullable ? { ok: true, value: null } : { ok: false, error: "Completează un număr." };
    const n = Number(t);
    return Number.isFinite(n) ? { ok: true, value: n } : { ok: false, error: "Trebuie să fie un număr, de exemplu 2000 sau 0,7." };
  }
  if (kind === "list") return { ok: true, value: s.split(/[,;\n]/).map((x) => x.trim()).filter(Boolean) };
  if (kind === "enum") return { ok: true, value: s === "" ? null : s };
  if (original === null) {
    const t = s.trim();
    if (t === "") return { ok: true, value: null };
    return { ok: true, value: /^-?\d+([.,]\d+)?$/.test(t) ? Number(t.replace(",", ".")) : t };
  }
  if (typeof original === "object" && original !== null) {
    try {
      return { ok: true, value: JSON.parse(s) };
    } catch {
      return { ok: false, error: "Valoarea trebuie să fie JSON valid." };
    }
  }
  return { ok: true, value: s };
}

const same = (a: unknown, b: unknown) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

function shown(v: unknown): string {
  if (v === null || v === undefined || v === "") return "gol";
  if (typeof v === "boolean") return v ? "da" : "nu";
  if (Array.isArray(v)) return v.length ? v.join(", ") : "listă goală";
  if (typeof v === "number") return String(v).replace(".", ",");
  return String(v);
}

type SaveResult = { ok: true; at: number; labels: string[] } | { ok: false; message: string };

function ParamsForm({ res, rules, onSaved }: { res: Resource<RuleParams>; rules?: RuleCatalogEntry[]; onSaved: () => void }) {
  const api = useApi();
  const [base, setBase] = useState<Record<string, unknown> | null>(null);
  const [draft, setDraft] = useState<Record<string, Draft>>({});
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<SaveResult | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const keys = useMemo(() => (base ? Object.keys(base) : []), [base]);
  const kinds = useMemo(() => Object.fromEntries(keys.map((k) => [k, kindOf(k, base?.[k])])) as Record<string, Kind>, [keys, base]);

  const parsed = useMemo(() => {
    const out: Record<string, ReturnType<typeof parseDraft>> = {};
    for (const k of keys) out[k] = parseDraft(draft[k] ?? toDraft(base?.[k], kinds[k]), kinds[k], base?.[k], k);
    return out;
  }, [keys, draft, base, kinds]);
  const changed = keys.filter((k) => {
    const p = parsed[k];
    return p.ok ? !same(p.value, base?.[k]) : true;
  });
  const invalid = keys.filter((k) => !parsed[k].ok);

  // date noi de la server: le preluăm doar dacă nu există modificări nesalvate
  useEffect(() => {
    const data = res.data && typeof res.data === "object" && !Array.isArray(res.data) ? (res.data as Record<string, unknown>) : null;
    if (!data) return;
    if (base && changed.length > 0) return;
    setBase(data);
    setDraft({});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [res.data]);

  const usedBy = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const r of rules ?? []) {
      for (const k of paramKeys(r)) map.set(k, [...(map.get(k) ?? []), r.rule_id]);
    }
    return map;
  }, [rules]);

  function edit(key: string, value: Draft) {
    setDraft((d) => ({ ...d, [key]: value }));
    setResult(null);
    setFieldErrors((e) => {
      if (!e[key]) return e;
      const next = { ...e };
      delete next[key];
      return next;
    });
  }

  function discard() {
    setDraft({});
    setResult(null);
    setFieldErrors({});
  }

  async function save() {
    if (!base || changed.length === 0 || invalid.length > 0) return;
    const body: Record<string, unknown> = {};
    for (const k of changed) {
      const p = parsed[k];
      if (p.ok) body[k] = p.value;
    }
    setSaving(true);
    setResult(null);
    try {
      const out = await api.putRuleParams(body as RuleParams);
      const next = out && typeof out === "object" && !Array.isArray(out) ? { ...base, ...(out as Record<string, unknown>) } : { ...base, ...body };
      setBase(next);
      setDraft({});
      setFieldErrors({});
      setResult({ ok: true, at: Date.now(), labels: Object.keys(body).map((k) => paramMeta(k).label) });
      onSaved();
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      // backend-ul răspunde „cheie: motiv; cheie2: motiv”
      const errs: Record<string, string> = {};
      for (const part of message.split(/;\s*/)) {
        const m = part.match(/^\s*([a-z0-9_.-]+)\s*:\s*(.+)$/i);
        if (m && body[m[1]] !== undefined) errs[m[1]] = m[2];
      }
      setFieldErrors(errs);
      setResult({ ok: false, message });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section id="parametri" aria-labelledby="params-title" className="mt-10 scroll-mt-6">
      <h2 id="params-title" className="text-[1.2rem] font-semibold">Parametri configurabili [U]</h2>
      <p className="mt-1 max-w-[70ch] text-muted">
        Valori pe care textele oficiale nu le stabilesc: sunt parametri, nu constante în cod. Le schimbi aici, iar regulile le folosesc de la următoarea evaluare.
      </p>

      <div className="mt-4">
        {res.error && !base ? (
          <ErrorNote error={res.error} what="parametrii" onRetry={res.reload} />
        ) : !base ? (
          <div className="flex flex-col gap-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-14" />)}</div>
        ) : keys.length === 0 ? (
          <EmptyState title="Motorul nu are parametri configurabili.">Toate regulile au valori citite în textul oficial.</EmptyState>
        ) : (
          <div className="rounded-lg border border-line bg-paper">
            <div className="hidden grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)_minmax(0,0.6fr)] gap-4 border-b border-line bg-canvas px-4 py-2.5 text-[0.8667rem] font-semibold text-muted md:grid">
              <span>Parametru</span>
              <span>Valoare</span>
              <span>Folosit de</span>
            </div>
            <ul>
              {keys.map((k) => (
                <ParamRow
                  key={k}
                  name={k}
                  kind={kinds[k]}
                  original={base[k]}
                  draft={draft[k] ?? toDraft(base[k], kinds[k])}
                  changed={changed.includes(k)}
                  error={(!parsed[k].ok ? (parsed[k] as { error: string }).error : undefined) ?? fieldErrors[k]}
                  rules={Array.from(new Set([...(usedBy.get(k) ?? []), ...(paramMeta(k).rule ? [paramMeta(k).rule as string] : [])]))}
                  onChange={(v) => edit(k, v)}
                />
              ))}
            </ul>
            <div className="sticky bottom-0 flex flex-wrap items-center justify-between gap-3 rounded-b-lg border-t border-line bg-paper px-4 py-3">
              <SaveStatus result={result} changed={changed.length} invalid={invalid.length} />
              <div className="flex items-center gap-2">
                <Button onClick={discard} disabled={changed.length === 0 || saving}>Renunță</Button>
                <Button variant="primary" onClick={save} busy={saving} disabled={changed.length === 0 || invalid.length > 0}>
                  Salvează modificările
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function SaveStatus({ result, changed, invalid }: { result: SaveResult | null; changed: number; invalid: number }) {
  if (result && !result.ok) {
    return (
      <p role="alert" className="flex min-w-0 flex-1 items-start gap-2 text-danger">
        <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
        <span>
          <span className="font-semibold">Nu am salvat.</span> Motiv: {result.message} Modificările tale au rămas în formular.
        </span>
      </p>
    );
  }
  if (result?.ok && changed === 0) {
    return (
      <p role="status" className="flex min-w-0 flex-1 items-start gap-2">
        <CircleCheck aria-hidden className="mt-0.5 size-4 shrink-0 text-ok" />
        <span>
          <span className="font-semibold">Salvat la {clock(result.at, false)}:</span> {result.labels.join(", ")}.
        </span>
      </p>
    );
  }
  if (invalid > 0) {
    return <p className="flex-1 text-danger">{ro(invalid, "valoare nu e validă", "valori nu sunt valide")}: corectează înainte de salvare.</p>;
  }
  return (
    <p className="flex-1 text-muted" aria-live="polite">
      {changed === 0 ? "Nicio modificare." : `${ro(changed, "modificare nesalvată", "modificări nesalvate")}.`}
    </p>
  );
}

function ParamRow({ name, kind, original, draft, changed, error, rules, onChange }: {
  name: string;
  kind: Kind;
  original: unknown;
  draft: Draft;
  changed: boolean;
  error?: string;
  rules: string[];
  onChange: (v: Draft) => void;
}) {
  const id = useId();
  const meta = paramMeta(name);
  const locked = Boolean(meta.locked);
  const inputCls = cx(
    "h-9 rounded-md border bg-paper px-2.5",
    error ? "border-danger" : changed ? "border-ink" : "border-line-strong",
    "disabled:cursor-not-allowed disabled:bg-canvas disabled:text-muted",
  );

  let control;
  if (kind === "boolean") {
    const on = draft === true;
    control = (
      <span className="inline-flex items-center gap-2.5">
        <button
          id={id}
          type="button"
          role="switch"
          aria-checked={on}
          disabled={locked}
          onClick={() => onChange(!on)}
          className={cx(
            "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition-colors",
            on ? "border-ink bg-ink" : "border-line-strong bg-hover",
            "disabled:cursor-not-allowed disabled:opacity-60",
          )}
        >
          <span aria-hidden className={cx("inline-block size-4 rounded-full border border-line bg-paper transition-transform", on ? "translate-x-6" : "translate-x-1")} />
        </button>
        <span className="font-medium">{on ? "Da" : "Nu"}</span>
      </span>
    );
  } else if (kind === "enum") {
    const choices = meta.choices ?? [];
    const current = typeof draft === "string" ? draft : "";
    const options = [...(meta.nullable || original === null ? [""] : []), ...choices];
    if (current && !options.includes(current)) options.push(current);
    control = (
      <select id={id} value={current} disabled={locked} onChange={(e) => onChange(e.target.value)} className={cx(inputCls, "w-full max-w-xs")}>
        {options.map((o) => (
          <option key={o || "gol"} value={o}>{o === "" ? "Gol (neaplicat)" : meta.choiceLabels?.[o] ?? o.replace(/_/g, " ")}</option>
        ))}
      </select>
    );
  } else if (kind === "list") {
    control = (
      <textarea
        id={id}
        rows={2}
        value={String(draft)}
        disabled={locked}
        onChange={(e) => onChange(e.target.value)}
        className={cx(inputCls, "h-auto w-full py-1.5 text-[0.9333rem]")}
      />
    );
  } else {
    control = (
      <input
        id={id}
        type="text"
        inputMode={kind === "number" ? "decimal" : undefined}
        value={String(draft)}
        disabled={locked}
        placeholder={original === null ? "gol" : undefined}
        onChange={(e) => onChange(e.target.value)}
        className={cx(inputCls, kind === "number" ? "w-32 tabular-nums" : "w-full max-w-xs")}
      />
    );
  }

  return (
    <li id={`param-${name}`} className={cx("grid scroll-mt-24 gap-x-4 gap-y-2 border-b border-line px-4 py-3 last:border-b-0 md:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)_minmax(0,0.6fr)]", changed && "bg-yellow-tint")}>
      <div className="min-w-0">
        <label htmlFor={id} className="font-semibold">{meta.label}</label>
        <p className="font-mono text-[0.8667rem] break-all text-muted">{name}</p>
        {meta.help && <p className="mt-0.5 text-[0.8667rem] text-muted">{meta.help}</p>}
      </div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          {control}
          {meta.unit && kind === "number" && <span className="text-[0.9333rem] text-muted">{meta.unit}</span>}
        </div>
        {meta.unit && kind !== "number" && kind !== "boolean" && <p className="mt-1 text-[0.8667rem] text-muted">Format: {meta.unit}</p>}
        {locked && (
          <p className="mt-1 flex items-center gap-1.5 text-[0.8667rem] text-muted">
            <Lock aria-hidden className="size-3.5" />
            {meta.locked}
          </p>
        )}
        {error ? (
          <p className="mt-1 text-[0.8667rem] text-danger">{error}</p>
        ) : changed ? (
          <p className="mt-1 text-[0.8667rem] text-ink-soft">Modificat · înainte: {shown(original)}</p>
        ) : null}
      </div>
      <div className="flex flex-wrap content-start gap-1.5">
        {rules.length ? rules.map((r) => <IdTag key={r}>{r}</IdTag>) : <span className="text-[0.8667rem] text-muted">nicio regulă din catalog</span>}
      </div>
    </li>
  );
}
