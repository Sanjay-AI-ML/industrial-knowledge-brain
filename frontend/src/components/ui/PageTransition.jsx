/** Wraps page content with a keyed enter animation on route change. */
export default function PageTransition({ pageKey, children }) {
  return (
    <div key={pageKey} className="animate-page-enter flex-1 flex flex-col min-h-0">
      {children}
    </div>
  );
}
