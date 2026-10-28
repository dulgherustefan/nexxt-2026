import { ArrowRight, CheckCircle, DeviceMobile, XCircle } from "@phosphor-icons/react";
import { LazyMotion, m, MotionConfig, useInView, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { dateLong } from "../../api/format";
import { AnimatedGridPattern } from "../../components/fx/AnimatedGridPattern";
import { NumberTicker } from "../../components/fx/NumberTicker";
import { Logo } from "../../ui/Logo";
import { cx } from "../../ui/kit";
import EvidenceSeal from "./EvidenceSeal";
import FlowDiagram from "./FlowDiagram";
import Story, { StoryStacked } from "./Story";

const loadFeatures = () => import("./motionFeatures").then((mod) => mod.default);
const EASE = [0.22, 1, 0.36, 1] as const;

export default function HomePage() {
  useEffect(() => {
    document.title = "VersoML · Disputed payments, refunded on time";
  }, []);
  return (
    <MotionConfig reducedMotion="user" transition={{ duration: 0.3, ease: EASE }}>
      <LazyMotion features={loadFeatures} strict>
        <div className="min-h-dvh bg-night text-night-text selection:bg-yellow selection:text-[#2b2d33]">
          <Nav />
          <main>
            <Hero />
            <Story />
            <StoryStacked />
            <Evidence />
            <Recovery />
            <Results />
            <FinalCta />
          </main>
          <Footer />
        </div>
      </LazyMotion>
    </MotionConfig>
  );
}

// ---------------------------------------------------------------- helpers

function Container({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("mx-auto w-full max-w-[1200px] px-5 sm:px-8", className)}>{children}</div>;
}

function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="text-[0.9333rem] font-medium text-night-muted">{children}</p>;
}

function H2({ children, className }: { children: ReactNode; className?: string }) {
  return <h2 className={cx("mt-3 max-w-[20ch] text-[2.1rem] leading-[1.06] font-semibold tracking-[-0.03em] text-night-text sm:text-[2.6rem]", className)}>{children}</h2>;
}

/** The one yellow button: Raiffeisen yellow, charcoal text, an arrow that nudges on hover. */
function YellowLink({ to, children, size = "lg" }: { to: string; children: ReactNode; size?: "md" | "lg" }) {
  return (
    <Link
      to={to}
      className={cx(
        "press group inline-flex items-center gap-2 rounded-full bg-yellow font-semibold text-[#2b2d33] transition-colors hover:bg-[#ffee3d]",
        size === "lg" ? "h-12 pr-2 pl-6 text-[0.9667rem]" : "h-9 pr-1.5 pl-4 text-[0.9333rem]",
      )}
    >
      {children}
      <span className={cx("grid place-items-center rounded-full bg-[#2b2d33] text-yellow transition-transform duration-200 ease-[var(--ease-out)] group-hover:translate-x-0.5", size === "lg" ? "size-8" : "size-6")}>
        <ArrowRight size={size === "lg" ? 15 : 12} weight="bold" />
      </span>
    </Link>
  );
}

function Reveal({ children, className, delay = 0 }: { children: ReactNode; className?: string; delay?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "0px 0px -12% 0px" });
  const reduce = useReducedMotion();
  return (
    <m.div
      ref={ref}
      className={className}
      initial={reduce ? false : { opacity: 0, y: 18, filter: "blur(4px)" }}
      animate={inView ? { opacity: 1, y: 0, filter: "blur(0px)" } : undefined}
      transition={{ duration: 0.7, ease: EASE, delay }}
    >
      {children}
    </m.div>
  );
}

// ---------------------------------------------------------------- nav (floating pill)

function Nav() {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 24);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  return (
    <header className="fixed inset-x-0 top-4 z-40 px-4">
      <div
        className={cx(
          "mx-auto flex h-14 max-w-[880px] items-center justify-between gap-4 rounded-full pr-2 pl-5 ring-1 transition-[background-color,box-shadow] duration-300",
          scrolled ? "bg-[#141518]/80 shadow-[0_12px_40px_-12px_rgb(0_0_0/0.6)] ring-white/10 backdrop-blur-md" : "bg-transparent ring-transparent",
        )}
      >
        <Link to="/" aria-label="VersoML home" className="rounded-md text-[1.02rem] text-night-text">
          <Logo />
        </Link>
        <nav aria-label="Sections" className="hidden items-center gap-6 text-[0.9rem] text-night-muted md:flex">
          <a href="#how" className="transition-colors hover:text-night-text">How it works</a>
          <a href="#evidence" className="transition-colors hover:text-night-text">Evidence</a>
          <a href="#recovery" className="transition-colors hover:text-night-text">Recovery</a>
          <a href="#results" className="transition-colors hover:text-night-text">Results</a>
        </nav>
        <YellowLink to="/cases" size="md">Open console</YellowLink>
      </div>
    </header>
  );
}

// ---------------------------------------------------------------- hero

function Hero() {
  const reduce = useReducedMotion();
  return (
    <section className="relative overflow-hidden pt-36 pb-16 sm:pt-44 lg:pb-6">
      <div aria-hidden className="absolute inset-0 [mask-image:radial-gradient(60%_55%_at_50%_30%,#000_10%,transparent_90%)]">
        <AnimatedGridPattern className="text-white" numSquares={14} maxOpacity={0.09} duration={3.6} />
      </div>
      <div aria-hidden className="pointer-events-none absolute top-[-18rem] left-1/2 size-[46rem] -translate-x-1/2 rounded-full bg-yellow/[0.14] blur-[120px]" />
      <Container className="relative">
        <div className="mx-auto max-w-[56rem] text-center">
          <h1 className="text-[2.7rem] leading-[1.02] font-semibold tracking-[-0.04em] sm:text-[4.4rem]">
            Disputed payments, refunded by the <span className="text-yellow">next business day</span>.
          </h1>
          <m.p
            initial={reduce ? false : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: EASE, delay: 0.15 }}
            className="mx-auto mt-6 max-w-[40rem] text-[1.1rem] leading-relaxed text-night-muted"
          >
            VersoML gathers the evidence and applies the law. A person signs only the exceptions.
          </m.p>
          <m.div
            initial={reduce ? false : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: EASE, delay: 0.25 }}
            className="mt-9 flex flex-wrap items-center justify-center gap-x-6 gap-y-4"
          >
            <YellowLink to="/cases">Open the console</YellowLink>
            <a href="#how" className="text-[0.9333rem] font-medium text-night-muted transition-colors hover:text-night-text">
              See how a case runs ↓
            </a>
          </m.div>
        </div>
        <m.div
          initial={reduce ? false : { opacity: 0, y: 30, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.9, ease: EASE, delay: 0.35 }}
          className="mx-auto mt-16 max-w-[980px] sm:mt-20"
        >
          <FlowDiagram />
        </m.div>
      </Container>
    </section>
  );
}

// ---------------------------------------------------------------- evidence

function Evidence() {
  return (
    <section id="evidence" className="relative scroll-mt-20 border-t border-white/[0.07] py-24 lg:py-32">
      <Container>
        <div className="grid gap-6 lg:grid-cols-2 lg:items-end">
          <Reveal>
            <Eyebrow>Evidence</Eyebrow>
            <H2>Every fact gets a fingerprint.</H2>
          </Reveal>
          <Reveal delay={0.1}>
            <p className="max-w-[48ch] text-[1.0667rem] leading-relaxed text-night-muted lg:justify-self-end">
              Each item is hashed when it’s collected, and the file is signed when the case closes. Change one word and the signature breaks.
            </p>
          </Reveal>
        </div>
        <Reveal className="mt-12" delay={0.15}>
          <EvidenceSeal />
        </Reveal>
      </Container>
    </section>
  );
}

// ---------------------------------------------------------------- recovery

const RECOVERY = [
  { payment: "Online card payment, no 3-D Secure", outcome: "File a Visa 10.4 chargeback", note: "Fraud, card not present", ok: true },
  { payment: "Card payment approved with Visa Secure", outcome: "Don’t file 10.4", note: "ECI 05 with CAVV moves the liability to the bank", ok: false },
  { payment: "Instant transfer to another bank", outcome: "Send a recall", note: "SEPA camt.056, reason FRAD", ok: true },
  { payment: "Transfer to an account at the same bank", outcome: "Freeze it and ask for the money back", note: "Rule REC-03", ok: true },
];

function Recovery() {
  const ref = useRef<HTMLUListElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.35 });
  const reduce = useReducedMotion();
  return (
    <section id="recovery" className="scroll-mt-20 border-t border-white/[0.07] py-24 lg:py-32">
      <Container className="grid gap-12 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)] lg:gap-20">
        <Reveal>
          <Eyebrow>Recovery</Eyebrow>
          <H2>Chargebacks only where they can win.</H2>
          <p className="mt-5 max-w-[42ch] text-[1.0667rem] leading-relaxed text-night-muted">
            A chargeback that fails still costs fees. VersoML checks the scheme rules first and picks the route that can work.
          </p>
        </Reveal>
        <ul ref={ref} className="divide-y divide-white/[0.07] overflow-hidden rounded-[22px] bg-[#131416] ring-1 ring-white/10">
          {RECOVERY.map((r, i) => (
            <m.li
              key={r.payment}
              className="grid grid-cols-[1.5rem_minmax(0,1fr)] gap-x-4 gap-y-1 px-6 py-5 sm:grid-cols-[1.5rem_minmax(0,1fr)_minmax(0,1fr)]"
              initial={reduce ? false : { opacity: 0, x: 16 }}
              animate={inView ? { opacity: 1, x: 0 } : undefined}
              transition={{ duration: 0.5, ease: EASE, delay: i * 0.09 }}
            >
              <span className={cx("mt-0.5", r.ok ? "text-yellow" : "text-[#ff7a66]")}>
                {r.ok ? <CheckCircle size={20} weight="fill" /> : <XCircle size={20} weight="fill" />}
              </span>
              <p className="text-night-muted">{r.payment}</p>
              <div className="col-start-2 sm:col-start-3">
                <p className="font-medium text-night-text">{r.outcome}</p>
                <p className="text-[0.8667rem] text-night-muted">{r.note}</p>
              </div>
            </m.li>
          ))}
        </ul>
      </Container>
    </section>
  );
}

// ---------------------------------------------------------------- results

interface Proof { at: string; cases: number; refundsOk: number; deadlinesOk: number; injections: [number, number]; pii: number }

const SNAPSHOT: Proof = { at: "2026-10-28", cases: 340, refundsOk: 100, deadlinesOk: 100, injections: [28, 28], pii: 0 };

function useProof(): Proof {
  const [p, setP] = useState(SNAPSHOT);
  useEffect(() => {
    let alive = true;
    fetch("/api/eval")
      .then((r) => (r.ok ? r.json() : null))
      .then((raw) => {
        const g = raw?.rules_golden;
        if (!alive || typeof g?.verdict_accuracy !== "number") return;
        const gen = raw?.rules_generated;
        const inj = raw?.injection;
        setP({
          at: raw.generated_at ?? SNAPSHOT.at,
          cases: (g.cases ?? 0) + (gen?.cases ?? 0),
          refundsOk: Math.round(Math.min(g.verdict_accuracy, gen?.verdict_accuracy ?? 1) * 100),
          deadlinesOk: Math.round((g.deadline_accuracy ?? 1) * 100),
          injections: typeof inj?.detected === "number" ? [inj.detected, inj.injection_cases] : SNAPSHOT.injections,
          pii: raw?.privacy?.raw_pii_to_llm ?? 0,
        });
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);
  return p;
}

function Results() {
  const p = useProof();
  const items = [
    { value: p.refundsOk, suffix: "%", label: "correct refund decisions" },
    { value: p.deadlinesOk, suffix: "%", label: "deadlines right, holidays included" },
    { value: p.injections[0], suffix: ` of ${p.injections[1]}`, label: "prompt injections caught" },
    { value: p.pii, suffix: "", label: "personal data sent to the model" },
  ];
  return (
    <section id="results" className="scroll-mt-20 border-t border-white/[0.07] py-24 lg:py-32">
      <Container>
        <div className="flex flex-wrap items-end justify-between gap-6">
          <Reveal>
            <Eyebrow>Results</Eyebrow>
            <H2>Tested before anyone trusts it.</H2>
          </Reveal>
          <Reveal delay={0.1}>
            <p className="max-w-[38ch] text-night-muted">
              {p.cases} synthetic cases, run on {dateLong(p.at)}.{" "}
              <Link to="/evaluation" className="font-medium text-night-text underline decoration-white/25 underline-offset-4 hover:decoration-yellow">Read the report</Link>
            </p>
          </Reveal>
        </div>
        <dl className="relative mt-14 grid sm:grid-cols-2 lg:grid-cols-4">
          {items.map((it, i) => (
            <div key={it.label} className="relative border-t border-white/[0.09] px-1 pt-7 pb-8 sm:px-6 lg:border-l lg:first:border-l-0">
              <span aria-hidden className="absolute -top-[3px] -left-[3px] hidden size-[5px] rounded-full bg-white/40 lg:block" />
              <dt className="sr-only">{it.label}</dt>
              <dd>
                <p className="text-[2.8rem] leading-none font-semibold tracking-[-0.04em] text-night-text">
                  <NumberTicker value={it.value} delay={i * 0.12} />
                  <span className="text-yellow">{it.suffix}</span>
                </p>
                <p className="mt-4 max-w-[22ch] text-[0.9333rem] text-night-muted">{it.label}</p>
              </dd>
            </div>
          ))}
        </dl>
      </Container>
    </section>
  );
}

// ---------------------------------------------------------------- final call to action + footer

function FinalCta() {
  return (
    <section className="relative overflow-hidden border-t border-white/[0.07] py-28 lg:py-36">
      <div aria-hidden className="pointer-events-none absolute bottom-[-22rem] left-1/2 size-[44rem] -translate-x-1/2 rounded-full bg-yellow/[0.12] blur-[120px]" />
      <Container className="relative text-center">
        <Reveal>
          <h2 className="mx-auto max-w-[18ch] text-[2.4rem] leading-[1.04] font-semibold tracking-[-0.035em] sm:text-[3.4rem]">See a case from claim to refund.</h2>
          <p className="mx-auto mt-5 max-w-[46ch] text-[1.0667rem] text-night-muted">
            Run a sample case, or report a payment from your phone.
          </p>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-x-7 gap-y-4">
            <YellowLink to="/cases">Open the console</YellowLink>
            <Link to="/bank" className="inline-flex items-center gap-2 text-[0.9333rem] font-medium text-night-muted transition-colors hover:text-night-text">
              <DeviceMobile size={18} /> Open Demo Bank
            </Link>
          </div>
        </Reveal>
      </Container>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-white/[0.07]">
      <Container className="flex flex-col gap-6 py-10 text-[0.8667rem] text-night-muted md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-3 text-night-text">
          <Logo className="text-[0.95rem]" />
        </div>
        <p className="max-w-[56ch]">Synthetic data. Demo Bank is not a real bank.</p>
        <nav aria-label="Footer" className="flex gap-5">
          <Link to="/cases" className="hover:text-night-text">Console</Link>
          <Link to="/rules" className="hover:text-night-text">Rules</Link>
          <Link to="/evaluation" className="hover:text-night-text">Evaluation</Link>
          <Link to="/mcp" className="hover:text-night-text">MCP</Link>
        </nav>
      </Container>
    </footer>
  );
}
