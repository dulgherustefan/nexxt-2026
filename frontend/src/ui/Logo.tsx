import { cx } from "./kit";

/**
 * The VersoML mark: a V cut down the middle, each arm folded once like paper. The ink arm is the case as
 * reported; the yellow arm is the verso, the side the bank has to prove, and its fold shows the darker back.
 * The ink arm follows `currentColor`, so the same mark works on paper and on the dark homepage.
 */
function Arms({ onYellow }: { onYellow?: boolean }) {
  return (
    <>
      <path d="M2.4 5.5h5.4L16 28z" fill="currentColor" />
      <path d="M7.8 5.5h1.8L16 16.2V28z" fill="currentColor" fillOpacity={0.72} />
      {/* on a yellow ground the verso arm turns white, so it doesn't vanish into the background */}
      <path d="M29.6 5.5h-5.4L16 28z" fill={onYellow ? "#FFFFFF" : "#FEE600"} />
      <path d="M24.2 5.5h-1.8L16 16.2V28z" fill={onYellow ? "#FFFFFF" : "#D6B900"} fillOpacity={onYellow ? 0.6 : 1} />
    </>
  );
}

export function LogoMark({ className, title, onYellow }: { className?: string; title?: string; onYellow?: boolean }) {
  return (
    <svg viewBox="0 0 32 32" className={cx("shrink-0", className)} role={title ? "img" : undefined} aria-hidden={title ? undefined : true}>
      {title && <title>{title}</title>}
      <Arms onYellow={onYellow} />
    </svg>
  );
}

export function Logo({ className, markClassName, onYellow }: { className?: string; markClassName?: string; onYellow?: boolean }) {
  return (
    <span className={cx("inline-flex items-center gap-2", className)}>
      <LogoMark className={cx("size-[1.3em]", markClassName)} onYellow={onYellow} />
      <span className="font-semibold tracking-[-0.02em]">VersoML</span>
    </span>
  );
}
