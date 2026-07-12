import { useEffect, useState } from "react";
import { Outlet, NavLink } from "react-router-dom";
import {
  Brain,
  Ear,
  History,
  Lightbulb,
  LogOut,
  Network,
  ShieldAlert,
  Menu,
  X,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import LanguageSelect from "./LanguageSelect";

const NAV_ITEMS = [
  { to: "/",        label: "Mood",         Icon: Brain       },
  { to: "/patterns",label: "Patterns",     Icon: Network     },
  { to: "/ambient", label: "Ambient",      Icon: Ear         },
  { to: "/safety",  label: "Safety",       Icon: ShieldAlert },
  { to: "/history", label: "Mood History", Icon: History     },
  { to: "/devices", label: "Devices",      Icon: Lightbulb   },
];

export default function Layout() {
  const { user, logout } = useAuth();
  // Mobile: slide-in drawer. Desktop: collapse to an icon-only rail.
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem("sidebar-collapsed") === "true",
  );

  useEffect(() => {
    localStorage.setItem("sidebar-collapsed", String(collapsed));
  }, [collapsed]);

  // `hideOnCollapse` hides an element ONLY on desktop when collapsed — the
  // mobile drawer always shows full labels, so it stays visible below lg.
  const hideOnCollapse = collapsed ? "lg:hidden" : "";

  const desktopLink = ({ isActive }) =>
    [
      "flex items-center gap-2 px-4 py-2 rounded-lg transition-colors text-sm",
      collapsed ? "lg:justify-center lg:px-2" : "",
      isActive
        ? "bg-[var(--pp-accent)] text-[#131a22] font-semibold shadow-sm"
        : "text-[var(--pp-muted)] hover:text-[var(--pp-text)] hover:bg-[var(--pp-surface-2)]",
    ].join(" ");

  const mobileLink = ({ isActive }) =>
    `flex flex-col items-center gap-0.5 px-2 py-1.5 rounded-lg transition-colors text-[10px] font-medium ${
      isActive ? "text-[var(--pp-accent-text)]" : "text-[var(--pp-subtle)] hover:text-[var(--pp-text-2)]"
    }`;

  return (
    <div className="min-h-screen flex bg-[#131a22]">

      {/* ── Mobile overlay when drawer is open ────────────────────────────── */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/60 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* ── Sidebar (desktop: collapsible rail · mobile: slide-in drawer) ────
          `data-ptheme="dark"` scopes the Amazon (Squid Ink + Orange) palette
          variables to the chrome without remapping the page content. */}
      <aside
        data-ptheme="dark"
        className={[
          "fixed inset-y-0 left-0 z-30 flex flex-col w-64",
          "bg-[var(--pp-surface)] border-r border-[var(--pp-border)] p-6",
          "transition-all duration-300 ease-in-out",
          // On desktop always show; on mobile slide in/out
          "lg:static lg:translate-x-0 lg:z-auto",
          collapsed ? "lg:w-20 lg:px-3" : "lg:w-64",
          sidebarOpen ? "translate-x-0" : "-translate-x-full",
        ].join(" ")}
      >
        {/* Logo row + collapse toggle (desktop) / close button (mobile) */}
        <div
          className={[
            "mb-8 flex gap-3",
            collapsed
              ? "items-center lg:flex-col lg:gap-4"
              : "items-center justify-between",
          ].join(" ")}
        >
          {/* Desktop collapse / expand toggle (burger) */}
          <button
            onClick={() => setCollapsed((c) => !c)}
            className="hidden lg:flex items-center justify-center shrink-0 p-1.5 rounded-md text-[var(--pp-muted)] hover:text-[var(--pp-text)] hover:bg-[var(--pp-surface-2)] transition-colors"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={collapsed ? "Expand menu" : "Collapse menu"}
          >
            <Menu className="w-5 h-5" />
          </button>

          {/* Logo — icon always shown; the text collapses away on desktop */}
          <div className="flex items-center gap-3 min-w-0">
            <img
              src="/Amazon_Alexa_blue_logo.svg"
              alt="Amazon Alexa"
              className="h-8 w-8 shrink-0"
            />
            <div className={`min-w-0 ${hideOnCollapse}`}>
              <h1 className="text-lg font-bold text-[var(--pp-text)] leading-tight">
                Awaas AI
              </h1>
              <p className="text-[13px] text-[var(--pp-subtle)]">Powered by Amazon Alexa</p>
            </div>
          </div>

          {/* Mobile drawer close */}
          <button
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden ml-auto text-[var(--pp-subtle)] hover:text-[var(--pp-text)] p-1 rounded-md"
            aria-label="Close menu"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Nav links */}
        <nav className="flex flex-col gap-1">
          {NAV_ITEMS.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={desktopLink}
              onClick={() => setSidebarOpen(false)}
              title={collapsed ? label : undefined}
            >
              <Icon className="w-4 h-4 shrink-0" />
              <span className={hideOnCollapse}>{label}</span>
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="mt-auto pt-4 border-t border-[var(--pp-border)] space-y-3">
          <div className={hideOnCollapse}>
            <LanguageSelect />
          </div>
          {user && (
            <p
              className={`text-xs text-[var(--pp-muted)] truncate ${hideOnCollapse}`}
              title={user.email}
            >
              {user.email}
            </p>
          )}
          <button
            onClick={logout}
            title={collapsed ? "Sign Out" : undefined}
            className={[
              "flex items-center gap-2 w-full px-4 py-2 rounded-lg",
              "text-[var(--pp-muted)] hover:text-[var(--pp-danger)] hover:bg-[var(--pp-surface-2)]",
              "transition-colors text-sm",
              collapsed ? "lg:justify-center lg:px-2" : "",
            ].join(" ")}
          >
            <LogOut className="w-4 h-4 shrink-0" />
            <span className={hideOnCollapse}>Sign Out</span>
          </button>
          <p className={`text-xs text-[var(--pp-subtle)] ${hideOnCollapse}`}>
            Powered by Nvidia Nemotron on AWS Bedrock
          </p>
        </div>
      </aside>

      {/* ── Right column: top bar (mobile) + page content ─────────────────── */}
      <div className="flex flex-col flex-1 min-w-0">

        {/* Mobile top bar */}
        <header data-ptheme="dark" className="lg:hidden flex items-center gap-3 px-4 py-3 bg-[var(--pp-surface)] border-b border-[var(--pp-border)] shrink-0">
          <button
            onClick={() => setSidebarOpen(true)}
            className="text-[var(--pp-muted)] hover:text-[var(--pp-text)] p-1 rounded-md"
            aria-label="Open menu"
          >
            <Menu className="w-5 h-5" />
          </button>
          <div className="flex items-center gap-2">
            <img
              src="/Amazon_Alexa_blue_logo.svg"
              alt="Amazon Alexa"
              className="h-6 w-6 shrink-0"
            />
            <span className="text-sm font-bold text-[var(--pp-text)]">Awaas AI</span>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 pb-20 lg:pb-8">
          <Outlet />
        </main>

        {/* Mobile bottom tab bar */}
        <nav data-ptheme="dark" className="lg:hidden fixed bottom-0 inset-x-0 z-10 flex items-center justify-around
                        bg-[var(--pp-surface)] border-t border-[var(--pp-border)] px-2 py-1 safe-area-bottom">
          {NAV_ITEMS.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={mobileLink}
            >
              <Icon className="w-5 h-5" />
              <span className="truncate max-w-13 text-center">{label}</span>
            </NavLink>
          ))}
        </nav>
      </div>

    </div>
  );
}
