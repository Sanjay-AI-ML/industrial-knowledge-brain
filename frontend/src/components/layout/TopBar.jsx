import { Sun, Moon, Circle, Keyboard } from "lucide-react";

export default function TopBar({ isDark, toggleTheme, health, showShortcuts, onToggleShortcuts }) {
  const backendUp = health.status === "ok";

  return (
    <header className="sticky top-0 z-40 bg-white/80 backdrop-blur-lg border-b border-slate-200 px-4 py-2.5 flex items-center justify-between gap-3">
      <div className="md:hidden flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-600 to-indigo-700 flex items-center justify-center text-white text-xs font-bold">
          IKB
        </div>
        <span className="text-sm font-semibold text-slate-800">Knowledge Brain</span>
      </div>

      <div className="hidden md:block text-xs text-slate-400">
        Press <kbd className="kbd">1</kbd>–<kbd className="kbd">5</kbd> to switch · <kbd className="kbd">D</kbd> for theme
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <span
          title={backendUp ? "Backend reachable" : "Backend unreachable"}
          className="flex items-center gap-1.5 text-xs text-slate-400 px-2 py-1 rounded-lg bg-slate-50"
        >
          <Circle
            size={8}
            className={`transition-colors duration-500 ${
              health.status === "checking"
                ? "fill-amber-400 text-amber-400 animate-pulse"
                : backendUp
                ? "fill-emerald-500 text-emerald-500"
                : "fill-red-500 text-red-500"
            }`}
          />
          <span className="hidden sm:inline">
            {health.status === "checking" ? "Checking…" : backendUp ? "Online" : "Offline"}
          </span>
        </span>

        <button
          onClick={onToggleShortcuts}
          title="Keyboard shortcuts"
          className={`p-2 rounded-lg transition-all hidden sm:block ${
            showShortcuts ? "bg-blue-100 text-blue-600" : "text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          }`}
        >
          <Keyboard size={16} />
        </button>

        <button
          onClick={toggleTheme}
          title="Toggle dark mode (D)"
          className="p-2 rounded-lg text-slate-500 hover:bg-slate-100 transition-all active:scale-95"
        >
          {isDark ? <Sun size={16} /> : <Moon size={16} />}
        </button>
      </div>
    </header>
  );
}
