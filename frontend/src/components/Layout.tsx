import React from "react";
import { NavLink } from "react-router-dom";

type LayoutProps = {
  children: React.ReactNode;
};

const navItems = [
  { to: "/dashboard", label: "Overview" },
  { to: "/meetings", label: "Meetings" },
  { to: "/tasks", label: "Tasks" },
  { to: "/junk", label: "Inbox Hygiene" },
  { to: "/analytics", label: "Analytics" }
];

export const Layout: React.FC<LayoutProps> = ({ children }) => {
  return (
    <div className="app-root">
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="logo-pill">P</div>
          <div className="brand">
            <span className="brand-name">Pare</span>
            <span className="brand-sub">Email Suite</span>
          </div>
        </div>
        <nav className="sidebar-nav">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                "nav-item" + (isActive ? " nav-item-active" : "")
              }
            >
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <button
            className="ghost-button"
            onClick={() => {
              window.location.href = "/logout";
            }}
          >
            Logout
          </button>
        </div>
      </aside>
      <main className="main">
        <header className="main-header">
          <div className="header-title">
            <h1>Pare Workspace</h1>
            <p>AI-powered email organization for meetings, tasks, and insights.</p>
          </div>
          <div className="header-actions">
            <button
              className="primary-button"
              onClick={() => {
                // Reuse legacy manual sync endpoint as a power feature
                window.location.href = "/sync";
              }}
            >
              Run Full Sync
            </button>
          </div>
        </header>
        <section className="main-content">{children}</section>
      </main>
    </div>
  );
};


