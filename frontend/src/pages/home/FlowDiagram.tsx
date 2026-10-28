import { ChatCircleText, CreditCard, DeviceMobile, EnvelopeSimple, Globe, Receipt, ShieldCheck, Wallet, type Icon } from "@phosphor-icons/react";
import { forwardRef, useRef } from "react";
import { AnimatedBeam } from "../../components/fx/AnimatedBeam";
import { BorderBeam } from "../../components/fx/BorderBeam";
import { LogoMark } from "../../ui/Logo";
import { cx } from "../../ui/kit";

const IN: Array<{ icon: Icon; label: string; sub: string }> = [
  { icon: ChatCircleText, label: "Customer claim", sub: "“I didn’t make this payment”" },
  { icon: CreditCard, label: "Transaction", sub: "core banking" },
  { icon: ShieldCheck, label: "3-D Secure", sub: "what the screen showed" },
  { icon: DeviceMobile, label: "Device", sub: "new or known" },
  { icon: Globe, label: "Website", sub: "age of the fake domain" },
];

const OUT: Array<{ icon: Icon; label: string; sub: string; tone: "yellow" | "plain" }> = [
  { icon: Wallet, label: "Refund sent", sub: "by the next business day", tone: "yellow" },
  { icon: Receipt, label: "Chargeback drafted", sub: "only where it can win", tone: "plain" },
  { icon: EnvelopeSimple, label: "Letter to the customer", sub: "plain English", tone: "plain" },
];

/** The icon sits on the side facing the hub, so beams start at the icon and never cross the label. */
const Node = forwardRef<HTMLDivElement, { icon: Icon; label: string; sub: string; tone?: "yellow" | "plain"; side: "in" | "out" }>(
  function Node({ icon: I, label, sub, tone = "plain", side }, ref) {
    return (
      <div className={cx("flex items-center gap-3", side === "in" && "flex-row-reverse text-right")}>
        <div
          ref={ref}
          className={cx(
            "relative z-10 grid size-11 shrink-0 place-items-center rounded-xl ring-1",
            tone === "yellow" ? "bg-yellow text-[#2b2d33] ring-yellow" : "bg-[#18191c] text-night-text ring-white/10",
          )}
        >
          <I size={20} />
        </div>
        <div className="hidden min-w-0 leading-tight sm:block">
          <p className="text-[0.9333rem] font-medium text-night-text">{label}</p>
          <p className="mt-0.5 truncate text-[0.8rem] text-night-muted">{sub}</p>
        </div>
      </div>
    );
  },
);

/** Inputs flow into VersoML; decisions flow out. The beams carry the yellow light left to right. */
export default function FlowDiagram() {
  const box = useRef<HTMLDivElement>(null);
  const hub = useRef<HTMLDivElement>(null);
  const ins = [useRef<HTMLDivElement>(null), useRef<HTMLDivElement>(null), useRef<HTMLDivElement>(null), useRef<HTMLDivElement>(null), useRef<HTMLDivElement>(null)];
  const outs = [useRef<HTMLDivElement>(null), useRef<HTMLDivElement>(null), useRef<HTMLDivElement>(null)];
  return (
    <div className="relative overflow-hidden rounded-[28px] bg-[#111214] p-6 ring-1 ring-white/10 sm:p-10">
      <BorderBeam size={180} duration={10} />
      <div ref={box} className="relative grid grid-cols-[1fr_auto_1fr] items-center gap-6 sm:gap-10">
        <div className="flex flex-col items-end gap-5 sm:gap-6">
          {IN.map((n, i) => <Node key={n.label} ref={ins[i]} {...n} side="in" />)}
        </div>
        <div ref={hub} className="relative z-10 grid size-24 place-items-center rounded-[26px] bg-[#18191c] ring-1 ring-yellow/40 shadow-[0_0_60px_-10px_rgb(254_230_0/0.35)] sm:size-28">
          <LogoMark className="size-11 text-white sm:size-12" />
          <span className="absolute -bottom-7 text-[0.8rem] font-medium whitespace-nowrap text-night-muted">VersoML</span>
        </div>
        <div className="flex flex-col items-start gap-7 sm:gap-9">
          {OUT.map((n, i) => <Node key={n.label} ref={outs[i]} {...n} side="out" />)}
        </div>
        {ins.map((r, i) => (
          <AnimatedBeam key={`in${i}`} containerRef={box} fromRef={r} toRef={hub} curvature={(2 - i) * 22} duration={4.6} delay={i * 0.35} />
        ))}
        {outs.map((r, i) => (
          <AnimatedBeam key={`out${i}`} containerRef={box} fromRef={hub} toRef={r} curvature={(1 - i) * -22} duration={4.6} delay={2 + i * 0.35} />
        ))}
      </div>
    </div>
  );
}
