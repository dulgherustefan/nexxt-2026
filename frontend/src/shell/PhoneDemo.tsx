import qrcode from "qrcode-generator";
import { TriangleAlert, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { cx } from "../ui/kit";

/** QR desenat local (fără servicii externe), ca imagine SVG: conținutul nu se execută. */
function QrCode({ text, label }: { text: string; label: string }) {
  const src = useMemo(() => {
    const qr = qrcode(0, "M");
    qr.addData(text);
    qr.make();
    return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(qr.createSvgTag({ cellSize: 4, margin: 0, scalable: true }))}`;
  }, [text]);
  return <img src={src} alt={label} className="aspect-square w-full max-w-[13rem] bg-paper [image-rendering:pixelated]" />;
}

function isLocal(origin: string) {
  return /\/\/(localhost|127\.0\.0\.1|\[::1\])(:|$)/.test(origin);
}

/** Codurile QR pe care jurații le scanează de pe proiector: pagina falsă, apoi Banca Demo. */
export function PhoneDemoDialog({ onClose }: { onClose: () => void }) {
  const origin = window.location.origin;
  const [client, setClient] = useState<1 | 2>(1);
  const closeRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const bankUrl = client === 1 ? `${origin}/banca` : `${origin}/banca?client=CUST-DEMO-02`;

  // o singură dată la deschidere: focus pe „Închide”, Escape închide, focusul revine unde era
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onCloseRef.current();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      prev?.focus();
    };
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink/40 p-4 sm:items-center" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-labelledby="phone-demo-title" onClick={(e) => e.stopPropagation()}
        className="w-full max-w-[50rem] rounded-lg bg-paper shadow-overlay">
        <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-3.5">
          <h2 id="phone-demo-title" className="text-[1.15rem] font-bold">Demo pe telefon</h2>
          <button ref={closeRef} type="button" onClick={onClose} aria-label="Închide" className="grid size-8 place-items-center rounded-md hover:bg-hover">
            <X className="size-4" />
          </button>
        </header>

        <div className="flex flex-col gap-5 p-5">
          {isLocal(origin) && (
            <p role="alert" className="flex gap-2.5 rounded-md border border-danger-line bg-danger-soft px-4 py-3 text-[0.9333rem]">
              <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0 text-danger" />
              <span>Consola e deschisă pe {origin}, iar telefoanele nu ajung la această adresă. Deschide consola pe IP-ul laptopului din rețea (adresa „Network” din terminal).</span>
            </p>
          )}

          <ol className="grid gap-5 md:grid-cols-2">
            <li className="flex flex-col items-center gap-3 rounded-lg border border-line p-5 text-center">
              <p className="flex items-center gap-2 font-semibold"><Step n={1} /> Pagina falsă</p>
              <p className="text-[0.9333rem] text-ink-soft">Linkul din SMS-ul de la „curier”. Completează datele, ca o victimă.</p>
              <QrCode text={`${origin}/demo/livrare`} label="Cod QR spre pagina falsă de demo" />
              <p className="break-all font-mono text-[0.8rem] text-muted">{origin}/demo/livrare</p>
            </li>
            <li className="flex flex-col items-center gap-3 rounded-lg border border-line p-5 text-center">
              <p className="flex items-center gap-2 font-semibold"><Step n={2} /> Banca Demo</p>
              <p className="text-[0.9333rem] text-ink-soft">Apare plata de 3.200 lei. Apasă „Nu am făcut eu plata”.</p>
              <QrCode text={bankUrl} label={`Cod QR spre Banca Demo, clientul ${client}`} />
              <p className="break-all font-mono text-[0.8rem] text-muted">{bankUrl}</p>
              <div role="radiogroup" aria-label="Clientul din Banca Demo" className="inline-flex rounded-md border border-line p-0.5 text-[0.8667rem]">
                {([1, 2] as const).map((n) => (
                  <button key={n} type="button" role="radio" aria-checked={client === n} onClick={() => setClient(n)}
                    className={cx("rounded-[5px] px-3 py-1 font-medium", client === n ? "bg-ink text-paper" : "text-muted hover:text-ink")}>
                    {n === 1 ? "Primul jurat" : "Al doilea jurat"}
                  </button>
                ))}
              </div>
            </li>
          </ol>

          <p className="text-center text-[0.9333rem] text-muted">Contestația apare în lista de pe ecran în câteva secunde; semnezi rambursarea aici, iar telefonul arată banii returnați.</p>
        </div>
      </div>
    </div>
  );
}

function Step({ n }: { n: number }) {
  return <span aria-hidden className="grid size-6 place-items-center rounded-full bg-ink text-[0.8rem] font-bold text-paper">{n}</span>;
}
