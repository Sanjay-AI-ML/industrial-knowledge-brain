export default function ShortcutsPanel({ pages, onClose }) {
  const keys = Object.keys(pages);

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 bg-black/30 backdrop-blur-sm animate-fade-in" onClick={onClose}>
      <div
        className="bg-white border border-slate-200 rounded-2xl shadow-2xl p-6 max-w-sm w-full mx-4 animate-scale-in"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-sm font-bold text-slate-800 mb-4">Keyboard Shortcuts</h3>
        <ul className="space-y-2.5 text-sm">
          {keys.map((key, i) => (
            <li key={key} className="flex items-center justify-between text-slate-600">
              <span>{pages[key].label}</span>
              <kbd className="kbd">{i + 1}</kbd>
            </li>
          ))}
          <li className="flex items-center justify-between text-slate-600 pt-2 border-t border-slate-100">
            <span>Toggle dark mode</span>
            <kbd className="kbd">D</kbd>
          </li>
          <li className="flex items-center justify-between text-slate-600">
            <span>Send message (Copilot)</span>
            <kbd className="kbd">Enter</kbd>
          </li>
        </ul>
        <button
          onClick={onClose}
          className="mt-5 w-full text-xs text-slate-400 hover:text-slate-600 py-2 transition-colors"
        >
          Click anywhere to close
        </button>
      </div>
    </div>
  );
}
