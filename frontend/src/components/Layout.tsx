import React from "react";
import { NavLink } from "react-router-dom";
import { Button } from "./Button";
import { AnimatedBackground } from "./AnimatedBackground";

type LayoutProps = {
  children: React.ReactNode;
};

const navItems = [
  { to: "/dashboard", label: "Overview", icon: "📊" },
  { to: "/meetings", label: "Meetings", icon: "📅" },
  { to: "/tasks", label: "Tasks", icon: "✓" },
  { to: "/junk", label: "Inbox Hygiene", icon: "🧹" },
  { to: "/analytics", label: "Analytics", icon: "📈" }
];

export const Layout: React.FC<LayoutProps> = ({ children }) => {
  return (
    <div className="app-root">
      <AnimatedBackground />
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
              <span className="nav-item-icon">{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <Button
            variant="ghost"
            size="md"
            onClick={() => {
              window.location.href = "/logout";
            }}
          >
            Logout
          </Button>
        </div>
      </aside>
      <main className="main">
        <header className="main-header">
          <div className="header-title">
            <h1>Pare Workspace</h1>
            <p>AI-powered email organization for meetings, tasks, and insights.</p>
          </div>
          <div className="header-actions">
            <Button
              variant="primary"
              size="md"
              onClick={() => {
                window.location.href = "/sync";
              }}
            >
              Run Full Sync
            </Button>
          </div>
        </header>
        <section className="main-content">{children}</section>
      </main>
    </div>
  );
};


