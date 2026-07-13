import useHealth from "../hooks/useHealth.js";
import PageHeader from "../components/ui/PageHeader.jsx";

const FEATURE_CARDS = [
  {
    key: "copilot",
    emoji: "💬",
    title: "Knowledge Copilot",
    desc: "Ask natural-language questions across every ingested document, with citations and confidence scoring.",
    accent: "from-blue-500 to-indigo-600",
    glow: "hover:shadow-blue-500/20",
  },
  {
    key: "pid",
    emoji: "📐",
    title: "P&ID Symbol Viewer",
    desc: "Upload a P&ID drawing and detect valves, pumps, tanks, instruments & flow arrows via computer vision.",
    accent: "from-orange-400 to-amber-600",
    glow: "hover:shadow-orange-500/20",
  },
  {
    key: "maintenance",
    emoji: "🔧",
    title: "Maintenance & RCA",
    desc: "Root-cause analysis and asset risk scoring for equipment tags, grounded in maintenance history.",
    accent: "from-emerald-500 to-teal-600",
    glow: "hover:shadow-emerald-500/20",
  },
  {
    key: "compliance",
    emoji: "📋",
    title: "Compliance Tracker",
    desc: "Cross-reference facility records against Indian regulatory requirements (Factory Act, OISD, PESO).",
    accent: "from-purple-500 to-fuchsia-600",
    glow: "hover:shadow-purple-500/20",
  },
];

function StatusPill({ ok, label, delay = 0 }) {
  return (
    <span
      className={`stagger-item inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full border transition-all duration-300 ${
        ok
          ? "bg-emerald-50 text-emerald-700 border-emerald-200"
          : "bg-red-50 text-red-700 border-red-200"
      }`}
      style={{ animationDelay: `${delay}ms` }}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${ok ? "bg-emerald-500 animate-pulse" : "bg-red-500"}`} />
      {label}
    </span>
  );
}

function StatCard({ value, label, icon, delay = 0 }) {
  return (
    <div
      className="stagger-item card p-4 flex items-center gap-3"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center text-lg">
        {icon}
      </div>
      <div>
        <p className="text-xl font-bold text-slate-800">{value}</p>
        <p className="text-xs text-slate-500">{label}</p>
      </div>
    </div>
  );
}

export default function Dashboard({ onNavigate }) {
  const health = useHealth();
  const backendUp = health.status === "ok";
  const chunks = health.services?.chromadb?.chunks ?? 0;

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 sm:py-8 space-y-6 sm:space-y-8">
      <PageHeader
        badge="Industrial Knowledge Brain"
        title="Unified AI intelligence for asset-intensive plants"
        subtitle="Documents, drawings, maintenance history, and compliance — in one place, queryable in plain language and linked through a live knowledge graph."
      />

      {/* Quick stats row */}
      {backendUp && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <StatCard value={chunks} label="Indexed chunks" icon="📚" delay={100} />
          <StatCard
            value={health.services?.neo4j?.reachable ? "Connected" : "Offline"}
            label="Knowledge graph"
            icon="🔗"
            delay={200}
          />
          <StatCard value="6" label="AI subsystems" icon="⚡" delay={300} />
        </div>
      )}

      {/* System status */}
      <div className="card p-5 stagger-item" style={{ animationDelay: "150ms" }}>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-slate-700">System Status</h2>
          {health.status === "checking" && (
            <span className="text-xs text-slate-400 animate-pulse">Checking…</span>
          )}
        </div>
        {health.status === "unreachable" ? (
          <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 animate-slide-up">
            Can't reach the backend at <code>localhost:8000</code>. Make sure the
            API server is running (<code>docker compose up</code> or{" "}
            <code>uvicorn app.main:app</code>).
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            <StatusPill ok={backendUp} label="API server" delay={200} />
            <StatusPill ok={!!health.services?.chromadb?.reachable} label="Vector store (ChromaDB)" delay={300} />
            <StatusPill ok={!!health.services?.neo4j?.reachable} label="Knowledge graph (Neo4j)" delay={400} />
            {health.services?.chromadb?.reachable && (
              <span className="text-xs text-slate-400 self-center stagger-item" style={{ animationDelay: "500ms" }}>
                {health.services.chromadb.chunks} chunks indexed
              </span>
            )}
          </div>
        )}
      </div>

      {/* Feature cards */}
      <div>
        <h2 className="text-sm font-semibold text-slate-700 mb-3 stagger-item" style={{ animationDelay: "250ms" }}>
          Subsystems
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {FEATURE_CARDS.map((f, i) => (
            <button
              key={f.key}
              onClick={() => onNavigate(f.key)}
              className={`stagger-item text-left card-interactive p-5 group shadow-sm hover:shadow-lg ${f.glow}`}
              style={{ animationDelay: `${300 + i * 80}ms` }}
            >
              <div
                className={`w-11 h-11 rounded-xl bg-gradient-to-br ${f.accent} flex items-center justify-center text-lg mb-3
                            transition-transform duration-300 group-hover:scale-110 group-hover:rotate-3`}
              >
                {f.emoji}
              </div>
              <h3 className="text-sm font-semibold text-slate-800 mb-1 flex items-center gap-1.5">
                {f.title}
                <span className="text-slate-300 group-hover:translate-x-1 group-hover:text-blue-500 transition-all duration-300">
                  →
                </span>
              </h3>
              <p className="text-xs text-slate-500 leading-relaxed">{f.desc}</p>
            </button>
          ))}
        </div>
      </div>

      {/* Quick tips */}
      <div
        className="stagger-item bg-slate-50 border border-slate-200 rounded-2xl p-5 text-xs text-slate-500 leading-relaxed"
        style={{ animationDelay: "600ms" }}
      >
        <p className="font-semibold text-slate-600 mb-1">💡 Getting started</p>
        <p>
          No documents ingested yet? Try <code>POST /api/ingest</code> from the{" "}
          <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer" className="text-blue-600 hover:underline transition-colors">
            Swagger UI
          </a>{" "}
          with a sample file from <code>backend/data/sample_documents/</code>, then
          come back and ask the Copilot about it.
        </p>
      </div>
    </div>
  );
}
