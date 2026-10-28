// Adapted from Magic UI "Number Ticker" (MIT, magicui.design).
import { useInView, useMotionValue, useReducedMotion, useSpring } from "motion/react";
import { useEffect, useRef } from "react";
import { cx } from "../../ui/kit";

/** Counts up to `value` once, when it scrolls into view. Writes to the DOM directly, no re-renders per frame. */
export function NumberTicker({ value, delay = 0, decimals = 0, suffix = "", className }: {
  value: number; delay?: number; decimals?: number; suffix?: string; className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const reduce = useReducedMotion();
  const mv = useMotionValue(reduce ? value : 0);
  const spring = useSpring(mv, { damping: 60, stiffness: 110 });
  const inView = useInView(ref, { once: true, margin: "0px 0px -15% 0px" });
  const fmt = (n: number) =>
    new Intl.NumberFormat("en-GB", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(Number(n.toFixed(decimals))) + suffix;

  useEffect(() => {
    if (!inView) return;
    const t = window.setTimeout(() => mv.set(value), delay * 1000);
    return () => window.clearTimeout(t);
  }, [inView, delay, value, mv]);

  useEffect(() => spring.on("change", (v) => { if (ref.current) ref.current.textContent = fmt(v); }), [spring]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <span ref={ref} className={cx("inline-block", className)} aria-label={fmt(value)}>
      {fmt(reduce ? value : 0)}
    </span>
  );
}
