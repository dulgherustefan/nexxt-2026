// Adapted from Magic UI "Border Beam" (MIT, magicui.design).
import { m, useReducedMotion, type MotionStyle } from "motion/react";
import type { CSSProperties } from "react";
import { cx } from "../../ui/kit";

/** A short light that travels around the border of its (relatively positioned, rounded) parent. */
export function BorderBeam({
  className,
  size = 120,
  duration = 8,
  delay = 0,
  colorFrom = "#fee600",
  colorTo = "#fff6b0",
  reverse = false,
  borderWidth = 1,
}: {
  className?: string;
  size?: number;
  duration?: number;
  delay?: number;
  colorFrom?: string;
  colorTo?: string;
  reverse?: boolean;
  borderWidth?: number;
}) {
  const reduce = useReducedMotion();
  if (reduce) return null;
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-0 rounded-[inherit] border-(length:--beam-w) border-transparent mask-[linear-gradient(transparent,transparent),linear-gradient(#000,#000)] mask-intersect [mask-clip:padding-box,border-box]"
      style={{ "--beam-w": `${borderWidth}px` } as CSSProperties}
    >
      <m.div
        className={cx("absolute aspect-square bg-linear-to-l from-(--c-from) via-(--c-to) to-transparent", className)}
        style={{ width: size, offsetPath: `rect(0 auto auto 0 round ${size}px)`, "--c-from": colorFrom, "--c-to": colorTo } as MotionStyle}
        initial={{ offsetDistance: "0%" }}
        animate={{ offsetDistance: reverse ? ["100%", "0%"] : ["0%", "100%"] }}
        transition={{ repeat: Infinity, ease: "linear", duration, delay: -delay }}
      />
    </div>
  );
}
