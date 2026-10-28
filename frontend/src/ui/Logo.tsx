import { cx } from "./kit";

/**
 * The VersoML mark: a V cut down the middle. The ink half is the front of the case, the yellow
 * half is the verso, the other side the bank has to prove.
 */
export function LogoMark({ className, title }: { className?: string; title?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cx("shrink-0", className)} role={title ? "img" : undefined} aria-hidden={title ? undefined : true}>
      {title && <title>{title}</title>}
      <path d="M29.6 5.5h-7.2L16 16.2V28z" fill="#FEE600" />
      <path d="M2.4 5.5h7.2L16 16.2V28z" fill="currentColor" />
    </svg>
  );
}

export function Logo({ className, markClassName }: { className?: string; markClassName?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-2", className)}>
      <LogoMark className={cx("size-[1.3em]", markClassName)} />
      <span className="font-semibold tracking-[-0.02em]">VersoML</span>
    </span>
  );
}
