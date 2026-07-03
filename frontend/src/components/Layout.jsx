import { useState } from "react";
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
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const desktopLink = ({ isActive }) =>
    `flex items-center gap-2 px-4 py-2 rounded-lg transition-colors text-sm ${
      isActive
        ? "bg-indigo-600 text-white"
        : "text-gray-400 hover:text-white hover:bg-gray-800"
    }`;

  const mobileLink = ({ isActive }) =>
    `flex flex-col items-center gap-0.5 px-2 py-1.5 rounded-lg transition-colors text-[10px] font-medium ${
      isActive ? "text-indigo-400" : "text-gray-500 hover:text-gray-300"
    }`;

  return (
    <div className="min-h-screen flex bg-gray-950">

      {/* ── Mobile overlay when drawer is open ────────────────────────────── */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/60 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* ── Sidebar (desktop: always visible · mobile: slide-in drawer) ───── */}
      <aside
        className={[
          "fixed inset-y-0 left-0 z-30 flex flex-col w-64",
          "bg-gray-900 border-r border-gray-800 p-6",
          "transition-transform duration-300 ease-in-out",
          // On desktop always show; on mobile slide in/out
          "lg:static lg:translate-x-0 lg:z-auto",
          sidebarOpen ? "translate-x-0" : "-translate-x-full",
        ].join(" ")}
      >
        {/* Logo row + close button (mobile only) */}
        <div className="mb-8 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <img
              src="/Amazon_Alexa_blue_logo.svg"
              alt="Amazon Alexa"
              className="h-8 w-8 shrink-0"
            />
            <div>
              <h1 className="text-lg font-bold text-white leading-tight">
                Awaas AI
              </h1>
              <p className="text-[13px] text-gray-500">Powered by Amazon Alexa</p>
            </div>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden text-gray-500 hover:text-white p-1 rounded-md"
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
            >
              <Icon className="w-4 h-4 shrink-0" />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="mt-auto pt-4 border-t border-gray-800 space-y-3">
          <LanguageSelect />
          {user && (
            <p className="text-xs text-gray-400 truncate" title={user.email}>
              {user.email}
            </p>
          )}
          <button
            onClick={logout}
            className="flex items-center gap-2 w-full px-4 py-2 rounded-lg
                       text-gray-400 hover:text-red-400 hover:bg-gray-800
                       transition-colors text-sm"
          >
            <LogOut className="w-4 h-4" />
            Sign Out
          </button>
          <p className="text-xs text-gray-600">
            Powered by Nvidia Nemotron on AWS Bedrock
          </p>
        </div>
      </aside>

      {/* ── Right column: top bar (mobile) + page content ─────────────────── */}
      <div className="flex flex-col flex-1 min-w-0">

        {/* Mobile top bar */}
        <header className="lg:hidden flex items-center gap-3 px-4 py-3 bg-gray-900 border-b border-gray-800 shrink-0">
          <button
            onClick={() => setSidebarOpen(true)}
            className="text-gray-400 hover:text-white p-1 rounded-md"
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
            <span className="text-sm font-bold text-white">Awaas AI</span>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 pb-20 lg:pb-8">
          <Outlet />
        </main>

        {/* Mobile bottom tab bar */}
        <nav className="lg:hidden fixed bottom-0 inset-x-0 z-10 flex items-center justify-around
                        bg-gray-900 border-t border-gray-800 px-2 py-1 safe-area-bottom">
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
