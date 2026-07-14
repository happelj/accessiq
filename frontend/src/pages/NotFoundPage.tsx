import { Link } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";

export function NotFoundPage() {
  return (
    <main className="standalone-page">
      <EmptyState title="Page not found" detail="The requested route does not exist." />
      <Link className="primary-button" to="/dashboard">
        Dashboard
      </Link>
    </main>
  );
}
