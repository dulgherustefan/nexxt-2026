/**
 * Free-form intake in mock mode: a synthetic customer directory, the customer search, and the
 * preview that finds the customer and the disputed payment in a pasted complaint.
 * Aliases, references and masked accounts follow the rest of the mock data; nothing is real.
 */
import { money } from "../api/format";
import type { CustomerHit, IntakeExtracted, IntakePreview, IntakePreviewBody, MatchResult, TxCandidate } from "../api/types";
import { isoRo } from "./calendar";
import type { MockDb } from "./store";
import { MULE_IBAN_SHORT } from "./stories";

const H = 3600_000;

interface TxSeed {
  tx_id: string;
  agoH: number;
  amount: number;
  payee: string;
  channel: "card" | "transfer" | "transfer_instant";
  direction: "in" | "out";
  newPayee?: boolean;
}

interface DirEntry {
  customer_ref: string;
  alias: string;
  city: string;
  accounts: string[];
  /** The last digits of the phone on file, for the "phone number in the message" match. */
  phone_tail: string;
  txs: TxSeed[];
}

const acct = (bank: string, tail: string) => `RO49 ${bank} •••• •••• •••• ${tail}`;

const DIRECTORY: DirEntry[] = [
  {
    customer_ref: "CUST-DEMO-01", alias: "Customer 0042", city: "București", accounts: [acct("BDEM", "0042")], phone_tail: "042",
    txs: [
      { tx_id: "TX-D1-007", agoH: 0.2, amount: 3200, payee: `Transfer to ${MULE_IBAN_SHORT}`, channel: "transfer", direction: "out", newPayee: true },
      { tx_id: "TX-D1-006", agoH: 5, amount: 184.3, payee: "Demo Supermarket", channel: "card", direction: "out" },
      { tx_id: "TX-D1-005", agoH: 27, amount: 62.15, payee: "Demo Pharmacy", channel: "card", direction: "out" },
      { tx_id: "TX-D1-004", agoH: 50, amount: 231.4, payee: "Electricity bill, Demo Energy", channel: "transfer", direction: "out" },
    ],
  },
  {
    customer_ref: "CUST-DEMO-02", alias: "Customer 0117", city: "Cluj-Napoca", accounts: [acct("BDEM", "0117")], phone_tail: "117",
    txs: [
      { tx_id: "TX-D2-004", agoH: 0.5, amount: 1850, payee: `Transfer to ${MULE_IBAN_SHORT}`, channel: "transfer", direction: "out", newPayee: true },
      { tx_id: "TX-D2-003", agoH: 9, amount: 275.8, payee: "Demo Gas Station", channel: "card", direction: "out" },
    ],
  },
  {
    customer_ref: "CUST-0198", alias: "Customer 0198", city: "Iași", accounts: [acct("BDEM", "0198")], phone_tail: "198",
    txs: [
      { tx_id: "TX-0198-31", agoH: 27, amount: 512.4, payee: "Shop Demo Online", channel: "card", direction: "out", newPayee: true },
      { tx_id: "TX-0198-30", agoH: 30, amount: 96.2, payee: "Demo Supermarket", channel: "card", direction: "out" },
      { tx_id: "TX-0198-29", agoH: 52, amount: 41.75, payee: "Demo Pharmacy", channel: "card", direction: "out" },
    ],
  },
  {
    customer_ref: "CUST-0464", alias: "Customer 0464", city: "Timișoara", accounts: [acct("BDEM", "0464"), acct("BDEM", "4640")], phone_tail: "464",
    txs: [
      { tx_id: "TX-0464-18", agoH: 6 * 24 + 3, amount: 512.4, payee: "Shop Demo Online", channel: "card", direction: "out", newPayee: true },
      { tx_id: "TX-0464-17", agoH: 7 * 24 + 5, amount: 498, payee: "Market Demo SRL (online)", channel: "card", direction: "out", newPayee: true },
      { tx_id: "TX-0464-16", agoH: 8 * 24, amount: 275.8, payee: "Demo Gas Station", channel: "card", direction: "out" },
    ],
  },
  {
    customer_ref: "CUST-0105", alias: "Customer 0105", city: "Brașov", accounts: [acct("BDEM", "0105")], phone_tail: "105",
    txs: [
      { tx_id: "TX-0105-44", agoH: 5.5, amount: 8000, payee: "Transfer to RO49 YBNK •••• 2290", channel: "transfer", direction: "out", newPayee: true },
      { tx_id: "TX-0105-43", agoH: 30, amount: 120, payee: "Demo Telecom", channel: "transfer", direction: "out" },
    ],
  },
  {
    customer_ref: "CUST-0233", alias: "Customer 0233", city: "Constanța", accounts: [acct("BDEM", "0233")], phone_tail: "233",
    txs: [{ tx_id: "TX-0233-12", agoH: 9, amount: 4750, payee: "Transfer to RO49 YBNK •••• 5518", channel: "transfer", direction: "out", newPayee: true }],
  },
  {
    customer_ref: "CUST-0317", alias: "Customer 0317", city: "Sibiu", accounts: [acct("BDEM", "0317")], phone_tail: "317",
    txs: [{ tx_id: "TX-0317-08", agoH: 21, amount: 1249.9, payee: "Electro Demo SRL", channel: "card", direction: "out", newPayee: true }],
  },
  {
    customer_ref: "CUST-0412", alias: "Customer 0412", city: "Craiova", accounts: [acct("BDEM", "0412")], phone_tail: "412",
    txs: [{ tx_id: "TX-0412-22", agoH: 3, amount: 2310, payee: "Demo Mall Store", channel: "card", direction: "out" }],
  },
  {
    customer_ref: "CUST-0561", alias: "Customer 0561", city: "Ploiești", accounts: [acct("BDEM", "0561")], phone_tail: "561",
    txs: [
      { tx_id: "TX-0561-05", agoH: 31, amount: 389, payee: "Demo Gas Station", channel: "card", direction: "out" },
      { tx_id: "TX-0561-04", agoH: 31.01, amount: 389, payee: "Demo Gas Station", channel: "card", direction: "out" },
    ],
  },
  {
    customer_ref: "CUST-0750", alias: "Customer 0750", city: "Oradea", accounts: [acct("BDEM", "0750")], phone_tail: "750",
    txs: [{ tx_id: "TX-0750-14", agoH: 3.2, amount: 2900, payee: `Transfer to ${MULE_IBAN_SHORT}`, channel: "transfer", direction: "out", newPayee: true }],
  },
  {
    customer_ref: "CUST-0089", alias: "Customer 0089", city: "Galați", accounts: [acct("BDEM", "0089")], phone_tail: "089",
    txs: [{ tx_id: "TX-0089-02", agoH: 14 * 30 * 24, amount: 640, payee: "Demo Travel Agency", channel: "card", direction: "out" }],
  },
  ...[
    ["0007", "Arad"], ["0023", "Bacău"], ["0311", "Suceava"], ["0588", "Pitești"], ["0642", "Brăila"], ["0815", "Deva"], ["0901", "Baia Mare"],
  ].map(([n, city]): DirEntry => ({
    customer_ref: `CUST-${n}`, alias: `Customer ${n}`, city, accounts: [acct("BDEM", n)], phone_tail: n.slice(1),
    txs: [
      { tx_id: `TX-${n}-03`, agoH: 20 + Number(n) % 30, amount: 150 + (Number(n) % 7) * 41.5, payee: "Demo Supermarket", channel: "card", direction: "out" },
      { tx_id: `TX-${n}-02`, agoH: 70 + Number(n) % 20, amount: 900 + (Number(n) % 5) * 120, payee: "Transfer to RO49 YBNK •••• 3301", channel: "transfer", direction: "out" },
    ],
  })),
];

function fold(s: string): string {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

export function directoryEntry(ref: string | null | undefined): DirEntry | undefined {
  return ref ? DIRECTORY.find((d) => d.customer_ref === ref) : undefined;
}

export function searchCustomers(q: string, now = Date.now()): CustomerHit[] {
  const needle = fold(q.trim());
  if (!needle) return [];
  const score = (d: DirEntry) => {
    const hay = [d.customer_ref, d.alias, d.city, ...d.accounts].map(fold);
    if (hay.some((h) => h.startsWith(needle))) return 2;
    if (hay.some((h) => h.includes(needle)) || fold(d.alias).replace(/\D/g, "").includes(needle.replace(/\D/g, "") || "~")) return 1;
    return 0;
  };
  return DIRECTORY.map((d) => ({ d, s: score(d) }))
    .filter((x) => x.s > 0)
    .sort((a, b) => b.s - a.s || a.d.customer_ref.localeCompare(b.d.customer_ref))
    .slice(0, 20)
    .map(({ d }) => ({
      customer_ref: d.customer_ref,
      alias: d.alias,
      city: d.city,
      accounts: d.accounts,
      last_tx_at: isoRo(now - Math.min(...d.txs.map((t) => t.agoH)) * H),
    }));
}

// ------------------------------------------------------------------ reading the message

const LANGS: Array<[string, string[]]> = [
  ["ro", ["nu", "am", "si", "plata", "banii", "va", "rog", "contul", "azi", "ieri", "buna", "ziua", "din", "mi", "pe", "eu", "facut"]],
  ["de", ["ich", "nicht", "und", "habe", "meine", "meinem", "konto", "zahlung", "bitte", "heute", "gestern", "ist", "von"]],
  ["hu", ["nem", "vagyok", "fizetes", "szamlam", "kerem", "tegnap", "es", "egy"]],
  ["fr", ["je", "pas", "paiement", "compte", "mon", "argent", "hier", "le", "la", "est"]],
  ["es", ["yo", "pago", "cuenta", "dinero", "hoy", "ayer", "el", "mi", "por", "favor"]],
  ["it", ["non", "pagamento", "conto", "soldi", "oggi", "ho", "il", "mio"]],
  ["en", ["the", "i", "my", "and", "did", "not", "payment", "account", "money", "from", "was", "is", "please"]],
];

/** The language with the most common words in the message; Romanian letters settle it. */
export function detectLanguage(text: string): string {
  if (/[ăâîșțşţ]/i.test(text)) return "ro";
  const words = fold(text).split(/[^a-z']+/).filter(Boolean);
  let best = "en";
  let bestN = 0;
  for (const [code, list] of LANGS) {
    const n = words.filter((w) => list.includes(w)).length;
    if (n > bestN) {
      best = code;
      bestN = n;
    }
  }
  return best;
}

export const INJECTION = /(ignore (all|any|the|previous)[^.]{0,30}(rules|instructions)|\bsystem\s*:|approve the refund (immediately|now)|ignor[ăa] (toate )?regulile|aprob[ăa] rambursarea)/i;

/** "3.200 lei", "RON 3,200.00", "2,99 lei", "512.40 RON" → numbers. */
export function parseAmounts(text: string): number[] {
  const out: number[] = [];
  const num = String.raw`\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?`;
  const re = new RegExp(String.raw`(?:(?:RON|EUR|lei)\s*(${num}))|(?:(${num})\s*(?:lei|RON|EUR|euro|€))`, "gi");
  for (const m of text.matchAll(re)) {
    const raw = (m[1] ?? m[2] ?? "").replace(/\s/g, "");
    if (!raw) continue;
    const lastSep = Math.max(raw.lastIndexOf("."), raw.lastIndexOf(","));
    let value: number;
    if (lastSep === -1) value = Number(raw);
    else {
      const decimals = raw.length - lastSep - 1;
      value = decimals === 3 ? Number(raw.replace(/[.,]/g, "")) : Number(`${raw.slice(0, lastSep).replace(/[.,]/g, "")}.${raw.slice(lastSep + 1)}`);
    }
    if (Number.isFinite(value) && value > 0 && !out.includes(value)) out.push(value);
  }
  return out;
}

function extract(text: string, receivedAt: number): IntakeExtracted {
  const t = text;
  const urls = Array.from(new Set(t.match(/https?:\/\/[^\s)"']+|\b[a-z0-9-]+\.(?:example|test)(?:\/[^\s)"']*)?/gi) ?? []));
  const phones = Array.from(new Set(t.match(/(?:\+40\s?|0)7\d{2}[\s.-]?\d{3}[\s.-]?\d{3}/g) ?? [])).map((p) => {
    const d = p.replace(/\D/g, "");
    return `+40 7•• ••• ${d.slice(-3)}`;
  });
  const dates: string[] = [];
  const day = (offset: number) => isoRo(receivedAt - offset * 24 * H).slice(0, 10);
  if (/\b(today|this morning|azi|astăzi|heute|aujourd'hui|hoy|oggi|ma)\b/i.test(t)) dates.push(day(0));
  if (/\b(yesterday|ieri|gestern|tegnap|hier|ayer)\b/i.test(t)) dates.push(day(1));
  if (/\b(last week|săptămâna trecută|saptamana trecuta|letzte woche)\b/i.test(t)) dates.push(day(7));
  const contacted_by = /\b(sms|text message|mesaj)\b/i.test(t) ? "sms"
    : /\b(call(ed)?|sunat|apel|angerufen|telefonat)\b/i.test(t) ? "apel"
      : /\b(e-?mail)\b/i.test(t) ? "email"
        : /\b(whatsapp|telegram|chat)\b/i.test(t) ? "mesagerie"
          : urls.length ? "site" : null;
  const impersonated_entity = /\b(courier|curier|kurier|parcel|colet)\b/i.test(t) ? "courier"
    : /\b(bank|banc[aă]|securit|security)\b/i.test(t) && /\b(call|sunat|apel|security|securitate)\b/i.test(t) ? "the bank"
      : /\b(police|poliți)/i.test(t) ? "the police" : null;
  return { amounts: parseAmounts(t), dates, urls, phones_masked: phones, contacted_by, impersonated_entity };
}

// ------------------------------------------------------------------ finding the customer and the payment

function identify(text: string, body: IntakePreviewBody): { entry: DirEntry; reason: string; confidence: number } | null {
  if (body.customer_ref) {
    const e = directoryEntry(body.customer_ref);
    return e ? { entry: e, reason: "Picked by the operator.", confidence: 1 } : null;
  }
  const ref = text.match(/\bCUST-(?:DEMO-)?\d{2,4}\b/i)?.[0]?.toUpperCase();
  const byRef = directoryEntry(ref);
  if (byRef) return { entry: byRef, reason: "The message gives the customer reference.", confidence: 0.99 };
  const alias = text.match(/\b(?:customer|client(?:ul)?|kunde)\s+(\d{4})\b/i)?.[1];
  const byAlias = alias ? DIRECTORY.find((d) => d.alias.endsWith(alias)) : undefined;
  if (byAlias) return { entry: byAlias, reason: "The message names the customer's alias.", confidence: 0.95 };
  for (const p of text.match(/(?:\+40\s?|0)7\d{2}[\s.-]?\d{3}[\s.-]?\d{3}/g) ?? []) {
    const digits = p.replace(/\D/g, "");
    const e = DIRECTORY.find((d) => digits.endsWith(d.phone_tail.padStart(3, "0")) && digits.slice(-6, -3) === "000");
    if (e) return { entry: e, reason: "The phone number in the message matches the customer's file.", confidence: 0.9 };
  }
  const tail = text.match(/\bRO\d{2}\s?BDEM[\s•]*(?:[•\d]{4}\s?){0,3}(\d{4})\b/i)?.[1];
  const byAcct = tail ? DIRECTORY.find((d) => d.accounts.some((a) => a.endsWith(tail))) : undefined;
  if (byAcct) return { entry: byAcct, reason: "The account number in the message matches.", confidence: 0.85 };
  return null;
}

function candidatesFor(entry: DirEntry, db: MockDb | null, ex: IntakeExtracted, body: IntakePreviewBody, receivedAt: number, text: string): TxCandidate[] {
  const txs: TxSeed[] = [...entry.txs];
  // Demo Bank's own ledger for the two demo customers: a payment made in this session counts too
  for (const t of db?.bank[entry.customer_ref]?.transactions ?? []) {
    if (t.direction !== "out" || txs.some((x) => x.tx_id === t.id)) continue;
    if (txs.some((x) => Math.abs(x.amount - Math.abs(t.amount)) < 0.01 && x.payee === t.description)) continue;
    txs.push({ tx_id: t.id, agoH: (receivedAt - new Date(t.ts).getTime()) / H, amount: Math.abs(t.amount), payee: t.description, channel: /transfer/i.test(t.description) ? "transfer" : "card", direction: "out", newPayee: /XBNK/.test(t.description) });
  }
  const amounts = (ex.amounts ?? []).map((a) => (typeof a === "number" ? a : a.value));
  const fraudClaim = /\b(didn'?t|did not|not me|nu eu|n-am|nu am făcut|nu am facut|nicht gemacht|unauthori[sz]ed|neautorizat)/i.test(text);
  const scored = txs.filter((t) => t.direction === "out").map((t) => {
    let s = 0;
    const reasons: string[] = [];
    const exact = amounts.find((a) => Math.abs(a - t.amount) < 0.01);
    const close = !exact && amounts.find((a) => Math.abs(a - t.amount) / t.amount < 0.1);
    if (exact) {
      s += 0.55;
      reasons.push(`Amount matches ${money(t.amount)}`);
    } else if (close) {
      s += 0.3;
      reasons.push(`Amount close to ${money(close)}`);
    }
    const ago = t.agoH;
    const mentionsLastWeek = (ex.dates ?? []).some((d) => d === isoRo(receivedAt - 7 * 24 * H).slice(0, 10));
    const txDay = isoRo(receivedAt - t.agoH * H).slice(0, 10);
    if (!mentionsLastWeek && (ex.dates ?? []).includes(txDay)) {
      s += 0.2;
      reasons.push(txDay === isoRo(receivedAt).slice(0, 10) ? "Same day as the message" : "On the day the message mentions");
    } else if (mentionsLastWeek && ago >= 4 * 24 && ago <= 10 * 24) {
      s += 0.15;
      reasons.push("In the week the message mentions");
    } else if (ago <= 6) {
      s += 0.1;
      reasons.push("Made shortly before the message");
    }
    if (body.channel_hint && (body.channel_hint === t.channel || (body.channel_hint.startsWith("transfer") && t.channel.startsWith("transfer")))) {
      s += 0.08;
      reasons.push("Payment type matches");
    }
    if (fraudClaim && t.newPayee) {
      s += 0.12;
      reasons.push("New payee");
    }
    if (ex.urls?.length && t.channel !== "card" && t.newPayee) s += 0.05;
    return {
      tx_id: t.tx_id,
      amount: t.amount,
      currency: "RON",
      ts: isoRo(receivedAt - t.agoH * H),
      payee: t.payee,
      channel: t.channel,
      direction: t.direction,
      score: Math.min(0.99, Math.round(s * 100) / 100),
      reasons,
    } satisfies TxCandidate;
  });
  return scored.filter((c) => c.score >= 0.15).sort((a, b) => b.score - a.score).slice(0, 4);
}

export function matchFor(found: ReturnType<typeof identify>, candidates: TxCandidate[]): MatchResult {
  if (!found) {
    return {
      customer_ref: null,
      customer_match_reason: null,
      tx_id: null,
      confidence: 0,
      needs_human: true,
      reason: "No customer found from the message. VersoML asks the customer to confirm who they are and which payment it is.",
      candidates: [],
    };
  }
  const [top, second] = candidates;
  const base = { customer_ref: found.entry.customer_ref, customer_match_reason: found.reason };
  if (!top || top.score < 0.4) {
    return { ...base, tx_id: null, confidence: top?.score ?? 0, needs_human: true, reason: "No payment matches the amount or the date in the message.", candidates };
  }
  if ((top.score >= 0.75 && (!second || top.score - second.score >= 0.25)) || (top.score >= 0.55 && (!second || second.score < 0.3))) {
    return { ...base, tx_id: top.tx_id, confidence: top.score, needs_human: false, reason: "One payment matches what the message says.", candidates };
  }
  return {
    ...base,
    tx_id: null,
    confidence: top.score,
    needs_human: true,
    reason: second ? "More than one payment could match. A person picks the right one." : "The best match is weak. A person confirms the payment.",
    candidates,
  };
}

export function previewIntake(db: MockDb | null, body: IntakePreviewBody, now = Date.now()): IntakePreview {
  const all = [body.text, ...(body.attachments ?? []).map((a) => a.content)].join("\n");
  const receivedAt = body.received_at ? new Date(body.received_at).getTime() || now : now;
  const extracted = extract(all, receivedAt);
  const found = identify(all, body);
  const candidates = found ? candidatesFor(found.entry, db, extracted, body, receivedAt, all) : [];
  return {
    language: detectLanguage(body.text),
    injection_suspected: INJECTION.test(all),
    customer: found ? { customer_ref: found.entry.customer_ref, alias: found.entry.alias, match_reason: found.reason, confidence: found.confidence } : null,
    match: matchFor(found, candidates),
    extracted,
  };
}

/** The match a case gets when the customer picked the payment in the app (Demo Bank and the seeded inbox). */
export function appMatch(customerRef: string, tx: { tx_id: string; amount: number; ts: string; payee: string; channel: string }): MatchResult {
  return {
    customer_ref: customerRef,
    customer_match_reason: "Signed in to the Demo Bank app.",
    tx_id: tx.tx_id,
    confidence: 0.99,
    needs_human: false,
    reason: "The customer picked the payment in the app.",
    candidates: [{ ...tx, currency: "RON", direction: "out", score: 0.99, reasons: ["Picked by the customer in the app"] }],
  };
}
