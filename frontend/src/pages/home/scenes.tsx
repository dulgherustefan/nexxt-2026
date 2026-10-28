import NumberFlow from "@number-flow/react";
import {
  CheckCircle,
  CreditCard,
  DeviceMobile,
  EnvelopeSimple,
  Globe,
  Receipt,
  Scales,
  ShieldCheck,
  Storefront,
  type Icon,
} from "@phosphor-icons/react";
import { m, type Variants } from "motion/react";
import { useEffect, useState } from "react";
import { cx } from "../../ui/kit";
import { useScramble } from "./useScramble";

/**
 * The five scenes of one case, drawn as a dark product card. They play when they become
 * the active step of the scroll story (and render final when motion is reduced).
 */

const EASE = [0.22, 1, 0.36, 1] as const;
const list: Variants = { hidden: {}, show: { transition: { staggerChildren: 0.11, delayChildren: 0.05 } } };
const item: Variants = { hidden: { opacity: 0, y: 8 }, show: { opacity: 1, y: 0, transition: { duration: 0.45, ease: EASE } } };

function Live({ tone = "yellow" }: { tone?: "yellow" | "green" }) {
  return <span className={cx("live-dot inline-block size-2 rounded-full", tone === "yellow" ? "bg-yellow" : "bg-[#5bd08a]")} />;
}

function Chip({ children, tone = "muted" }: { children: React.ReactNode; tone?: "muted" | "yellow" | "green" }) {
  return (
    <span className={cx(
      "inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-[0.75rem] font-medium whitespace-nowrap",
      tone === "yellow" ? "bg-yellow/12 text-yellow" : tone === "green" ? "bg-[#5bd08a]/12 text-[#7ee2a8]" : "bg-white/6 text-night-muted",
    )}>
      {children}
    </span>
  );
}

export function ClaimScene() {
  return (
    <m.div variants={list} initial="hidden" animate="show" className="flex h-full flex-col gap-4 p-6">
      <m.div variants={item} className="flex items-center gap-3">
        <span className="grid size-9 place-items-center rounded-full bg-white/8 text-[0.75rem] font-semibold text-night-text">DC</span>
        <div className="leading-tight">
          <p className="text-[0.9333rem] font-medium text-night-text">Demo Customer 01</p>
          <p className="text-[0.8rem] text-night-muted">Demo Bank app · 19:38</p>
        </div>
        <span className="ml-auto"><Chip tone="yellow"><Live /> New claim</Chip></span>
      </m.div>
      <m.p variants={item} className="max-w-[38ch] rounded-2xl rounded-tl-md bg-white/6 px-4 py-3 text-[0.9333rem] leading-relaxed text-night-text/90">
        “I didn’t make this payment. I paid a 2.99 delivery fee on a courier site, and an hour later RON 3,200.00 went to a shop I’ve never heard of.”
      </m.p>
      <m.div variants={item} className="mt-auto flex items-center gap-3 rounded-xl bg-white/[0.03] px-4 py-3 ring-1 ring-night-line">
        <span className="grid size-9 place-items-center rounded-lg bg-white/6 text-night-muted"><Storefront size={18} /></span>
        <div className="min-w-0 leading-tight">
          <p className="truncate text-[0.9333rem] font-medium text-night-text">Nova Electro Online</p>
          <p className="text-[0.8rem] text-night-muted">Card •• 4821 · online · 18:31</p>
        </div>
        <p className="tnum ml-auto text-[0.9333rem] font-medium whitespace-nowrap text-night-text">−RON 3,200.00</p>
      </m.div>
    </m.div>
  );
}

const EVIDENCE: Array<{ icon: Icon; label: string; finding: string; hash: string }> = [
  { icon: CreditCard, label: "Transaction", finding: "Online card payment to a shop the customer never used", hash: "9f2c41ab…e07d" },
  { icon: ShieldCheck, label: "3-D Secure", finding: "Not used on this payment (ECI 07)", hash: "4b1d07e9…a3c2" },
  { icon: DeviceMobile, label: "Device", finding: "Card details typed on a device the customer never used", hash: "c07ae512…19fb" },
  { icon: Globe, label: "Website", finding: "Fake courier site, registered 6 hours before the payment", hash: "e81f3c6d…5a90" },
];

export function EvidenceScene({ animate }: { animate: boolean }) {
  return (
    <m.ul
      variants={{ hidden: {}, show: { transition: { staggerChildren: 0.32, delayChildren: 0.05 } } }}
      initial="hidden"
      animate="show"
      className="flex h-full flex-col justify-center divide-y divide-night-line px-6"
    >
      {EVIDENCE.map((e, i) => <EvidenceRow key={e.label} {...e} delay={animate ? 80 + i * 320 : 0} animate={animate} />)}
    </m.ul>
  );
}

function EvidenceRow({ icon: I, label, finding, hash, delay, animate }: (typeof EVIDENCE)[number] & { delay: number; animate: boolean }) {
  const text = useScramble(hash, animate, { delay: delay + 140 });
  const settled = text === hash;
  return (
    <m.li variants={item} className="flex items-center gap-3 py-3.5">
      <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-white/6 text-night-text"><I size={18} /></span>
      <div className="min-w-0 flex-1 leading-tight">
        <p className="text-[0.9333rem] font-medium text-night-text">{label}</p>
        <p className="mt-0.5 truncate text-[0.8rem] text-night-muted">{finding}</p>
      </div>
      <span aria-hidden className="hidden w-[7.5rem] text-right font-mono text-[0.72rem] text-night-muted sm:block">{text}</span>
      <CheckCircle size={18} weight={settled ? "fill" : "regular"} className={cx("shrink-0 transition-colors duration-300", settled ? "text-yellow" : "text-white/20")} />
    </m.li>
  );
}

export function DecisionScene() {
  return (
    <m.div variants={list} initial="hidden" animate="show" className="flex h-full flex-col p-6">
      <m.p variants={item} className="flex items-center gap-2 text-[0.8rem] font-medium text-night-muted"><Scales size={16} /> Rules engine</m.p>
      <m.div variants={item} className="mt-5">
        <p className="text-[2.1rem] leading-none font-semibold tracking-[-0.03em] text-night-text">Refund owed</p>
        <p className="mt-2 text-night-muted">by the end of the next business day</p>
      </m.div>
      <m.div variants={item} className="mt-4 flex flex-wrap items-center gap-1.5">
        <Chip>PAY-03</Chip>
        <Chip>PAY-15</Chip>
        <span className="ml-1 text-[0.8rem] text-night-muted">Law 209/2019, art. 173 · CJEU C-70/25</span>
      </m.div>
      <m.div variants={item} className="mt-auto">
        <div className="relative h-8">
          <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-white/12" />
          <m.div
            className="absolute top-1/2 left-0 h-px w-full origin-left -translate-y-1/2 bg-yellow"
            initial={{ scaleX: 0 }}
            animate={{ scaleX: 0.06, transition: { delay: 0.5, duration: 0.6, ease: EASE } }}
          />
          <span className="absolute top-1/2 left-0 size-2.5 -translate-y-1/2 rounded-full bg-night-text" />
          <m.div className="absolute inset-0" initial={{ x: "0%", opacity: 0 }} animate={{ x: "6%", opacity: 1, transition: { delay: 0.5, duration: 0.6, ease: EASE } }}>
            <span className="absolute top-1/2 left-0 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-yellow ring-4 ring-yellow/20" />
          </m.div>
          <span className="absolute top-1/2 right-0 size-2.5 -translate-y-1/2 rounded-full ring-1 ring-white/40" />
        </div>
        <div className="flex justify-between text-[0.8rem]">
          <span><span className="text-night-muted">Reported</span> <span className="tnum text-night-text">Wed 19:38</span></span>
          <span className="text-right"><span className="text-night-muted">Deadline</span> <span className="tnum text-night-text">Thu 23:59</span></span>
        </div>
        <p className="mt-3 text-[0.8rem] text-night-muted"><span className="font-medium text-yellow">Decided at 19:38:57</span>, 28 hours before the deadline.</p>
      </m.div>
    </m.div>
  );
}

export function RefundScene({ animate }: { animate: boolean }) {
  const [balance, setBalance] = useState(animate ? 9250 : 12450);
  useEffect(() => {
    if (!animate) return;
    const t = window.setTimeout(() => setBalance(12450), 420);
    return () => window.clearTimeout(t);
  }, [animate]);
  return (
    <m.div variants={list} initial="hidden" animate="show" className="flex h-full flex-col gap-4 p-6">
      <m.div variants={item} className="rounded-xl bg-white/[0.04] px-5 py-5 ring-1 ring-night-line">
        <p className="text-[0.8rem] text-night-muted">Customer balance</p>
        <p className="mt-1.5 text-[2.1rem] leading-none font-semibold tracking-[-0.03em] text-night-text">
          <NumberFlow value={balance} locales="en-GB" prefix="RON " format={{ minimumFractionDigits: 2, maximumFractionDigits: 2 }} />
        </p>
        <p className="mt-2.5 text-[0.8rem] font-medium text-[#7ee2a8]">+RON 3,200.00 refunded · Wed 19:39</p>
      </m.div>
      <m.div variants={item} className="flex items-center gap-3 rounded-xl px-4 py-3 ring-1 ring-night-line">
        <span className="grid size-8 place-items-center rounded-full bg-yellow text-[#2b2d33]"><CheckCircle size={16} weight="bold" /></span>
        <div className="min-w-0 flex-1 leading-tight">
          <p className="text-[0.9333rem] font-medium text-night-text">Sent automatically · 19:39</p>
          <p className="mt-0.5 text-[0.8rem] text-night-muted">Under the RON 5,000.00 limit, with no risk signals.</p>
        </div>
      </m.div>
    </m.div>
  );
}

export function RecoveryScene() {
  const rows = [
    { icon: Receipt, title: "Visa chargeback 10.4", sub: "Fraud, card not present. Valid: no 3-D Secure.", chip: <Chip tone="yellow"><Live /> Needs approval</Chip> },
    { icon: Globe, title: "Phishing report", sub: "nova-courier.example sent to the national CERT", chip: <Chip>Draft</Chip> },
    { icon: EnvelopeSimple, title: "Letter to the customer", sub: "What happened, what we did, what comes next", chip: <Chip tone="green">Ready</Chip> },
  ];
  return (
    <m.ul variants={list} initial="hidden" animate="show" className="flex h-full flex-col justify-center gap-2.5 p-6">
      {rows.map((r) => (
        <m.li key={r.title} variants={item} className="flex items-center gap-3 rounded-xl bg-white/[0.03] px-4 py-3.5 ring-1 ring-night-line">
          <r.icon size={18} className="shrink-0 text-night-text" />
          <div className="min-w-0 flex-1 leading-tight">
            <p className="text-[0.9333rem] font-medium text-night-text">{r.title}</p>
            <p className="mt-0.5 truncate text-[0.8rem] text-night-muted">{r.sub}</p>
          </div>
          {r.chip}
        </m.li>
      ))}
    </m.ul>
  );
}
