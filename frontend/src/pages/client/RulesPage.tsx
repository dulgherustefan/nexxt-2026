import { CaretDown, CheckCircle, Lock, MagnifyingGlass, Scales, WarningCircle, X } from "@phosphor-icons/react";
import { useEffect, useId, useMemo, useState, type ReactNode } from "react";
import { clock, money, plural } from "../../api/format";
import { useApi, useResource, type Resource } from "../../api/runtime";
import type { RuleCatalogEntry, RuleParams } from "../../api/types";
import { Button, cx, EmptyState, ErrorNote, IdTag, PageHeader, SectionBoundary, Skeleton, Status, Tabs, type Tone } from "../../ui/kit";
import { PARAM_GROUPS, paramMeta, paramOrder, type ParamGroup, type ParamMeta } from "./paramMeta";
import { fold, withoutT1 } from "./trustUi";

// ---------------------------------------------------------------- packs and confidence

const PACK_ORDER = ["PAY", "DSP", "CMP", "REC", "URM", "DP"];

const PACKS: Record<string, { name: string; caption: string }> = {
  PAY: { name: "Payments", caption: "Payment rules from Law 209/2019 (PSD2) and CJEU ruling C-70/25." },
  DSP: { name: "Card disputes", caption: "How a dispute runs under the Visa and Mastercard scheme rules." },
  CMP: { name: "Complaints", caption: "Deadlines for the answer to the customer, and what it has to say." },
  REC: { name: "Recalls", caption: "Asking the receiving bank to send a transfer back. Based on EPC guidance and VersoML proposals." },
  URM: { name: "Product rules", caption: "VersoML’s own rules, on top of what the law requires." },
  DP: { name: "Data protection", caption: "Automated decisions and the explanation each one needs." },
};

const CONFIDENCE: Record<string, { word: string; tone: Tone; explain: string }> = {
  P: { word: "Official text", tone: "dark", explain: "Read in the official legal text." },
  V: { word: "Verified", tone: "ok", explain: "Checked against the source during research." },
  S: { word: "Secondary source", tone: "neutral", explain: "Taken from a secondary source, such as a guide or an aggregator." },
  U: { word: "Unverified", tone: "warn", explain: "An inference or a proposal. Confirm it before relying on it." },
};

const isRecord = (v: unknown): v is Record<string, unknown> => Boolean(v) && typeof v === "object" && !Array.isArray(v);

/** AML is out of the product: its pack, its rule IDs and the rules that only run in the AML zone stay hidden. */
function isAmlRule(r: RuleCatalogEntry): boolean {
  const zone = String((r as { zone?: unknown }).zone ?? "").toLowerCase();
  return String(r.pack ?? "").toUpperCase() === "AML" || /^AML-/i.test(String(r.rule_id ?? "")) || zone === "aml";
}

const isAmlParam = (key: string) => /^aml_/i.test(key);

function paramKeys(r: RuleCatalogEntry): string[] {
  if (!r.params) return [];
  if (Array.isArray(r.params)) return r.params.filter((p): p is string => typeof p === "string");
  return Object.keys(r.params);
}

function aliasesOf(r: RuleCatalogEntry): string[] {
  const a = (r as { aliases?: unknown }).aliases;
  return Array.isArray(a) ? a.filter((x): x is string => typeof x === "string") : [];
}

const packName = (p: string) => PACKS[p]?.name ?? p;
const paramInputId = (key: string) => `param-input-${key}`;

const LINK = "underline decoration-line-strong underline-offset-2 transition-colors hover:text-ink hover:decoration-ink";

export default function RulesPage() {
  const api = useApi();
  const rules = useResource(() => api.rules(), [api]);
  const params = useResource(() => api.ruleParams(), [api]);
  return (
    <>
      <PageHeader
        title="Rules"
        description="Every decision cites one of these rules and its legal basis."
        actions={
          <a
            href="#parameters"
            className="press inline-flex h-9 items-center rounded-full bg-paper px-4 text-[0.9333rem] font-medium shadow-[var(--shadow-card)] transition-colors hover:bg-hover"
          >
            Edit parameters
          </a>
        }
      />
      <SectionBoundary label="Rule catalog">
        <Catalog res={rules} />
      </SectionBoundary>
      <SectionBoundary label="Parameters">
        <ParamsForm res={params} catalog={rules.data} onSaved={() => void rules.reload()} />
      </SectionBoundary>
    </>
  );
}

// ---------------------------------------------------------------- catalog

function Catalog({ res }: { res: Resource<RuleCatalogEntry[]> }) {
  const [query, setQuery] = useState("");
  const [pack, setPack] = useState("all");
  const all = useMemo(() => (Array.isArray(res.data) ? res.data.filter((r) => isRecord(r) && !isAmlRule(r)) : []), [res.data]);
  const index = useMemo(
    () =>
      all.map((r) => ({
        rule: r,
        text: fold(
          [r.rule_id, r.title, withoutT1(r.title ?? ""), r.basis, r.pack, packName(r.pack), ...aliasesOf(r), ...paramKeys(r).map((k) => paramMeta(k).label)].join(" "),
        ),
      })),
    [all],
  );
  const q = fold(query.trim());
  const matches = useMemo(() => (q ? index.filter((x) => x.text.includes(q)).map((x) => x.rule) : all), [index, all, q]);
  const packs = useMemo(() => {
    const found = Array.from(new Set(all.map((r) => r.pack).filter(Boolean)));
    return [...PACK_ORDER.filter((p) => found.includes(p)), ...found.filter((p) => !PACK_ORDER.includes(p)).sort()];
  }, [all]);
  const visible = pack === "all" ? matches : matches.filter((r) => r.pack === pack);
  const unverified = all.filter((r) => r.confidence === "U").length;

  if (res.error && !res.data) return <ErrorNote error={res.error} what="the rules" onRetry={res.reload} />;
  if (!res.data) return <CatalogSkeleton />;
  if (all.length === 0) {
    return (
      <EmptyState icon={<Scales aria-hidden size={20} />} title="No rules yet">
        The server sent an empty catalog. Restart it, then reload this page.
      </EmptyState>
    );
  }

  let empty: ReactNode = null;
  if (visible.length === 0) {
    const term = query.trim();
    empty = q && matches.length > 0 ? (
      <EmptyState
        title={`No ${packName(pack)} rules match “${term}”`}
        action={<Button size="sm" onClick={() => setPack("all")}>Search all packs</Button>}
      >
        Other packs have matches.
      </EmptyState>
    ) : q ? (
      <EmptyState title={`No rules match “${term}”`} action={<Button size="sm" onClick={() => setQuery("")}>Clear search</Button>}>
        Try a rule ID such as PAY-03, a word from the title, or an article such as art. 173.
      </EmptyState>
    ) : (
      <EmptyState title="No rules in this pack">Pick another pack.</EmptyState>
    );
  }

  return (
    <section aria-labelledby="rules-catalog">
      <h2 id="rules-catalog" className="sr-only">Rule catalog</h2>
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
        <SearchField value={query} onChange={setQuery} />
        <p className="tnum text-[0.8667rem] text-muted">
          {plural(all.length, "rule", "rules")} · {plural(unverified, "unverified", "unverified")}
        </p>
      </div>

      <div className="mt-5">
        <Tabs<string>
          label="Filter rules by pack"
          value={pack}
          onChange={setPack}
          tabs={[
            { id: "all", label: "All", count: matches.length },
            ...packs.map((p) => ({ id: p, label: packName(p), count: matches.filter((r) => r.pack === p).length })),
          ]}
        />
      </div>
      {pack !== "all" && PACKS[pack] && (
        <p className="mt-3 text-[0.8667rem] text-muted">
          <span className="id-text text-[0.8rem] font-medium text-subtle">{pack}</span> · {PACKS[pack].caption}
        </p>
      )}

      <div className="mt-4">{empty ?? <RuleList rules={visible} />}</div>
    </section>
  );
}

function SearchField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const id = useId();
  return (
    <div className="relative w-full max-w-sm">
      <label htmlFor={id} className="sr-only">Search rules</label>
      <MagnifyingGlass aria-hidden size={16} className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-subtle" />
      <input
        id={id}
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape" && value) {
            e.preventDefault();
            onChange("");
          }
        }}
        placeholder="Search by ID, title or article"
        autoComplete="off"
        spellCheck={false}
        className="h-9 w-full rounded-md bg-paper pr-9 pl-9 text-[0.9333rem] shadow-[var(--shadow-card)] placeholder:text-subtle [&::-webkit-search-cancel-button]:appearance-none"
      />
      {value && (
        <button
          type="button"
          aria-label="Clear search"
          onClick={() => onChange("")}
          className="absolute top-1/2 right-1.5 grid size-6 -translate-y-1/2 place-items-center rounded-full text-subtle transition-colors hover:bg-hover hover:text-ink"
        >
          <X aria-hidden size={14} />
        </button>
      )}
    </div>
  );
}

const RULE_GRID = "md:grid-cols-[5rem_minmax(0,1.55fr)_minmax(0,1fr)_9.5rem]";

function RuleList({ rules }: { rules: RuleCatalogEntry[] }) {
  return (
    <div className="overflow-hidden rounded-2xl bg-paper shadow-[var(--shadow-card)]">
      <div aria-hidden className={cx("hidden gap-x-6 border-b border-line px-5 py-2.5 text-[0.8rem] text-subtle md:grid", RULE_GRID)}>
        <span>ID</span>
        <span>Rule</span>
        <span>Legal basis</span>
        <span>Confidence</span>
      </div>
      <ul className="divide-y divide-line">
        {rules.map((r) => <RuleRow key={r.rule_id} rule={r} />)}
      </ul>
    </div>
  );
}

function RuleRow({ rule: r }: { rule: RuleCatalogEntry }) {
  const conf = CONFIDENCE[String(r.confidence)] ?? { word: "Not marked", tone: "neutral" as Tone, explain: "The rule has no confidence mark." };
  const keys = paramKeys(r).filter((k) => !isAmlParam(k));
  const aliases = aliasesOf(r);
  return (
    <li className={cx("grid grid-cols-[5rem_minmax(0,1fr)] items-start gap-x-4 gap-y-1.5 px-5 py-3.5 md:gap-x-6", RULE_GRID)}>
      <span className="pt-px">
        <IdTag>{r.rule_id}</IdTag>
      </span>
      <div className="min-w-0">
        <p className="leading-snug font-medium">{withoutT1(r.title || "Untitled rule")}</p>
        {(keys.length > 0 || aliases.length > 0) && (
          <p className="mt-1 text-[0.8rem] leading-relaxed text-muted">
            {keys.length > 0 && (
              <>
                {keys.length === 1 ? "Parameter: " : "Parameters: "}
                {keys.map((k, i) => (
                  <span key={k}>
                    {i > 0 && ", "}
                    <a href={`#param-${k}`} className={LINK}>{paramMeta(k).label}</a>
                  </span>
                ))}
              </>
            )}
            {keys.length > 0 && aliases.length > 0 && " · "}
            {aliases.length > 0 && `Also listed as ${aliases.join(", ")}`}
          </p>
        )}
      </div>
      <p className="col-start-2 text-[0.8667rem] leading-snug text-ink-soft md:col-start-auto md:pt-px md:text-[0.9333rem]">
        {r.basis || "No legal basis given"}
      </p>
      <span className="col-start-2 md:col-start-auto md:pt-0.5" title={conf.explain}>
        <Status tone={conf.tone}>
          {conf.word}
          <span className="sr-only"> {conf.explain}</span>
        </Status>
      </span>
    </li>
  );
}

function CatalogSkeleton() {
  return (
    <div className="flex flex-col gap-4" aria-busy="true">
      <Skeleton className="h-9 w-full max-w-sm" />
      <Skeleton className="h-10 w-full max-w-xl" />
      <div className="overflow-hidden rounded-2xl bg-paper shadow-[var(--shadow-card)]">
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="flex items-center gap-6 border-b border-line px-5 py-4 last:border-b-0">
            <Skeleton className="h-5 w-14" />
            <Skeleton className="h-4 flex-1" />
            <Skeleton className="hidden h-4 w-48 md:block" />
            <Skeleton className="hidden h-4 w-24 md:block" />
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- parameters

type Kind = "boolean" | "number" | "list" | "enum" | "text";
type Draft = string | boolean;
type Parsed = { ok: true; value: unknown } | { ok: false; error: string };

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
  if (kind === "number") return String(value);
  if (kind === "list") return (Array.isArray(value) ? value : [value]).map(String).join(", ");
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

/** "2000", "0.7", "5,000" (comma as a thousands separator). A decimal comma gets a clear message. */
function parseNumber(raw: string, nullable: boolean): Parsed {
  const t = raw.trim().replace(/[\s_]/g, "");
  if (t === "") return nullable ? { ok: true, value: null } : { ok: false, error: "Enter a number." };
  const clean = /^-?\d{1,3}(,\d{3})+(\.\d+)?$/.test(t) ? t.replace(/,/g, "") : t;
  if (clean.includes(",")) return { ok: false, error: "Use a dot for decimals, for example 0.7." };
  const n = Number(clean);
  return Number.isFinite(n) ? { ok: true, value: n } : { ok: false, error: "Enter a number, for example 2000 or 0.7." };
}

function parseDraft(d: Draft, kind: Kind, original: unknown, meta: ParamMeta): Parsed {
  if (kind === "boolean") return { ok: true, value: d === true };
  const s = String(d);
  if (kind === "number") return parseNumber(s, original === null || Boolean(meta.nullable));
  if (kind === "list") return { ok: true, value: s.split(/[,;\n]/).map((x) => x.trim()).filter(Boolean) };
  if (kind === "enum") return { ok: true, value: s === "" ? null : s };
  if (original === null) {
    const t = s.trim();
    if (t === "") return { ok: true, value: null };
    return { ok: true, value: /^-?\d+(\.\d+)?$/.test(t) ? Number(t) : t };
  }
  if (typeof original === "object" && original !== null) {
    try {
      return { ok: true, value: JSON.parse(s) };
    } catch {
      return { ok: false, error: "Enter valid JSON." };
    }
  }
  return { ok: true, value: s };
}

const same = (a: unknown, b: unknown) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
const plainNumber = (v: number) => new Intl.NumberFormat("en-GB", { maximumFractionDigits: 4 }).format(v);
const choiceWord = (meta: ParamMeta, v: string) => meta.choiceLabels?.[v] ?? v.replace(/_/g, " ");

/** The saved value, in words, for the "Currently" note under an edited field. */
function shown(v: unknown, meta: ParamMeta): string {
  if (v === null || v === undefined || v === "") return meta.emptyLabel ?? "Not set";
  if (typeof v === "boolean") return v ? "On" : "Off";
  if (Array.isArray(v)) return v.length ? v.join(", ") : "None";
  if (typeof v === "number") {
    if (meta.unit === "RON") return money(v);
    return meta.unit ? `${plainNumber(v)} ${meta.unit}` : plainNumber(v);
  }
  if (typeof v === "string") return choiceWord(meta, v);
  return JSON.stringify(v);
}

/** "the minimum is 0" → "The minimum is 0." */
function sentence(s: string): string {
  const t = s.trim();
  const c = t.charAt(0).toUpperCase() + t.slice(1);
  return /[.!?]$/.test(c) ? c : `${c}.`;
}

/** The backend answers a rejected save with "key: reason; key2: reason". */
function fieldErrorsFrom(message: string, sent: Record<string, unknown>): Record<string, string> {
  const errs: Record<string, string> = {};
  for (const part of message.split(/;\s*/)) {
    const m = part.match(/^\s*([a-z0-9_.-]+)\s*:\s*(.+)$/i);
    if (m && m[1] in sent) errs[m[1]] = sentence(m[2]);
  }
  return errs;
}

const groupIndex = (key: string) => {
  const g: ParamGroup = paramMeta(key).group ?? "other";
  const i = PARAM_GROUPS.findIndex((x) => x.id === g);
  return i === -1 ? PARAM_GROUPS.length : i;
};

type SaveResult = { ok: true; at: number; labels: string[] } | { ok: false; message: string; fields: number };

const PARAM_GRID = "md:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)_minmax(0,0.5fr)]";

function ParamsForm({ res, catalog, onSaved }: { res: Resource<RuleParams>; catalog?: RuleCatalogEntry[]; onSaved: () => void }) {
  const api = useApi();
  const [base, setBase] = useState<Record<string, unknown> | null>(null);
  const [draft, setDraft] = useState<Record<string, Draft>>({});
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<SaveResult | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  // the visible rules that use each key, and the keys only hidden (AML) rules use
  const { usedBy, hiddenOnly } = useMemo(() => {
    const visible = new Map<string, string[]>();
    const total = new Map<string, number>();
    const hidden = new Map<string, number>();
    for (const r of Array.isArray(catalog) ? catalog : []) {
      if (!isRecord(r)) continue;
      const aml = isAmlRule(r);
      for (const k of paramKeys(r)) {
        total.set(k, (total.get(k) ?? 0) + 1);
        if (aml) hidden.set(k, (hidden.get(k) ?? 0) + 1);
        else visible.set(k, [...(visible.get(k) ?? []), r.rule_id]);
      }
    }
    return { usedBy: visible, hiddenOnly: new Set([...total.keys()].filter((k) => hidden.get(k) === total.get(k))) };
  }, [catalog]);

  const keys = useMemo(() => {
    if (!base) return [];
    const server = Object.keys(base);
    return server
      .filter((k) => !isAmlParam(k) && !hiddenOnly.has(k))
      .sort((a, b) => groupIndex(a) - groupIndex(b) || paramOrder(a) - paramOrder(b) || server.indexOf(a) - server.indexOf(b));
  }, [base, hiddenOnly]);
  const kinds = useMemo(() => Object.fromEntries(keys.map((k) => [k, kindOf(k, base?.[k])])) as Record<string, Kind>, [keys, base]);

  // only edited fields are parsed, so an untouched value can never count as a change
  const parsed = useMemo(() => {
    const out: Record<string, Parsed> = {};
    for (const k of Object.keys(draft)) {
      if (kinds[k]) out[k] = parseDraft(draft[k], kinds[k], base?.[k], paramMeta(k));
    }
    return out;
  }, [draft, kinds, base]);
  const changed = keys.filter((k) => {
    const p = parsed[k];
    return p ? (p.ok ? !same(p.value, base?.[k]) : true) : false;
  });
  const invalid = keys.filter((k) => parsed[k] && !parsed[k].ok);

  // new data from the server replaces the form only when nothing is waiting to be saved
  useEffect(() => {
    const data = isRecord(res.data) ? res.data : null;
    if (!data) return;
    if (base && changed.length > 0) return;
    setBase(data);
    setDraft({});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [res.data]);

  const groups = useMemo(
    () =>
      PARAM_GROUPS.map((g) => ({ ...g, keys: keys.filter((k) => (paramMeta(k).group ?? "other") === g.id) })).filter((g) => g.keys.length > 0),
    [keys],
  );

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
      if (p?.ok) body[k] = p.value;
    }
    setSaving(true);
    setResult(null);
    try {
      const out = await api.putRuleParams(body as RuleParams);
      setBase(isRecord(out) ? { ...base, ...out } : { ...base, ...body });
      setDraft({});
      setFieldErrors({});
      setResult({ ok: true, at: Date.now(), labels: Object.keys(body).map((k) => paramMeta(k).label) });
      onSaved();
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      const errs = fieldErrorsFrom(message, body);
      setFieldErrors(errs);
      setResult({ ok: false, message, fields: Object.keys(errs).length });
      const first = keys.find((k) => errs[k]);
      if (first) window.requestAnimationFrame(() => document.getElementById(paramInputId(first))?.focus());
    } finally {
      setSaving(false);
    }
  }

  return (
    <section id="parameters" aria-labelledby="params-title" className="mt-14 scroll-mt-6">
      <div className="max-w-[68ch]">
        <h2 id="params-title" className="text-[1.15rem] font-semibold tracking-[-0.01em]">Parameters</h2>
        <p className="mt-1 text-muted">
          The law doesn’t fix these values, so the bank sets them here. The rules use a new value from the next case they evaluate.
        </p>
      </div>

      <div className="mt-4">
        {res.error && !base ? (
          <ErrorNote error={res.error} what="the parameters" onRetry={res.reload} />
        ) : !base ? (
          <ParamsSkeleton />
        ) : keys.length === 0 ? (
          <EmptyState title="No parameters to set">Every rule uses a value from the official text.</EmptyState>
        ) : (
          <div className="overflow-clip rounded-2xl bg-paper shadow-[var(--shadow-card)]">
            <div aria-hidden className={cx("hidden gap-x-6 px-5 py-2.5 text-[0.8rem] text-subtle md:grid", PARAM_GRID)}>
              <span>Parameter</span>
              <span>Value</span>
              <span>Used by</span>
            </div>
            {groups.map((g, i) => (
              <div key={g.id} role="group" aria-labelledby={`params-group-${g.id}`}>
                <h3
                  id={`params-group-${g.id}`}
                  className={cx("border-b border-line bg-canvas px-5 py-2 text-[0.8rem] font-medium text-muted", i > 0 ? "border-t" : "md:border-t")}
                >
                  {g.title}
                </h3>
                <ul className="divide-y divide-line">
                  {g.keys.map((k) => {
                    const p = parsed[k];
                    const meta = paramMeta(k);
                    return (
                      <ParamRow
                        key={k}
                        name={k}
                        kind={kinds[k]}
                        original={base[k]}
                        draft={k in draft ? draft[k] : toDraft(base[k], kinds[k])}
                        changed={changed.includes(k)}
                        error={(p && !p.ok ? p.error : undefined) ?? fieldErrors[k]}
                        rules={Array.from(new Set([...(usedBy.get(k) ?? []), ...(meta.rule ? [meta.rule] : [])]))}
                        rulesLoaded={catalog !== undefined}
                        onChange={(v) => edit(k, v)}
                      />
                    );
                  })}
                </ul>
              </div>
            ))}
            <div className="sticky bottom-0 z-10 flex flex-wrap items-center justify-between gap-3 border-t border-line bg-paper/95 px-5 py-3 backdrop-blur">
              <SaveStatus result={result} changed={changed.length} invalid={invalid.length} />
              <div className="flex items-center gap-2">
                <Button onClick={discard} disabled={changed.length === 0 || saving}>Discard changes</Button>
                <Button variant="primary" onClick={save} busy={saving} disabled={changed.length === 0 || invalid.length > 0}>
                  Save changes
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
    const why = result.fields > 0
      ? `The server rejected ${plural(result.fields, "value", "values")}.`
      : `${sentence(result.message || "The server didn’t answer")}`;
    return (
      <p role="alert" className="flex min-w-0 flex-1 items-start gap-2 text-[0.9333rem] text-danger">
        <WarningCircle aria-hidden size={18} className="mt-px shrink-0" />
        <span>
          <span className="font-medium">Couldn’t save.</span> {why} Your changes are still in the form.
        </span>
      </p>
    );
  }
  if (result?.ok && changed === 0) {
    return (
      <p role="status" className="flex min-w-0 flex-1 items-start gap-2 text-[0.9333rem]">
        <CheckCircle aria-hidden size={18} weight="fill" className="mt-px shrink-0 text-ok" />
        <span>
          <span className="font-medium">Saved at <span className="tnum">{clock(result.at, false)}</span>:</span> {result.labels.join(", ")}.
        </span>
      </p>
    );
  }
  if (invalid > 0) {
    return <p className="flex-1 text-[0.9333rem] text-danger">{plural(invalid, "value needs", "values need")} fixing before you can save.</p>;
  }
  return (
    <p className="flex-1 text-[0.9333rem] text-muted" aria-live="polite">
      {changed === 0 ? "No changes" : plural(changed, "unsaved change", "unsaved changes")}
    </p>
  );
}

function ParamRow({ name, kind, original, draft, changed, error, rules, rulesLoaded, onChange }: {
  name: string;
  kind: Kind;
  original: unknown;
  draft: Draft;
  changed: boolean;
  error?: string;
  rules: string[];
  rulesLoaded: boolean;
  onChange: (v: Draft) => void;
}) {
  const meta = paramMeta(name);
  const inputId = paramInputId(name);
  const helpId = `${inputId}-help`;
  const noteId = `${inputId}-note`;
  const locked = Boolean(meta.locked);

  const note: ReactNode = error ? (
    <span className="text-danger">{error}</span>
  ) : changed ? (
    <span className="text-ink-soft">Currently: {shown(original, meta)}</span>
  ) : locked ? (
    <span className="inline-flex items-start gap-1.5">
      <Lock aria-hidden size={14} className="mt-px shrink-0 text-subtle" />
      {meta.locked}
    </span>
  ) : meta.format && (kind === "text" || kind === "list") ? (
    meta.format
  ) : null;

  const describedBy = [meta.help ? helpId : null, note ? noteId : null].filter(Boolean).join(" ") || undefined;
  const field = cx(
    "rounded-md bg-paper text-[0.9333rem] ring-1 ring-inset transition-shadow",
    "disabled:cursor-not-allowed disabled:bg-canvas disabled:text-muted",
    error ? "ring-danger" : changed ? "ring-ink" : "ring-line-strong",
  );
  const a11y = { id: inputId, "aria-describedby": describedBy, "aria-invalid": error ? true : undefined };

  let control: ReactNode;
  if (kind === "boolean") {
    const on = draft === true;
    control = (
      <span className="inline-flex items-center gap-2.5">
        <button
          {...a11y}
          type="button"
          role="switch"
          aria-checked={on}
          disabled={locked}
          onClick={() => onChange(!on)}
          className={cx(
            "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors duration-150",
            "disabled:cursor-not-allowed disabled:opacity-60",
            on ? "bg-ink" : "bg-line-strong",
          )}
        >
          <span
            aria-hidden
            className={cx(
              "size-4 rounded-full bg-paper shadow-[0_1px_2px_rgb(18_19_22/0.2)] transition-transform duration-150",
              on ? "translate-x-[18px]" : "translate-x-0.5",
            )}
          />
        </button>
        <span aria-hidden className="text-[0.9333rem] text-ink-soft">{on ? "On" : "Off"}</span>
      </span>
    );
  } else if (kind === "enum") {
    const current = typeof draft === "string" ? draft : "";
    const options = [...(meta.nullable || original === null ? [""] : []), ...(meta.choices ?? [])];
    if (current && !options.includes(current)) options.push(current);
    control = (
      <span className="relative inline-flex w-full max-w-xs">
        <select
          {...a11y}
          value={current}
          disabled={locked}
          onChange={(e) => onChange(e.target.value)}
          className={cx(field, "h-9 w-full appearance-none truncate pr-9 pl-3")}
        >
          {options.map((o) => (
            <option key={o || "(empty)"} value={o}>{o === "" ? meta.emptyLabel ?? "Not set" : choiceWord(meta, o)}</option>
          ))}
        </select>
        <CaretDown aria-hidden size={14} className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-subtle" />
      </span>
    );
  } else if (kind === "list") {
    control = (
      <textarea
        {...a11y}
        rows={2}
        value={String(draft)}
        disabled={locked}
        spellCheck={false}
        onChange={(e) => onChange(e.target.value)}
        className={cx(field, "min-h-[4.25rem] w-full resize-y px-3 py-2 leading-snug")}
      />
    );
  } else {
    control = (
      <input
        {...a11y}
        type="text"
        inputMode={kind === "number" ? "decimal" : undefined}
        autoComplete="off"
        spellCheck={false}
        value={String(draft)}
        disabled={locked}
        placeholder={original === null || meta.nullable ? meta.emptyLabel ?? "Not set" : undefined}
        onChange={(e) => onChange(e.target.value)}
        className={cx(field, "h-9 px-3", kind === "number" ? "tnum w-32" : "w-full max-w-xs")}
      />
    );
  }

  return (
    <li
      id={`param-${name}`}
      className={cx("grid scroll-mt-24 gap-x-6 gap-y-2.5 px-5 py-4 transition-colors target:animate-flash", PARAM_GRID, changed && "bg-canvas")}
    >
      <div className="min-w-0">
        <label htmlFor={inputId} className="font-medium">{meta.label}</label>
        {meta.help && <p id={helpId} className="mt-0.5 text-[0.8667rem] leading-snug text-muted">{meta.help}</p>}
        <p className="mt-1 font-mono text-[0.72rem] break-all text-subtle">{name}</p>
      </div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          {meta.unitBefore && meta.unit && <span className="text-[0.8667rem] text-muted">{meta.unit}</span>}
          {control}
          {!meta.unitBefore && meta.unit && kind === "number" && <span className="text-[0.8667rem] text-muted">{meta.unit}</span>}
        </div>
        {note && <p id={noteId} className="mt-1.5 text-[0.8rem] leading-snug text-muted">{note}</p>}
      </div>
      <div className="flex flex-wrap content-start items-center gap-1.5">
        <span className="text-[0.8rem] text-subtle md:sr-only">Used by</span>
        {rules.length > 0
          ? rules.map((r) => <IdTag key={r}>{r}</IdTag>)
          : rulesLoaded
            ? <span className="text-[0.8rem] text-subtle">No listed rule</span>
            : null}
      </div>
    </li>
  );
}

function ParamsSkeleton() {
  return (
    <div className="overflow-hidden rounded-2xl bg-paper shadow-[var(--shadow-card)]" aria-busy="true">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="grid gap-4 border-b border-line px-5 py-4 last:border-b-0 md:grid-cols-3">
          <div className="flex flex-col gap-2">
            <Skeleton className="h-4 w-48" />
            <Skeleton className="h-3 w-64 max-w-full" />
          </div>
          <Skeleton className="h-9 w-32" />
          <Skeleton className="hidden h-5 w-16 md:block" />
        </div>
      ))}
    </div>
  );
}
