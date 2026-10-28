/**
 * Calendar RO aproximativ, doar pentru modul mock. Termenele reale le calculează backend-ul
 * (`versoml/shared/rules/calendar_ro.py`); aici sărim peste weekenduri și sărbătorile legale fixe din 2026–2027.
 */
const HOLIDAYS = new Set([
  "2026-01-01", "2026-01-02", "2026-01-06", "2026-01-07", "2026-01-24", "2026-04-10", "2026-04-12", "2026-04-13",
  "2026-05-01", "2026-05-31", "2026-06-01", "2026-08-15", "2026-11-30", "2026-12-01", "2026-12-25", "2026-12-26",
  "2027-01-01", "2027-01-02", "2027-01-06", "2027-01-07", "2027-01-24",
]);

const TZ = "Europe/Bucharest";

/** Ofsetul României față de UTC, în minute, la momentul dat (EET +120 / EEST +180). */
export function bucharestOffset(at: Date): number {
  const parts = new Intl.DateTimeFormat("en-US", { timeZone: TZ, timeZoneName: "shortOffset" }).formatToParts(at);
  const name = parts.find((p) => p.type === "timeZoneName")?.value ?? "GMT+2";
  const m = name.match(/GMT([+-])(\d{1,2})(?::(\d{2}))?/);
  if (!m) return 120;
  const sign = m[1] === "-" ? -1 : 1;
  return sign * (Number(m[2]) * 60 + Number(m[3] ?? 0));
}

interface Ymd {
  y: number;
  m: number;
  d: number;
}

export function bucharestYmd(at: Date): Ymd {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(at);
  const get = (t: string) => Number(parts.find((p) => p.type === t)?.value);
  return { y: get("year"), m: get("month"), d: get("day") };
}

const key = (v: Ymd) => `${v.y}-${String(v.m).padStart(2, "0")}-${String(v.d).padStart(2, "0")}`;

function addDays(v: Ymd, n: number): Ymd {
  const dt = new Date(Date.UTC(v.y, v.m - 1, v.d + n));
  return { y: dt.getUTCFullYear(), m: dt.getUTCMonth() + 1, d: dt.getUTCDate() };
}

export function isBusinessDay(v: Ymd): boolean {
  const dow = new Date(Date.UTC(v.y, v.m - 1, v.d)).getUTCDay();
  return dow !== 0 && dow !== 6 && !HOLIDAYS.has(key(v));
}

/** ISO cu ofsetul României, ex. „2026-10-29T23:59:59+02:00". */
export function bucharestIso(v: Ymd, hh: number, mm: number, ss: number): string {
  const probe = new Date(Date.UTC(v.y, v.m - 1, v.d, 12));
  const off = bucharestOffset(probe);
  const sign = off >= 0 ? "+" : "-";
  const abs = Math.abs(off);
  const tz = `${sign}${String(Math.floor(abs / 60)).padStart(2, "0")}:${String(abs % 60).padStart(2, "0")}`;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${key(v)}T${p(hh)}:${p(mm)}:${p(ss)}${tz}`;
}

/** Sfârșitul zilei lucrătoare următoare (PAY-03), 23:59:59 ora României. */
export function endOfNextBusinessDay(from: Date): string {
  let day = addDays(bucharestYmd(from), 1);
  while (!isBusinessDay(day)) day = addDays(day, 1);
  return bucharestIso(day, 23, 59, 59);
}

/** Ziua lucrătoare N după data dată (CMP-01: 15 zile lucrătoare), la 23:59:59. */
export function addBusinessDays(from: Date, n: number): string {
  let day = bucharestYmd(from);
  let left = n;
  while (left > 0) {
    day = addDays(day, 1);
    if (isBusinessDay(day)) left -= 1;
  }
  return bucharestIso(day, 23, 59, 59);
}

/** ISO cu ofsetul României pentru un moment dat (pentru câmpurile `ts`, `retrieved_at`). */
export function isoRo(at: Date | number): string {
  const dt = typeof at === "number" ? new Date(at) : at;
  const off = bucharestOffset(dt);
  const local = new Date(dt.getTime() + off * 60_000);
  const p = (n: number) => String(n).padStart(2, "0");
  const sign = off >= 0 ? "+" : "-";
  const abs = Math.abs(off);
  return (
    `${local.getUTCFullYear()}-${p(local.getUTCMonth() + 1)}-${p(local.getUTCDate())}T` +
    `${p(local.getUTCHours())}:${p(local.getUTCMinutes())}:${p(local.getUTCSeconds())}` +
    `${sign}${p(Math.floor(abs / 60))}:${p(abs % 60)}`
  );
}
