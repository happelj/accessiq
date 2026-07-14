import { Link } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";

export function UnauthorizedPage() {
  return (
    <main className="standalone-page">
      <EmptyState
        title="Unauthorized"
        detail="The current account does not have access to this area."
      />
      <Link className="primary-button" to="/dashboard">
        Dashboard
      </Link>
    </main>
  );
}
