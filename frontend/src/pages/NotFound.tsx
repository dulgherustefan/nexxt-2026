import { Link } from "react-router";
import { EmptyState } from "../ui/kit";

export default function NotFound() {
  return (
    <EmptyState
      title="Pagina nu există."
      action={<Link className="font-semibold underline" to="/">Înapoi la început</Link>}
    >
      Linkul e greșit sau pagina a fost mutată.
    </EmptyState>
  );
}
