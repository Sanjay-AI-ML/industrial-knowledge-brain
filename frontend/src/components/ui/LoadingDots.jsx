/** Animated three-dot typing indicator for async states. */
export default function LoadingDots({ label = "Thinking" }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-slate-400 text-sm">
      <span>{label}</span>
      <span className="inline-flex gap-0.5">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce-dot"
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </span>
    </span>
  );
}
