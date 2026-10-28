import { CircleAlert, PackageX, TriangleAlert, Truck } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useApi } from "../../api/runtime";
import { Button } from "../../ui/kit";
import { amount2, clientFrom } from "./bankModel";

/**
 * Pagina falsă de demo („Curier Demo", brand fictiv). Câmpurile cardului au valori de test fixe și
 * nu sunt câmpuri de formular: nimic din ele nu se trimite și nu se păstrează. Butonul cere doar
 * serverului să simuleze plata escrocului din contul clientului de demo.
 */

const TEST_CARD: Array<{ label: string; value: string; wide?: boolean }> = [
  { label: "Numărul cardului", value: "4242 4242 4242 4242", wide: true },
  { label: "Expiră la", value: "12/29" },
  { label: "CVV", value: "123" },
  { label: "Numele de pe card", value: "Client Demo", wide: true },
];

export default function FakePage() {
  const api = useApi();
  const [search] = useSearchParams();
  const ref = clientFrom(search);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [paid, setPaid] = useState<{ amount: number } | null>(null);

  useEffect(() => {
    document.title = "DEMO · Curier Demo (pagină falsă)";
  }, []);

  const bankQuery = new URLSearchParams();
  if (search.get("client")) bankQuery.set("client", ref);
  if (search.get("mock")) bankQuery.set("mock", search.get("mock") as string);
  const bankHref = `/banca${bankQuery.toString() ? `?${bankQuery.toString()}` : ""}`;

  async function pay() {
    setBusy(true);
    setError(null);
    try {
      // doar referința clientului de demo: datele de card nu pleacă nicăieri
      const out = await api.demoScam({ customer_ref: ref });
      setPaid({ amount: typeof out?.amount === "number" ? out.amount : 0 });
      window.scrollTo({ top: 0 });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-dvh bg-paper">
      <div role="note" className="sticky top-0 z-50 flex items-center justify-center gap-2 bg-danger px-4 py-2.5 text-center text-[0.9333rem] font-bold text-paper">
        <TriangleAlert aria-hidden className="size-4 shrink-0" />
        <span>DEMO — pagină falsă de test. Nu introduce date reale.</span>
      </div>

      <header className="bg-ink text-paper">
        <div className="mx-auto flex max-w-md items-center gap-2.5 px-4 py-3">
          <span aria-hidden className="grid size-8 place-items-center rounded-md bg-paper text-ink">
            <Truck className="size-4" />
          </span>
          <span className="font-bold">Curier Demo</span>
          <span className="ml-auto text-[0.8667rem] text-paper/75">Urmărire colet</span>
        </div>
      </header>

      <main className="mx-auto max-w-md px-4 pt-5 pb-8">
        {paid ? (
          <Result amount={paid.amount} bankHref={bankHref} />
        ) : (
          <>
            <div className="flex items-start gap-3">
              <PackageX aria-hidden className="mt-1 size-7 shrink-0" />
              <div>
                <h1 className="text-[1.45rem] leading-tight font-bold">Coletul tău nu a putut fi livrat.</h1>
                <p className="mt-1.5 text-ink-soft">Plătește taxa de 2,99 lei ca să programăm o nouă livrare.</p>
              </div>
            </div>

            <dl className="mt-5 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 rounded-lg border border-line bg-canvas px-4 py-3 text-[0.9333rem]">
              <dt className="text-muted">AWB</dt>
              <dd className="font-mono text-[0.8667rem]">CD 4821 0033 917</dd>
              <dt className="text-muted">Stare</dt>
              <dd>Livrare eșuată: adresă incompletă</dd>
              <dt className="text-muted">Taxă de reprogramare</dt>
              <dd className="font-semibold">2,99 lei</dd>
            </dl>

            <section aria-labelledby="card-title" className="mt-6">
              <h2 id="card-title" className="font-semibold">Datele cardului</h2>
              <div className="mt-2 grid grid-cols-2 gap-3">
                {TEST_CARD.map((f) => (
                  <div key={f.label} className={f.wide ? "col-span-2" : undefined}>
                    <p className="text-[0.8667rem] font-medium text-muted">{f.label}</p>
                    <div
                      role="textbox"
                      aria-readonly="true"
                      aria-label={f.label}
                      className="mt-1 flex h-11 items-center rounded-md border border-line-strong bg-canvas px-3 font-medium tabular-nums text-ink-soft select-none"
                    >
                      {f.value}
                    </div>
                  </div>
                ))}
              </div>
              <p className="mt-2 text-[0.8667rem] text-muted">
                Valori de test, completate automat. Nu se pot modifica și nu se trimit nicăieri.
              </p>
            </section>

            {error && (
              <p role="alert" className="mt-4 flex items-start gap-2 rounded-md border border-danger-line bg-danger-soft px-3 py-2 text-[0.9333rem] text-danger">
                <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
                <span>Plata demo nu a pornit. Motiv: {error} Încearcă din nou.</span>
              </p>
            )}

            <Button variant="primary" className="mt-5 h-12 w-full text-[1rem]" busy={busy} onClick={pay}>
              {busy ? "Se procesează…" : "Plătește 2,99 lei"}
            </Button>
          </>
        )}
      </main>

      <footer className="mx-auto max-w-md border-t border-line px-4 py-4 text-[0.8667rem] text-muted">
        Curier Demo e un brand fictiv, creat pentru demonstrația VersoML. Pagina nu colectează și nu păstrează date de card.
      </footer>
    </div>
  );
}

function Result({ amount, bankHref }: { amount: number; bankHref: string }) {
  const sum = amount > 0 ? `${amount2(amount)} lei` : null;
  return (
    <div role="status">
      <span className="grid size-12 place-items-center rounded-full bg-danger-soft text-danger">
        <CircleAlert aria-hidden className="size-6" />
      </span>
      <h1 className="mt-4 text-[1.6rem] leading-tight font-bold">Ai fost păcălit (demo).</h1>
      <p className="mt-2 text-[1.2rem]">
        {sum ? (
          <>
            <span className="font-bold tabular-nums">{sum}</span> au plecat din contul tău.
          </>
        ) : (
          "Banii au plecat din contul tău."
        )}
      </p>
      <ul className="mt-5 flex flex-col gap-2.5 text-[0.9333rem]">
        <li className="flex gap-2.5">
          <span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-full bg-ink" />
          <span>Pagina a cerut 2,99 lei pentru o „taxă de livrare”.</span>
        </li>
        <li className="flex gap-2.5">
          <span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-full bg-ink" />
          <span>Cu datele introduse aici, escrocul a trimis {sum ?? "bani"} din contul tău către un cont controlat de el.</span>
        </li>
        <li className="flex gap-2.5">
          <span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-full bg-ink" />
          <span>Pentru o plată pe care nu ai autorizat-o, banca trebuie să îți returneze banii până la sfârșitul zilei lucrătoare următoare.</span>
        </li>
      </ul>
      <Link
        to={bankHref}
        className="mt-6 inline-flex h-12 w-full items-center justify-center rounded-md border border-ink bg-yellow px-4 text-[1rem] font-semibold text-ink hover:bg-yellow-hover"
      >
        Deschide Banca Demo
      </Link>
      <p className="mt-3 text-center text-[0.8667rem] text-muted">Acolo apasă „Nu am făcut eu plata” pe transferul de {sum ?? "azi"}.</p>
    </div>
  );
}
