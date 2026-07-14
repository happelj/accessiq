import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

const navigation = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/users", label: "Users" },
  { to: "/applications", label: "Applications" },
  { to: "/groups", label: "Groups" },
  { to: "/access", label: "Access" },
  { to: "/scim", label: "SCIM" },
  { to: "/connectors", label: "Connectors" },
  { to: "/provisioning-jobs", label: "Provisioning Jobs" },
  { to: "/access-reviews", label: "Access Reviews" },
  { to: "/remediation", label: "Remediation" },
  { to: "/authorization-graph", label: "Authorization Graph" },
  { to: "/ai-assistant", label: "AI Assistant" },
  { to: "/settings", label: "Settings" },
];

export function AppLayout() {
  const { currentUser, logout } = useAuth();

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <strong>AccessIQ</strong>
          <span>Admin</span>
        </div>
        <nav className="sidebar-nav" aria-label="Primary navigation">
          {navigation.map((item) => (
            <NavLink key={item.to} to={item.to}>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            <strong>{currentUser?.name ?? "AccessIQ"}</strong>
            <span>{currentUser?.operator_role ?? "Signed in"}</span>
          </div>
          <button type="button" className="secondary-button" onClick={logout}>
            Logout
          </button>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
