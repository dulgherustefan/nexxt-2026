import { useEffect, useId, useState } from "react";
import { flushSync } from "react-dom";
import { cx } from "./kit";

export type Theme = "light" | "dark";

const KEY = "versoml-theme";
const EVENT = "versoml-theme";

function readTheme(): Theme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

function savedTheme(): Theme | null {
  try {
    const t = localStorage.getItem(KEY);
    return t === "light" || t === "dark" ? t : null;
  } catch {
    return null;
  }
}

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  root.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "dark" ? "#0d0e10" : "#ffffff");
  window.dispatchEvent(new Event(EVENT));
}

/** The current theme, kept in sync across every toggle on the page and with the system setting until someone picks one. */
export function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setThemeState] = useState<Theme>(readTheme);
  useEffect(() => {
    const sync = () => setThemeState(readTheme());
    const media = matchMedia("(prefers-color-scheme: dark)");
    const onSystem = () => { if (!savedTheme()) applyTheme(media.matches ? "dark" : "light"); };
    window.addEventListener(EVENT, sync);
    media.addEventListener("change", onSystem);
    return () => {
      window.removeEventListener(EVENT, sync);
      media.removeEventListener("change", onSystem);
    };
  }, []);
  const setTheme = (t: Theme) => {
    try { localStorage.setItem(KEY, t); } catch { /* private mode: the choice lasts for this page only */ }
    flushSync(() => setThemeState(t));
    applyTheme(t);
  };
  return [theme, setTheme];
}

/** Sun and moon in one shape: the moon's bite slides in, the rays fold away. */
function SunMoon({ dark }: { dark: boolean }) {
  const mask = useId();
  const swing = "transition-transform duration-500 ease-[var(--ease-out)] [transform-box:fill-box] [transform-origin:center]";
  return (
    <svg viewBox="0 0 24 24" className="size-[18px]" aria-hidden>
      <mask id={mask}>
        <rect width="24" height="24" fill="white" />
        <circle cx="18" cy="6" r="6.5" fill="black" className={cx(swing, dark ? "translate-x-0 translate-y-0" : "translate-x-[9px] -translate-y-[9px]")} />
      </mask>
      <circle cx="12" cy="12" r="8" fill="currentColor" mask={`url(#${mask})`} className={cx(swing, dark ? "scale-100" : "scale-[0.55]")} />
      <g
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        className={cx("transition-[transform,opacity] duration-500 ease-[var(--ease-out)] [transform-origin:12px_12px]", dark ? "scale-50 -rotate-90 opacity-0" : "opacity-100")}
      >
        <path d="M12 1.5v2M12 20.5v2M1.5 12h2M20.5 12h2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M4.6 19.4L6 18M18 6l1.4-1.4" />
      </g>
    </svg>
  );
}

/** Switches light and dark. The new theme grows out of the button as a circle where the browser supports it. */
export function ThemeToggle({ className }: { className?: string }) {
  const [theme, setTheme] = useTheme();
  const dark = theme === "dark";
  const next: Theme = dark ? "light" : "dark";

  const onClick = (e: React.MouseEvent<HTMLButtonElement>) => {
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!document.startViewTransition || reduce) {
      setTheme(next);
      return;
    }
    const r = e.currentTarget.getBoundingClientRect();
    const x = r.left + r.width / 2;
    const y = r.top + r.height / 2;
    const radius = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
    const root = document.documentElement.style;
    root.setProperty("--theme-x", `${x}px`);
    root.setProperty("--theme-y", `${y}px`);
    root.setProperty("--theme-r", `${radius}px`);
    document.startViewTransition(() => setTheme(next));
  };

  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      title={dark ? "Light theme" : "Dark theme"}
      className={cx("press grid size-9 shrink-0 place-items-center rounded-full transition-colors", className)}
    >
      <SunMoon dark={dark} />
    </button>
  );
}
