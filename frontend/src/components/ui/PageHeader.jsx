/** Reusable gradient page header with optional badge and staggered entrance. */
export default function PageHeader({ badge, title, subtitle, gradient = "from-slate-900 via-blue-900 to-indigo-900", children }) {
  return (
    <header
      className={`bg-gradient-to-r ${gradient} text-white rounded-2xl p-6 sm:p-8 shadow-lg animate-slide-up relative overflow-hidden`}
    >
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_rgba(255,255,255,0.08),_transparent_60%)] pointer-events-none" />
      <div className="relative">
        {badge && (
          <p className="text-xs uppercase tracking-widest text-blue-300 font-semibold mb-2 animate-fade-in">
            {badge}
          </p>
        )}
        <h1 className="text-xl sm:text-2xl font-bold">{title}</h1>
        {subtitle && <p className="text-sm text-blue-100/90 mt-2 max-w-2xl leading-relaxed">{subtitle}</p>}
        {children}
      </div>
    </header>
  );
}
