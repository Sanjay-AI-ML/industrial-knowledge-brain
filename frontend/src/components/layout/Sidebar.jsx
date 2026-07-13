import { ChevronLeft, ChevronRight } from "lucide-react";

export default function Sidebar({ pages, currentPage, onNavigate, collapsed, onToggleCollapse }) {
  return (
    <aside
      className={`hidden md:flex flex-col bg-white border-r border-slate-200 shrink-0 transition-all duration-300 ease-out ${
        collapsed ? "w-[68px]" : "w-60"
      }`}
    >
      {/* Brand */}
      <div className={`flex items-center gap-2.5 px-4 py-4 border-b border-slate-100 ${collapsed ? "justify-center" : ""}`}>
        <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-700 flex items-center justify-center text-white text-sm font-bold shadow-md shrink-0">
          IKB
        </div>
        {!collapsed && (
          <div className="min-w-0 animate-fade-in">
            <p className="text-sm font-bold text-slate-800 truncate">Knowledge Brain</p>
            <p className="text-[10px] text-slate-400 uppercase tracking-wider">Industrial AI</p>
          </div>
        )}
      </div>

      {/* Nav links */}
      <nav className="flex-1 py-3 px-2 space-y-1 overflow-y-auto">
        {Object.entries(pages).map(([key, page]) => {
          const Icon = page.icon;
          const active = currentPage === key;
          return (
            <button
              key={key}
              onClick={() => onNavigate(key)}
              title={page.label}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 group relative ${
                active
                  ? "bg-blue-600 text-white shadow-md shadow-blue-600/25"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              } ${collapsed ? "justify-center" : ""}`}
            >
              <Icon size={18} className={`shrink-0 transition-transform duration-200 ${active ? "" : "group-hover:scale-110"}`} />
              {!collapsed && <span className="truncate">{page.label}</span>}
              {active && (
                <span className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-white/40 rounded-r-full" />
              )}
            </button>
          );
        })}
      </nav>

      {/* Collapse toggle */}
      <div className="p-2 border-t border-slate-100">
        <button
          onClick={onToggleCollapse}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-all"
        >
          {collapsed ? <ChevronRight size={16} /> : (
            <>
              <ChevronLeft size={16} />
              <span>Collapse</span>
            </>
          )}
        </button>
      </div>
    </aside>
  );
}
