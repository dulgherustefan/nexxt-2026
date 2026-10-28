// Adapted from Magic UI "Animated Grid Pattern" (MIT, magicui.design).
import { m, useInView, useReducedMotion } from "motion/react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { cx } from "../../ui/kit";

type Square = { id: number; pos: [number, number]; iteration: number };

/** A thin grid where a few cells softly light up and move on. Pauses when off screen. */
export function AnimatedGridPattern({
  cell = 56,
  numSquares = 24,
  maxOpacity = 0.35,
  duration = 3.2,
  className,
}: {
  cell?: number;
  numSquares?: number;
  maxOpacity?: number;
  duration?: number;
  className?: string;
}) {
  const id = useId();
  const ref = useRef<SVGSVGElement | null>(null);
  const inView = useInView(ref);
  const reduce = useReducedMotion();
  const [dims, setDims] = useState({ width: 0, height: 0 });
  const [squares, setSquares] = useState<Square[]>([]);

  const pos = useCallback(
    (): [number, number] => [Math.floor((Math.random() * dims.width) / cell), Math.floor((Math.random() * dims.height) / cell)],
    [dims.width, dims.height, cell],
  );

  useEffect(() => {
    if (dims.width && dims.height) setSquares(Array.from({ length: numSquares }, (_, i) => ({ id: i, pos: pos(), iteration: 0 })));
  }, [dims.width, dims.height, numSquares, pos]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setDims((d) => (d.width === width && d.height === height ? d : { width, height }));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const move = useCallback(
    (sid: number) =>
      setSquares((cur) => {
        const s = cur[sid];
        if (!s) return cur;
        const next = cur.slice();
        next[sid] = { ...s, pos: pos(), iteration: s.iteration + 1 };
        return next;
      }),
    [pos],
  );

  return (
    <svg ref={ref} aria-hidden className={cx("pointer-events-none absolute inset-0 h-full w-full", className)}>
      <defs>
        <pattern id={id} width={cell} height={cell} patternUnits="userSpaceOnUse" x={-1} y={-1}>
          <path d={`M.5 ${cell}V.5H${cell}`} fill="none" stroke="currentColor" strokeOpacity="0.09" />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill={`url(#${id})`} />
      {!reduce && inView && (
        <svg x={-1} y={-1} className="overflow-visible">
          {squares.map(({ pos: [x, y], id: sid, iteration }, i) => (
            <m.rect
              key={`${sid}-${iteration}`}
              initial={{ opacity: 0 }}
              animate={{ opacity: maxOpacity }}
              transition={{ duration, repeat: 1, delay: i * 0.12, repeatType: "reverse", repeatDelay: 0.4 }}
              onAnimationComplete={() => move(sid)}
              width={cell - 1}
              height={cell - 1}
              x={x * cell + 1}
              y={y * cell + 1}
              className="fill-yellow"
            />
          ))}
        </svg>
      )}
    </svg>
  );
}
