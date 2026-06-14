import { Outlet, NavLink } from "react-router-dom";
import { Brain, History, Lightbulb, Network, ShieldAlert } from "lucide-react";

export default function Layout() {
  const linkClass = ({ isActive }) =>
    `flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
      isActive
        ? "bg-indigo-600 text-white"
        : "text-gray-400 hover:text-white hover:bg-gray-800"
    }`;

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside className="w-64 bg-gray-900 border-r border-gray-800 p-6 flex flex-col">
        <div className="mb-8 flex items-center gap-3">
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

        <nav className="flex flex-col gap-2">
          <NavLink to="/" className={linkClass}>
            <Brain className="w-4 h-4" />
            Mood
          </NavLink>
          <NavLink to="/patterns" className={linkClass}>
            <Network className="w-4 h-4" />
            Patterns
          </NavLink>
          <NavLink to="/safety" className={linkClass}>
            <ShieldAlert className="w-4 h-4" />
            Safety
          </NavLink>
          <NavLink to="/history" className={linkClass}>
            <History className="w-4 h-4" />
            Mood History
          </NavLink>
          <NavLink to="/devices" className={linkClass}>
            <Lightbulb className="w-4 h-4" />
            Devices
          </NavLink>
        </nav>

        <div className="mt-auto pt-4 border-t border-gray-800">
          <p className="text-xs text-gray-600">Powered by Nvidia Nemotron on AWS Bedrock</p>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 p-8 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
