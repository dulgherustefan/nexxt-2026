import { ArrowRight, Check, CircleNotch, CreditCard, Package, Warning, WarningCircle, WarningOctagon, X } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useApi } from "../../api/runtime";
import { cx } from "../../ui/kit";
import { amountText, clientFrom, dayMonth, useThemeColor } from "./bankModel";

/**
 * The demo's fake page ("Demo Courier", a fictional brand). The card fields hold fixed test values
 * and are not form fields: nothing in them is sent or kept. The button only asks the server to
 * simulate the fraudster's payment out of the demo customer's account.
 */

const TEST_CARD: Array<{ label: string; value: string; wide?: boolean; card?: boolean }> = [
  { label: "Card number", value: "4242 4242 4242 4242", wide: true, card: true },
  { label: "Expiry date", value: "12/29" },
  { label: "Security code", value: "123" },
  { label: "Name on card", value: "Demo Customer", wide: true },
];

const FEE = "RON 2.99";

/** The banner's red, also used for the phone's browser bar. */
const DEMO_RED = "#c4321d";

export default function FakePage() {
  const api = useApi();
  const [search] = useSearchParams();
  const ref = clientFrom(search);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [paid, setPaid] = useState<{ amount: number } | null>(null);

  useEffect(() => {
    document.title = "DEMO · Demo Courier (fake page)";
  }, []);
  useThemeColor(DEMO_RED);

  const bankQuery = new URLSearchParams();
  if (search.get("client")) bankQuery.set("client", ref);
  if (search.get("mock")) bankQuery.set("mock", search.get("mock") as string);
  const bankHref = `/bank${bankQuery.toString() ? `?${bankQuery.toString()}` : ""}`;

  async function pay() {
    setBusy(true);
    setError(null);
    try {
      // only the demo customer's reference: the card details go nowhere
      const out = await api.demoScam({ customer_ref: ref });
      setPaid({ amount: typeof out?.amount === "number" ? out.amount : 0 });
      window.scrollTo({ top: 0 });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-dvh bg-canvas text-ink">
      <div role="note" className="sticky top-0 z-50 bg-danger px-4 pt-[max(0.625rem,env(safe-area-inset-top))] pb-2.5 text-paper">
        <p className="mx-auto flex max-w-md items-center justify-center gap-2 text-center text-[0.9333rem] font-semibold">
          <Warning aria-hidden size={18} weight="bold" className="shrink-0" />
          <span>Demo page. Do not enter real card details.</span>
        </p>
      </div>

      <header className="border-b border-line bg-paper">
        <div className="mx-auto flex max-w-md items-center gap-2.5 px-4 py-3.5">
          <span aria-hidden className="grid size-8 place-items-center rounded-lg bg-ink text-paper">
            <Package size={18} weight="bold" />
          </span>
          <span className="font-semibold tracking-[-0.01em]">Demo Courier</span>
          <span className="ml-auto text-[0.8667rem] text-muted">Parcel tracking</span>
        </div>
      </header>

      <main className="mx-auto max-w-md px-4 pt-5 pb-10">
        {paid ? <Result amount={paid.amount} bankHref={bankHref} /> : <Checkout busy={busy} error={error} onPay={pay} />}
      </main>

      <footer className="mx-auto max-w-md px-4 pb-[max(1.5rem,env(safe-area-inset-bottom))] text-[0.8rem] text-subtle">
        Demo Courier is a fictional brand made for the VersoML demo. This page doesn’t collect or keep card details.
      </footer>
    </div>
  );
}

// ------------------------------------------------------------------ the "redelivery fee" page

function Checkout({ busy, error, onPay }: { busy: boolean; error: string | null; onPay: () => void }) {
  const now = Date.now();
  const day = (offset: number) => dayMonth(new Date(now - offset * 86_400_000), now);
  const events = [
    { label: "Picked up from the sender", when: day(2), ok: true },
    { label: "Arrived at your local depot", when: day(1), ok: true },
    { label: "Delivery attempt failed", when: "Today", ok: false, note: "The address is incomplete." },
  ];

  return (
    <>
      <h1 className="text-[1.6rem] leading-tight font-semibold tracking-[-0.02em]">Your parcel couldn’t be delivered</h1>
      <p className="mt-1.5 text-ink-soft">Pay the {FEE} redelivery fee and we’ll bring it tomorrow.</p>

      <section aria-label="Parcel" className="mt-5 rounded-2xl bg-paper p-4 shadow-[var(--shadow-card)]">
        <div className="flex items-center justify-between gap-3 text-[0.8667rem]">
          <span className="text-muted">Tracking number</span>
          <span className="tnum font-mono text-[0.8rem] text-ink-soft">CD 4821 0033 917</span>
        </div>
        <ol className="mt-4 flex flex-col gap-3.5">
          {events.map((e) => (
            <li key={e.label} className="flex items-start gap-3">
              <span
                aria-hidden
                className={cx("mt-0.5 grid size-5 shrink-0 place-items-center rounded-full text-paper", e.ok ? "bg-ink" : "bg-danger")}
              >
                {e.ok ? <Check size={11} weight="bold" /> : <X size={11} weight="bold" />}
              </span>
              <span className="min-w-0 flex-1">
                <span className={cx("block text-[0.9333rem]", e.ok ? "text-ink-soft" : "font-semibold text-ink")}>{e.label}</span>
                {e.note && <span className="block text-[0.8667rem] text-muted">{e.note}</span>}
              </span>
              <span className="tnum shrink-0 text-[0.8rem] text-muted">{e.when}</span>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="card-title" className="mt-4 rounded-2xl bg-paper p-4 shadow-[var(--shadow-card)]">
        <h2 id="card-title" className="font-semibold">Card details</h2>
        <div className="mt-3 grid grid-cols-2 gap-3">
          {TEST_CARD.map((f) => (
            <div key={f.label} className={f.wide ? "col-span-2" : undefined}>
              <p className="text-[0.8rem] font-medium text-muted">{f.label}</p>
              <div
                role="textbox"
                aria-readonly="true"
                aria-label={f.label}
                className="tnum mt-1 flex h-12 items-center justify-between gap-2 rounded-xl bg-canvas px-3.5 font-medium text-ink-soft shadow-[inset_0_0_0_1px_var(--color-line-strong)] select-none"
              >
                {f.value}
                {f.card && <CreditCard aria-hidden size={20} className="text-subtle" />}
              </div>
            </div>
          ))}
        </div>
        <p className="mt-3 text-[0.8rem] text-muted">Test values, filled in for the demo. You can’t edit them, and they aren’t sent anywhere.</p>

        <div className="mt-4 flex items-center justify-between border-t border-line pt-4">
          <span className="text-ink-soft">Redelivery fee</span>
          <span className="tnum font-semibold">{FEE}</span>
        </div>

        {error && (
          <p role="alert" className="mt-4 flex items-start gap-2 rounded-xl bg-danger-soft px-3.5 py-3 text-[0.9333rem] text-danger">
            <WarningCircle aria-hidden size={18} className="mt-px shrink-0" />
            <span>The demo payment didn’t start. {/[.!?]$/.test(error.trim()) ? error.trim() : `${error.trim()}.`} Try again.</span>
          </p>
        )}

        <button
          type="button"
          onClick={onPay}
          disabled={busy}
          aria-busy={busy || undefined}
          className="press mt-4 inline-flex h-[3.25rem] w-full items-center justify-center gap-2 rounded-xl bg-ink text-[1rem] font-semibold text-paper transition-colors hover:bg-ink-soft disabled:cursor-not-allowed disabled:opacity-60"
        >
          {busy && <CircleNotch aria-hidden size={18} weight="bold" className="animate-spin" />}
          {busy ? "Processing…" : `Pay ${FEE}`}
        </button>
      </section>
    </>
  );
}

// ------------------------------------------------------------------ the reveal

function Result({ amount, bankHref }: { amount: number; bankHref: string }) {
  const sum = amount > 0 ? amountText(amount) : null;
  return (
    <div role="status" className="animate-enter">
      <span className="grid size-12 place-items-center rounded-full bg-danger-soft text-danger">
        <WarningOctagon aria-hidden size={26} weight="fill" />
      </span>
      <h1 className="mt-4 text-[1.75rem] leading-tight font-semibold tracking-[-0.025em]">You were scammed (demo).</h1>
      <p className="mt-2 text-[1.15rem] text-ink-soft">
        {sum ? (
          <>
            <span className="tnum font-semibold text-ink">{sum}</span> just left your account.
          </>
        ) : (
          "The money just left your account."
        )}
      </p>

      <section aria-labelledby="what-happened" className="mt-6 rounded-2xl bg-paper p-4 shadow-[var(--shadow-card)]">
        <h2 id="what-happened" className="font-semibold">What happened</h2>
        <ol className="mt-3 flex flex-col gap-3 text-[0.9333rem] text-ink-soft">
          {[
            `The page asked for ${FEE} as a “delivery fee”.`,
            `With the card details on this page, the scammer sent ${sum ?? "money"} from your account to an account they control.`,
            "For a payment you didn’t authorize, your bank must refund you by the end of the next business day.",
          ].map((line, i) => (
            <li key={i} className="flex gap-3">
              <span aria-hidden className="tnum grid size-6 shrink-0 place-items-center rounded-full bg-canvas text-[0.8rem] font-semibold text-ink">
                {i + 1}
              </span>
              <span className="pt-0.5">{line}</span>
            </li>
          ))}
        </ol>
      </section>

      <Link
        to={bankHref}
        className="press group mt-6 inline-flex h-[3.25rem] w-full items-center justify-center gap-2.5 rounded-full bg-ink pr-2 pl-6 text-[1rem] font-medium text-paper shadow-[0_1px_2px_rgb(18_19_22/0.15)] transition-colors hover:bg-ink-soft"
      >
        <span className="flex-1 text-center">Open Demo Bank</span>
        <span className="grid size-9 place-items-center rounded-full bg-paper text-ink transition-transform duration-200 ease-[var(--ease-out)] group-hover:translate-x-0.5">
          <ArrowRight aria-hidden size={16} weight="bold" />
        </span>
      </Link>
      <p className="mt-3 text-center text-[0.8667rem] text-muted">
        Then tap “I didn’t make this payment” on today’s <span className="whitespace-nowrap">{sum ? `${sum} transfer` : "transfer"}</span>.
      </p>
    </div>
  );
}
