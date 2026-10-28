// Adapted from Magic UI "Animated Beam" (MIT, magicui.design), as listed on 21st.dev.
import { m, useReducedMotion } from "motion/react";
import { useEffect, useId, useState, type RefObject } from "react";
import { cx } from "../../ui/kit";

export interface AnimatedBeamProps {
  className?: string;
  containerRef: RefObject<HTMLElement | null>;
  fromRef: RefObject<HTMLElement | null>;
  toRef: RefObject<HTMLElement | null>;
  curvature?: number;
  reverse?: boolean;
  pathColor?: string;
  pathWidth?: number;
  pathOpacity?: number;
  gradientStartColor?: string;
  gradientStopColor?: string;
  delay?: number;
  duration?: number;
  startXOffset?: number;
  startYOffset?: number;
  endXOffset?: number;
  endYOffset?: number;
}

/** A light pulse travelling along a curved path between two elements. */
export function AnimatedBeam({
  className,
  containerRef,
  fromRef,
  toRef,
  curvature = 0,
  reverse = false,
  duration = 5,
  delay = 0,
  pathColor = "white",
  pathWidth = 1.5,
  pathOpacity = 0.1,
  gradientStartColor = "#fee600",
  gradientStopColor = "#fff6b0",
  startXOffset = 0,
  startYOffset = 0,
  endXOffset = 0,
  endYOffset = 0,
}: AnimatedBeamProps) {
  const id = useId();
  const reduce = useReducedMotion();
  const [d, setD] = useState("");
  const [size, setSize] = useState({ width: 0, height: 0 });

  const coords = reverse
    ? { x1: ["90%", "-10%"], x2: ["100%", "0%"], y1: ["0%", "0%"], y2: ["0%", "0%"] }
    : { x1: ["10%", "110%"], x2: ["0%", "100%"], y1: ["0%", "0%"], y2: ["0%", "0%"] };

  useEffect(() => {
    const update = () => {
      const c = containerRef.current;
      const a = fromRef.current;
      const b = toRef.current;
      if (!c || !a || !b) return;
      const cr = c.getBoundingClientRect();
      const ar = a.getBoundingClientRect();
      const br = b.getBoundingClientRect();
      setSize({ width: cr.width, height: cr.height });
      const sx = ar.left - cr.left + ar.width / 2 + startXOffset;
      const sy = ar.top - cr.top + ar.height / 2 + startYOffset;
      const ex = br.left - cr.left + br.width / 2 + endXOffset;
      const ey = br.top - cr.top + br.height / 2 + endYOffset;
      setD(`M ${sx},${sy} Q ${(sx + ex) / 2},${sy - curvature} ${ex},${ey}`);
    };
    // nodes can move without the container resizing (late fonts, wrapping labels), so watch all three
    const ro = new ResizeObserver(update);
    for (const el of [containerRef.current, fromRef.current, toRef.current]) if (el) ro.observe(el);
    update();
    let alive = true;
    void document.fonts?.ready.then(() => alive && update());
    return () => {
      alive = false;
      ro.disconnect();
    };
  }, [containerRef, fromRef, toRef, curvature, startXOffset, startYOffset, endXOffset, endYOffset]);

  return (
    <svg
      fill="none"
      width={size.width}
      height={size.height}
      viewBox={`0 0 ${size.width} ${size.height}`}
      aria-hidden
      className={cx("pointer-events-none absolute top-0 left-0 transform-gpu", className)}
    >
      <path d={d} stroke={pathColor} strokeWidth={pathWidth} strokeOpacity={pathOpacity} strokeLinecap="round" />
      {!reduce && (
        <>
          <path d={d} strokeWidth={pathWidth} stroke={`url(#${id})`} strokeOpacity="1" strokeLinecap="round" />
          <defs>
            <m.linearGradient
              id={id}
              gradientUnits="userSpaceOnUse"
              initial={{ x1: "0%", x2: "0%", y1: "0%", y2: "0%" }}
              animate={coords}
              transition={{ delay, duration, ease: [0.16, 1, 0.3, 1], repeat: Infinity, repeatDelay: 0.6 }}
            >
              <stop stopColor={gradientStartColor} stopOpacity="0" />
              <stop stopColor={gradientStartColor} />
              <stop offset="32.5%" stopColor={gradientStopColor} />
              <stop offset="100%" stopColor={gradientStopColor} stopOpacity="0" />
            </m.linearGradient>
          </defs>
        </>
      )}
    </svg>
  );
}
