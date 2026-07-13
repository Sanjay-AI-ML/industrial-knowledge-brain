export default function MobileNav({ pages, currentPage, onNavigate }) {
  return (
    <nav className="md:hidden fixed bottom-0 inset-x-0 z-50 bg-white/90 backdrop-blur-lg border-t border-slate-200 safe-bottom">
      <div className="flex items-stretch justify-around px-1 py-1">
        {Object.entries(pages).map(([key, page]) => {
          const Icon = page.icon;
          const active = currentPage === key;
          return (
            <button
              key={key}
              onClick={() => onNavigate(key)}
              className={`flex flex-col items-center gap-0.5 px-2 py-2 rounded-xl transition-all duration-200 min-w-0 flex-1 ${
                active
                  ? "text-blue-600"
                  : "text-slate-400 active:scale-95"
              }`}
            >
              <div className={`p-1.5 rounded-xl transition-all duration-200 ${active ? "bg-blue-100" : ""}`}>
                <Icon size={18} />
              </div>
              <span className="text-[10px] font-medium truncate max-w-full">
                {page.shortLabel || page.label.split(" ")[0]}
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
