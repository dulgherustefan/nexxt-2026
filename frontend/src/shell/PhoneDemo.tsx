import qrcode from "qrcode-generator";
import { ExternalLink, TriangleAlert } from "lucide-react";
import { useMemo, useState } from "react";
import { Dialog, Segmented } from "../ui/kit";

/** QR desenat local (fără servicii externe), ca imagine SVG: conținutul nu se execută. */
function QrCode({ text, label }: { text: string; label: string }) {
  const src = useMemo(() => {
    const qr = qrcode(0, "M");
    qr.addData(text);
    qr.make();
    return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(qr.createSvgTag({ cellSize: 4, margin: 0, scalable: true }))}`;
  }, [text]);
  return <img src={src} alt={label} className="aspect-square w-full max-w-[12rem] bg-paper [image-rendering:pixelated]" />;
}

function isLocal(origin: string) {
  return /\/\/(localhost|127\.0\.0\.1|\[::1\])(:|$)/.test(origin);
}

/** Cele două coduri pentru jurați: pagina falsă, apoi Banca Demo. */
export function PhoneQr() {
  const origin = window.location.origin;
  const [client, setClient] = useState<"1" | "2">("1");
  const bankUrl = client === "1" ? `${origin}/banca` : `${origin}/banca?client=CUST-DEMO-02`;
  const fakeUrl = `${origin}/demo/livrare`;
  return (
    <div className="flex flex-col gap-5">
      {isLocal(origin) && (
        <p role="alert" className="flex gap-2.5 rounded-md border border-danger-line bg-danger-soft px-4 py-3 text-[0.9333rem]">
          <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0 text-danger" />
          <span>Consola rulează pe {origin}. Telefoanele nu ajung aici: deschide consola pe IP-ul laptopului din rețea.</span>
        </p>
      )}
      <ol className="grid gap-4 md:grid-cols-2">
        <li className="flex flex-col items-center gap-3 rounded-lg border border-line p-5 text-center">
          <p className="font-semibold">1. Pagina falsă</p>
          <p className="text-[0.9333rem] text-muted">Linkul din SMS-ul „de la curier”.</p>
          <QrCode text={fakeUrl} label="Cod QR spre pagina falsă de demo" />
          <a href="/demo/livrare" target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 break-all font-mono text-[0.8rem] text-muted hover:text-ink">
            {fakeUrl} <ExternalLink aria-hidden className="size-3 shrink-0" />
          </a>
        </li>
        <li className="flex flex-col items-center gap-3 rounded-lg border border-line p-5 text-center">
          <p className="font-semibold">2. Banca Demo</p>
          <p className="text-[0.9333rem] text-muted">Juratul apasă „Nu am făcut eu plata”.</p>
          <QrCode text={bankUrl} label={`Cod QR spre Banca Demo, clientul ${client}`} />
          <a href={client === "1" ? "/banca" : "/banca?client=CUST-DEMO-02"} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 break-all font-mono text-[0.8rem] text-muted hover:text-ink">
            {bankUrl} <ExternalLink aria-hidden className="size-3 shrink-0" />
          </a>
          <Segmented label="Clientul din Banca Demo" value={client} onChange={setClient}
            options={[{ id: "1", label: "Primul jurat" }, { id: "2", label: "Al doilea jurat" }]} />
        </li>
      </ol>
    </div>
  );
}

export function PhoneDemoDialog({ onClose }: { onClose: () => void }) {
  return (
    <Dialog title="Coduri QR pentru jurați" onClose={onClose} width={800}>
      <PhoneQr />
    </Dialog>
  );
}
