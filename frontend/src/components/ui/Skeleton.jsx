/** Shimmer skeleton block for loading placeholders. */
export function Skeleton({ className = "h-4" }) {
  return <div className={`rounded-lg bg-slate-200 animate-shimmer ${className}`} />;
}

export function SkeletonCard({ lines = 3 }) {
  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 space-y-3 animate-pulse">
      <Skeleton className="h-5 w-1/3" />
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={`h-4 ${i === lines - 1 ? "w-2/3" : "w-full"}`} />
      ))}
    </div>
  );
}
