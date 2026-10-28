import { Compass } from "@phosphor-icons/react";
import { Link } from "react-router";
import { EmptyState } from "../ui/kit";

export default function NotFound() {
  return (
    <div className="pt-6">
      <EmptyState
        icon={<Compass aria-hidden size={20} />}
        title="Page not found"
        action={
          <Link
            to="/cases"
            className="press inline-flex h-9 items-center rounded-full bg-paper px-4 text-[0.9333rem] font-medium shadow-[var(--shadow-card)] transition-colors hover:bg-hover"
          >
            Go to cases
          </Link>
        }
      >
        The link may be wrong, or the page has moved.
      </EmptyState>
    </div>
  );
}
