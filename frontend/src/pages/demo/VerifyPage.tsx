import { ArrowClockwise, CheckCircle, SealCheck, SealWarning, XCircle } from "@phosphor-icons/react";
import { useEffect } from "react";
import { useLocation, useParams } from "react-router";
import { dateTime, shortHash } from "../../api/format";
import { useApi, useResource } from "../../api/runtime";
import type { LedgerResponse, VerifyResult } from "../../api/types";
import { cx, Skeleton } from "../../ui/kit";
import { Logo } from "../../ui/Logo";
import { usePageTheme } from "../../ui/ThemeToggle";
import { useThemeColor } from "./bankModel";

type Outcome = "intact" | "mismatch" | "broken" | "unsealed" | "missing";

interface Check {
  ledger: LedgerResponse & { sealed?: boolean };
  verify: VerifyResult | null;
}

/** What the page concludes, in the order that matters: a file that exists, is sealed, verifies and matches the QR code. */
function outcome(c: Check, scanned: string): Outcome {
  if (!c.ledger.facts.length) return "missing";
  if (!c.ledger.seal) return "unsealed";
  if (!c.verify?.valid) return "broken";
  if (scanned && scanned !== c.ledger.seal.root) return "mismatch";
  return "intact";
}

const COPY: Record<Outcome, { title: string; body: string }> = {
  intact: {
    title: "Evidence file intact",
    body: "Nothing in the file changed since the bank sealed it. Every item, the order they were collected in and the bank’s signature check out.",
  },
  mismatch: {
    title: "This code is for an older seal",
    body: "The file on record verifies, but its signed root differs from the one in this QR code. Ask the bank for the current evidence file.",
  },
  broken: {
    title: "The file doesn’t verify",
    body: "At least one check failed: the file was changed after it was sealed. The failed checks are marked below.",
  },
  unsealed: {
    title: "Not sealed yet",
    body: "The case is still open. The bank seals the evidence file when the case closes; this page checks it from then on.",
  },
  missing: {
    title: "No evidence file with this ID",
    body: "Check the case ID, or scan the code again.",
  },
};

/**
 * The page the seal's QR code opens. Anyone can scan it: it asks the bank's server to check the file
 * again (hash chain, Merkle root, Ed25519 signature) and compares the root with the one in the code.
 */
export default function VerifyPage() {
  usePageTheme("light");
  useThemeColor("#fee600");
  const { id = "" } = useParams();
  const scanned = useLocation().hash.replace(/^#/, "").toLowerCase();
  const api = useApi();
  const res = useResource<Check>(async () => {
    const ledger = (await api.ledger(id)) as Check["ledger"];
    const verify = ledger.seal ? await api.verify({ case_id: id, facts: ledger.facts, seal: ledger.seal }) : null;
    return { ledger, verify };
  }, [api, id]);

  useEffect(() => {
    document.title = `Evidence check · ${id}`;
  }, [id]);

  const c = res.data;
  const result = c ? outcome(c, scanned) : null;
  const good = result === "intact";
  const seal = c?.ledger.seal;

  return (
    <div className="min-h-dvh bg-canvas text-ink">
      <header className="bg-yellow text-on-yellow">
        <div className="mx-auto flex max-w-[34rem] items-center justify-between gap-4 px-4 pt-[max(1rem,env(safe-area-inset-top))] pb-4">
          <Logo onYellow className="text-[1.05rem]" />
          <span className="text-[0.8667rem] font-medium">Evidence check</span>
        </div>
      </header>

      <main className="mx-auto flex max-w-[34rem] flex-col gap-4 px-4 pt-6 pb-[max(2rem,env(safe-area-inset-bottom))]">
        <p className="text-[0.8667rem] text-muted">
          Case <span className="id-text font-medium text-ink-soft">{id}</span>
        </p>

        {res.error && !c ? (
          <section className="rounded-2xl bg-paper p-5 shadow-[var(--shadow-card)]" role="alert">
            <p className="flex items-center gap-2 text-[1.2rem] font-semibold tracking-[-0.02em]">
              <SealWarning size={24} className="text-warn" /> The bank’s server didn’t answer
            </p>
            <p className="mt-2 text-ink-soft">The check runs on the bank’s server, and it isn’t reachable right now. Try again in a minute.</p>
            <button type="button" onClick={res.reload} className="press mt-4 inline-flex h-10 items-center gap-2 rounded-full bg-yellow px-5 font-medium text-on-yellow hover:bg-yellow-hover">
              <ArrowClockwise size={16} /> Check again
            </button>
          </section>
        ) : !c || !result ? (
          <section className="flex flex-col gap-3 rounded-2xl bg-paper p-5 shadow-[var(--shadow-card)]" role="status" aria-label="Checking the evidence file">
            <Skeleton className="h-7 w-2/3" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-4/5" />
          </section>
        ) : (
          <>
            <section className="animate-enter overflow-hidden rounded-2xl bg-paper shadow-[var(--shadow-card)]" aria-live="polite">
              <div className={cx("flex items-start gap-3.5 px-5 pt-5 pb-4", good && "bg-yellow-tint")}>
                <span className={cx(
                  "grid size-11 shrink-0 place-items-center rounded-full",
                  good ? "bg-yellow text-on-yellow" : result === "broken" ? "bg-danger-soft text-danger" : "bg-hover text-muted",
                )}>
                  {good ? <SealCheck size={24} weight="fill" /> : <SealWarning size={24} weight={result === "broken" ? "fill" : "regular"} />}
                </span>
                <div className="min-w-0">
                  <h1 className="text-[1.35rem] leading-tight font-semibold tracking-[-0.02em] text-balance">{COPY[result].title}</h1>
                  <p className="mt-1.5 text-[0.9333rem] text-ink-soft text-pretty">{COPY[result].body}</p>
                </div>
              </div>
              {seal && (
                <dl className="grid grid-cols-2 gap-x-4 gap-y-3 border-t border-line px-5 py-4 text-[0.9333rem]">
                  <div>
                    <dt className="text-[0.8rem] text-muted">Items</dt>
                    <dd className="tnum mt-0.5 font-medium">{seal.count}</dd>
                  </div>
                  <div>
                    <dt className="text-[0.8rem] text-muted">Sealed</dt>
                    <dd className="mt-0.5 font-medium">{dateTime(seal.sealed_at)}</dd>
                  </div>
                  <div className="col-span-2">
                    <dt className="text-[0.8rem] text-muted">Signed root</dt>
                    <dd className="mt-0.5 font-mono text-[0.8rem] break-all text-ink-soft">{seal.root}</dd>
                  </div>
                  {scanned && (
                    <div className="col-span-2 flex items-center gap-1.5 text-[0.8667rem]">
                      {scanned === seal.root
                        ? <><CheckCircle size={16} weight="fill" className="text-ok" /> <span>Matches the root in the QR code</span></>
                        : <><XCircle size={16} weight="fill" className="text-danger" /> <span>The QR code has <span className="font-mono">{shortHash(scanned, 12)}</span></span></>}
                    </div>
                  )}
                </dl>
              )}
            </section>

            {c.verify && (
              <section className="rounded-2xl bg-paper px-5 py-4 shadow-[var(--shadow-card)]" aria-labelledby="checks-title">
                <h2 id="checks-title" className="font-semibold">What was checked</h2>
                <ul className="mt-3 flex flex-col gap-3">
                  {c.verify.checks.map((k) => (
                    <li key={k.name} className="flex gap-2.5">
                      {k.ok
                        ? <CheckCircle size={18} weight="fill" className="mt-0.5 shrink-0 text-ok" />
                        : <XCircle size={18} weight="fill" className="mt-0.5 shrink-0 text-danger" />}
                      <div className="min-w-0">
                        <p className="text-[0.9333rem] font-medium">{k.name}</p>
                        {k.detail && <p className="text-[0.8667rem] text-muted">{k.detail}</p>}
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {seal && (
              <p className="px-1 text-[0.8rem] leading-relaxed text-muted">
                The bank signs the file’s Merkle root with its Ed25519 key{" "}
                <span className="font-mono text-ink-soft" title={seal.public_key}>{shortHash(seal.public_key, 10)}</span>.
                {" "}This page asks the bank’s server to run every check again each time it opens.
              </p>
            )}
            <button
              type="button"
              onClick={res.reload}
              disabled={res.loading}
              className="press inline-flex h-10 w-fit items-center gap-2 rounded-full bg-paper px-4 text-[0.9333rem] font-medium shadow-[var(--shadow-card)] hover:bg-hover disabled:opacity-60"
            >
              <ArrowClockwise size={16} className={cx(res.loading && "animate-spin")} /> Check again
            </button>
          </>
        )}

        <p className="mt-4 px-1 text-[0.75rem] text-subtle">Synthetic data. Demo Bank is not a real bank.</p>
      </main>
    </div>
  );
}
