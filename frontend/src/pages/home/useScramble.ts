import { useEffect, useState } from "react";

const HEX = "0123456789abcdef";

/**
 * A hash that "settles": random hex for a moment, then resolves left to right into the real value.
 * Short strings only (≤ 16 chars) and ≤ 30 fps, so it never competes with real work on the page.
 */
export function useScramble(target: string, active: boolean, { delay = 0, spin = 260, perChar = 22 } = {}): string {
  const [text, setText] = useState(() => (active ? "·".repeat(target.length) : target));
  useEffect(() => {
    if (!active) {
      setText(target);
      return;
    }
    let raf = 0;
    let last = 0;
    const start = performance.now() + delay;
    const settleAt = start + spin;
    const tick = (now: number) => {
      if (now - last < 33) {
        raf = requestAnimationFrame(tick);
        return;
      }
      last = now;
      if (now < start) {
        setText("·".repeat(target.length));
      } else {
        const fixed = now < settleAt ? 0 : Math.min(target.length, Math.floor((now - settleAt) / perChar));
        let out = target.slice(0, fixed);
        for (let i = fixed; i < target.length; i++) out += target[i] === "…" ? "…" : HEX[Math.floor(Math.random() * 16)];
        setText(out);
        if (fixed >= target.length) return;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, active, delay, spin, perChar]);
  return text;
}
