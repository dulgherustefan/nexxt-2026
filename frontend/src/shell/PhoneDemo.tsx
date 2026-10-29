import { X } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { cx } from "../ui/kit";
import { isLocalOrigin, PUBLIC_SITE, QrCode } from "../ui/QrCode";

/** The QR codes the jury scans from the projector: the fake courier page, then Demo Bank. */
export function PhoneDemoDialog({ onClose }: { onClose: () => void }) {
  // a phone can't open localhost: the public site reaches the same server through the tunnel
  const origin = isLocalOrigin(window.location.origin) ? PUBLIC_SITE : window.location.origin;
  const [client, setClient] = useState<1 | 2>(1);
  const closeRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const bankUrl = client === 1 ? `${origin}/bank` : `${origin}/bank?client=CUST-DEMO-02`;

  // once, on open: focus Close, Escape closes, focus returns to where it was
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onCloseRef.current();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      prev?.focus();
    };
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink/30 p-4 backdrop-blur-[2px] sm:items-center" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-labelledby="phone-demo-title" onClick={(e) => e.stopPropagation()}
        className="w-full max-w-[48rem] animate-enter rounded-2xl bg-paper shadow-[var(--shadow-overlay)]">
        <header className="flex items-center justify-between gap-3 px-6 pt-5 pb-2">
          <div>
            <h2 id="phone-demo-title" className="text-[1.15rem] font-semibold">Try it on a phone</h2>
            <p className="text-[0.9333rem] text-muted">Two scans: the scam, then the bank app.</p>
          </div>
          <button ref={closeRef} type="button" onClick={onClose} aria-label="Close" className="grid size-8 place-items-center rounded-full text-muted hover:bg-hover hover:text-ink">
            <X size={16} />
          </button>
        </header>

        <div className="flex flex-col gap-5 px-6 pt-3 pb-6">
          <ol className="grid gap-4 md:grid-cols-2">
            <li className="flex flex-col items-center gap-3 rounded-xl bg-canvas p-5 text-center">
              <p className="flex items-center gap-2 font-medium"><Step n={1} /> The fake courier page</p>
              <p className="text-[0.9333rem] text-muted">The link from the “courier” text message. Fill it in like a victim would.</p>
              <QrCode text={`${origin}/demo/delivery`} label="QR code to the fake courier page" className="w-full max-w-[12rem] rounded-lg" />
              <p className="font-mono text-[0.75rem] break-all text-subtle">{origin}/demo/delivery</p>
            </li>
            <li className="flex flex-col items-center gap-3 rounded-xl bg-canvas p-5 text-center">
              <p className="flex items-center gap-2 font-medium"><Step n={2} /> Demo Bank</p>
              <p className="text-[0.9333rem] text-muted">The RON 3,200.00 payment shows up. Tap “I didn’t make this payment”.</p>
              <QrCode text={bankUrl} label={`QR code to Demo Bank, customer ${client}`} className="w-full max-w-[12rem] rounded-lg" />
              <p className="font-mono text-[0.75rem] break-all text-subtle">{bankUrl}</p>
              <div role="radiogroup" aria-label="Demo Bank customer" className="inline-flex rounded-full bg-paper p-0.5 text-[0.8667rem] shadow-[var(--shadow-card)]">
                {([1, 2] as const).map((n) => (
                  <button key={n} type="button" role="radio" aria-checked={client === n} onClick={() => setClient(n)}
                    className={cx("rounded-full px-3 py-1 font-medium transition-colors", client === n ? "bg-ink text-paper" : "text-muted hover:text-ink")}>
                    {n === 1 ? "First juror" : "Second juror"}
                  </button>
                ))}
              </div>
            </li>
          </ol>

          <p className="text-center text-[0.9333rem] text-muted">The claim appears in the case list within seconds. Approve the refund here and the phone shows the money back.</p>
        </div>
      </div>
    </div>
  );
}

function Step({ n }: { n: number }) {
  return <span aria-hidden className="grid size-5 place-items-center rounded-full bg-ink text-[0.72rem] font-semibold text-paper">{n}</span>;
}
