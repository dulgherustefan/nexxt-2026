import qrcode from "qrcode-generator";
import { useMemo } from "react";
import { cx } from "./kit";

/**
 * A QR code drawn locally (no external service), as an SVG image: nothing in it can run.
 * Always black on white, whatever the theme: phone cameras read dark modules on a light ground.
 */
export function QrCode({ text, label, className }: { text: string; label: string; className?: string }) {
  const src = useMemo(() => {
    const qr = qrcode(0, "M");
    qr.addData(text);
    qr.make();
    return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(qr.createSvgTag({ cellSize: 4, margin: 0, scalable: true }))}`;
  }, [text]);
  return <img src={src} alt={label} className={cx("aspect-square bg-white p-2 [image-rendering:pixelated]", className)} />;
}

/** True when the page is open on this machine only, so a phone can't follow a link to it. */
export function isLocalOrigin(origin: string): boolean {
  return /\/\/(localhost|127\.0\.0\.1|\[::1\])(:|$)/.test(origin);
}

/** The public site, used for links a phone has to open while the console runs on localhost. */
export const PUBLIC_SITE = (import.meta.env.VITE_PUBLIC_SITE as string | undefined) || "https://versoml.vercel.app";

/** Where the seal's QR code leads: the public check page, with the signed root to compare against. */
export function verifyUrl(caseId: string, root: string): string {
  const origin = isLocalOrigin(window.location.origin) ? PUBLIC_SITE : window.location.origin;
  return `${origin}/verify/${encodeURIComponent(caseId)}#${root}`;
}
