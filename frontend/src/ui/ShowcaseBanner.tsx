import { Info, X } from "@phosphor-icons/react";
import { useState } from "react";

/** The public site is built with VITE_MOCK=1: no server, no model, everything runs in the browser. */
export const SHOWCASE = import.meta.env.VITE_MOCK === "1";

const KEY = "versoml.showcase.hidden";

function readHidden(): boolean {
  try {
    return sessionStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

/** The console's strip: says plainly that the live agents are off and what still works. */
export function ShowcaseBanner() {
  if (!SHOWCASE) return null;
  return (
    <div role="note" className="border-b border-yellow-line bg-yellow-tint px-5 py-2.5 sm:px-8 lg:px-10">
      <p className="mx-auto flex max-w-[1240px] items-start gap-2.5 text-[0.8667rem] leading-snug">
        <Info size={16} weight="fill" className="mt-0.5 shrink-0 text-yellow-text" />
        <span>
          <strong className="font-semibold">Showcase mode.</strong>{" "}
          <span className="text-ink-soft">
            The server and the live AI agents are offline. This version runs in your browser on demo data: the rules,
            deadlines, sign-off and the sealed evidence file all still work. Winner of the Raiffeisen Bank track at NEXXT
            Summit 2026.
          </span>
        </span>
      </p>
    </div>
  );
}

/** The homepage's pill: small, at the bottom, and it stays closed for the rest of the visit. */
export function ShowcasePill() {
  const [hidden, setHidden] = useState(readHidden);
  if (!SHOWCASE || hidden) return null;
  return (
    <div role="note" className="fixed inset-x-0 bottom-4 z-40 flex justify-center px-4">
      <div className="flex max-w-[640px] items-center gap-2.5 rounded-full bg-night-2/90 py-2 pr-2 pl-4 text-[0.8667rem] text-night-muted shadow-[var(--shadow-nav)] ring-1 ring-glass/10 backdrop-blur-md">
        <Info size={16} weight="fill" className="shrink-0 text-yellow" />
        <span>
          <strong className="font-semibold text-night-text">Showcase mode:</strong> the live agents are offline; the
          console runs in your browser on demo data.
        </span>
        <button
          type="button"
          aria-label="Hide"
          onClick={() => {
            setHidden(true);
            try {
              sessionStorage.setItem(KEY, "1");
            } catch {
              /* private mode: it just comes back on the next page */
            }
          }}
          className="grid size-7 shrink-0 place-items-center rounded-full hover:bg-glass/10 hover:text-night-text"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
}
