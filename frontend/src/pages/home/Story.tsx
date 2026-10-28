// Scroll story adapted from "Scroll Reveal Content A" (abui, on 21st.dev): a pinned visual with
// numbered steps whose progress bars follow the scroll.
import { AnimatePresence, m, useMotionValueEvent, useReducedMotion, useScroll } from "motion/react";
import { useRef, useState, type ReactNode } from "react";
import { BorderBeam } from "../../components/fx/BorderBeam";
import { cx } from "../../ui/kit";
import { ClaimScene, DecisionScene, EvidenceScene, RecoveryScene, RefundScene } from "./scenes";

const EASE = [0.22, 1, 0.36, 1] as const;

const STEPS: Array<{ title: string; body: string; scene: (animate: boolean) => ReactNode }> = [
  {
    title: "The claim comes in",
    body: "The customer taps “I didn’t make this payment” in the banking app.",
    scene: () => <ClaimScene />,
  },
  {
    title: "The evidence arrives",
    body: "Payment, 3-D Secure, device and the fake website, each saved with a fingerprint.",
    scene: (a) => <EvidenceScene animate={a} />,
  },
  {
    title: "The rules decide",
    body: "Rule PAY-03 decides, not a model: refund by the end of the next business day.",
    scene: () => <DecisionScene />,
  },
  {
    title: "The customer gets the money back",
    body: "Under RON 5,000 it goes out on its own. Above that, a person approves it in one click.",
    scene: (a) => <RefundScene animate={a} />,
  },
  {
    title: "Recovery starts",
    body: "A chargeback is drafted only if it can win, and the customer gets a letter.",
    scene: () => <RecoveryScene />,
  },
];

export default function Story() {
  const ref = useRef<HTMLElement>(null);
  const reduce = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end end"] });
  const [progress, setProgress] = useState(0);
  useMotionValueEvent(scrollYProgress, "change", (v) => setProgress(Math.round(v * 400) / 400));
  const n = STEPS.length;
  const step = Math.min(n - 1, Math.floor(progress * n * 0.999));

  return (
    <section ref={ref} id="how" aria-label="How a case runs" className="relative hidden lg:block" style={{ height: `${n * 90}vh` }}>
      <div className="sticky top-0 flex h-dvh items-center overflow-hidden">
        <div className="mx-auto grid w-full max-w-[1200px] grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] items-center gap-16 px-8">
          <div>
            <p className="text-[0.9333rem] font-medium text-night-muted">How a case runs</p>
            <h2 className="mt-3 max-w-[16ch] text-[2.6rem] leading-[1.06] font-semibold tracking-[-0.03em] text-night-text">From claim to refund in one sitting.</h2>
            <ol className="mt-10 flex flex-col">
              {STEPS.map((s, i) => {
                const fill = Math.max(0, Math.min(1, progress * n - i));
                const active = i === step;
                return (
                  <li key={s.title} className="grid grid-cols-[2px_minmax(0,1fr)] gap-x-5">
                    <span className="relative block bg-white/10">
                      <span className="absolute inset-x-0 top-0 block bg-yellow" style={{ height: `${fill * 100}%` }} />
                    </span>
                    <div className="pb-6">
                      <p className="flex items-baseline gap-3">
                        <span className={cx("tnum text-[0.8rem] transition-colors duration-300", active ? "text-yellow" : "text-night-muted")}>{String(i + 1).padStart(2, "0")}</span>
                        <span className={cx("text-[1.15rem] font-semibold transition-colors duration-300", active ? "text-night-text" : "text-night-muted")}>{s.title}</span>
                      </p>
                      <m.div
                        initial={false}
                        animate={{ height: active ? "auto" : 0, opacity: active ? 1 : 0 }}
                        transition={{ duration: 0.35, ease: EASE }}
                        className="overflow-hidden"
                      >
                        <p className="mt-2 max-w-[44ch] pl-8 leading-relaxed text-night-muted">{s.body}</p>
                      </m.div>
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>
          <div className="relative h-[420px] rounded-[28px] bg-[#131416] ring-1 ring-white/10 shadow-[0_40px_120px_-40px_rgb(254_230_0/0.18)]">
            <BorderBeam size={160} duration={9} />
            <div className="flex h-12 items-center gap-2 border-b border-white/[0.07] px-5">
              <span className="id-text text-[0.8rem] text-night-muted">CT-2026-311068</span>
              <span className="ml-auto text-[0.8rem] text-night-muted">Step {step + 1} of {n}</span>
            </div>
            <div className="relative h-[calc(100%-3rem)]">
              <AnimatePresence mode="wait" initial={false}>
                <m.div
                  key={step}
                  className="absolute inset-0"
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0, transition: { duration: 0.38, ease: EASE } }}
                  exit={{ opacity: 0, y: -8, transition: { duration: 0.16, ease: EASE } }}
                >
                  {STEPS[step].scene(!reduce)}
                </m.div>
              </AnimatePresence>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/** Small screens: no pinning, the same five steps as a simple stacked list. */
export function StoryStacked() {
  const reduce = useReducedMotion();
  return (
    <section aria-label="How a case runs" className="px-5 py-20 sm:px-8 lg:hidden">
      <p className="text-[0.9333rem] font-medium text-night-muted">How a case runs</p>
      <h2 className="mt-3 text-[2rem] leading-[1.08] font-semibold tracking-[-0.03em] text-night-text">From claim to refund in one sitting.</h2>
      <ol className="mt-10 flex flex-col gap-10">
        {STEPS.map((s, i) => (
          <li key={s.title}>
            <p className="flex items-baseline gap-3">
              <span className="tnum text-[0.8rem] text-night-muted">{String(i + 1).padStart(2, "0")}</span>
              <span className="text-[1.1rem] font-semibold text-night-text">{s.title}</span>
            </p>
            <p className="mt-2 leading-relaxed text-night-muted">{s.body}</p>
            <div className="mt-4 h-[340px] overflow-hidden rounded-2xl bg-[#131416] ring-1 ring-white/10">{s.scene(!reduce)}</div>
          </li>
        ))}
      </ol>
    </section>
  );
}
