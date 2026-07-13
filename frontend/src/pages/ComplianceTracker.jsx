import { useState } from "react";
import PageHeader from "../components/ui/PageHeader.jsx";
import { SkeletonCard } from "../components/ui/Skeleton.jsx";
import LoadingDots from "../components/ui/LoadingDots.jsx";

const API_BASE = "http://localhost:8000/api";

const STATUS_CONFIG = {
  covered: { dot: "bg-emerald-500", badge: "bg-emerald-50 text-emerald-700 border-emerald-200", label: "Covered", icon: "✓" },
  partial: { dot: "bg-amber-400", badge: "bg-amber-50 text-amber-700 border-amber-200", label: "Partial", icon: "~" },
  gap: { dot: "bg-red-500", badge: "bg-red-50 text-red-700 border-red-200", label: "Gap", icon: "✗" },
};

const SEVERITY_BADGE = {
  critical: "bg-red-100 text-red-700 border-red-200",
  high: "bg-orange-100 text-orange-700 border-orange-200",
  medium: "bg-yellow-100 text-yellow-700 border-yellow-200",
};

function StatusDot({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.gap;
  return <span className={`inline-block w-3 h-3 rounded-full flex-shrink-0 mt-1 ${cfg.dot}`} />;
}

function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.gap;
  return (
    <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${cfg.badge}`}>
      {cfg.icon} {cfg.label}
    </span>
  );
}

function SeverityBadge({ severity }) {
  const cls = SEVERITY_BADGE[severity] || "bg-slate-100 text-slate-600 border-slate-200";
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border capitalize ${cls}`}>
      {severity}
    </span>
  );
}

function SummaryBar({ covered, partial, gaps, total }) {
  const pctCovered = Math.round((covered / total) * 100) || 0;
  const pctPartial = Math.round((partial / total) * 100) || 0;
  const pctGap = 100 - pctCovered - pctPartial;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-xs font-medium text-slate-500 uppercase tracking-wide">
        <span>Compliance Coverage</span>
        <span>{total} requirements assessed</span>
      </div>
      <div className="w-full h-4 rounded-full overflow-hidden flex bg-slate-100">
        {pctCovered > 0 && (
          <div className="bg-emerald-500 transition-all duration-1000 ease-out" style={{ width: `${pctCovered}%` }} />
        )}
        {pctPartial > 0 && (
          <div className="bg-amber-400 transition-all duration-1000 ease-out" style={{ width: `${pctPartial}%`, transitionDelay: "200ms" }} />
        )}
        {pctGap > 0 && (
          <div className="bg-red-500 transition-all duration-1000 ease-out" style={{ width: `${pctGap}%`, transitionDelay: "400ms" }} />
        )}
      </div>
      <div className="flex gap-4 text-xs text-slate-600">
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block" />
          {covered} Covered
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-amber-400 inline-block" />
          {partial} Partial
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-red-500 inline-block" />
          {gaps} Gaps
        </span>
      </div>
    </div>
  );
}

function RegulationRow({ item, onEvidencePackage, index }) {
  const [open, setOpen] = useState(false);

  return (
    <div
      className="border border-slate-100 rounded-xl overflow-hidden transition-all duration-200 hover:border-slate-200 hover:shadow-sm stagger-item"
      style={{ animationDelay: `${index * 50}ms` }}
    >
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-start gap-3 px-4 py-3 text-left hover:bg-slate-50 transition-colors"
      >
        <StatusDot status={item.status} />
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-0.5">
            <span className="text-xs font-mono text-slate-400">{item.regulation_id}</span>
            <SeverityBadge severity={item.severity} />
            <StatusBadge status={item.status} />
          </div>
          <p className="text-sm font-semibold text-slate-800 leading-tight">
            {item.regulation} — {item.clause}
          </p>
        </div>
        <span className={`text-slate-400 text-sm shrink-0 ml-2 mt-0.5 transition-transform duration-200 ${open ? "rotate-180" : ""}`}>
          ▼
        </span>
      </button>

      {open && (
        <div className="px-4 pb-4 border-t border-slate-100 space-y-3 bg-slate-50/40 animate-slide-down">
          <div className="pt-3">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Requirement</p>
            <p className="text-sm text-slate-700 leading-relaxed">{item.requirement}</p>
          </div>

          {item.evidence_docs.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Evidence Documents</p>
              <div className="flex flex-wrap gap-1.5">
                {item.evidence_docs.map((d, i) => (
                  <span key={i} className="text-xs bg-blue-50 border border-blue-100 text-blue-700 px-2 py-0.5 rounded">
                    📄 {d}
                  </span>
                ))}
              </div>
            </div>
          )}

          {item.gap_explanation && (
            <div
              className={`rounded-lg p-3 text-sm leading-relaxed border ${
                item.status === "gap"
                  ? "bg-red-50 border-red-100 text-red-800"
                  : "bg-amber-50 border-amber-100 text-amber-800"
              }`}
            >
              <strong>Gap / Issue: </strong>
              {item.gap_explanation}
            </div>
          )}

          {item.remediation && (
            <div className="bg-indigo-50 border border-indigo-100 rounded-lg p-3 text-sm text-indigo-800 leading-relaxed">
              <strong>Suggested Remediation: </strong>
              {item.remediation}
            </div>
          )}

          <div className="flex gap-2 pt-1">
            <button
              onClick={() => onEvidencePackage(item.regulation_id)}
              className="btn-secondary text-xs hover:border-blue-300 hover:text-blue-600"
            >
              📋 Generate Evidence Package
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function EvidenceModal({ data, onClose }) {
  if (!data) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4 animate-fade-in" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto animate-scale-in"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-6 border-b border-slate-100">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs text-slate-400 font-mono">{data.regulation_id}</p>
              <h2 className="text-lg font-bold text-slate-800 mt-0.5">Audit Evidence Package</h2>
              <p className="text-sm text-slate-600 mt-1">{data.regulation} — {data.clause}</p>
            </div>
            <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl leading-none transition-colors hover:rotate-90 duration-200">
              ✕
            </button>
          </div>
        </div>

        <div className="p-6 space-y-5">
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Regulatory Requirement</p>
            <p className="text-sm text-slate-700 bg-slate-50 border border-slate-100 rounded-lg p-3 leading-relaxed">
              {data.requirement}
            </p>
          </div>

          {data.coverage_summary && (
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Coverage Summary (AI-Generated)</p>
              <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap">{data.coverage_summary}</p>
            </div>
          )}

          {data.evidence_documents.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Source Documents</p>
              <div className="space-y-2">
                {data.evidence_documents.map((d, i) => (
                  <div key={i} className="flex items-start gap-2 bg-slate-50 border border-slate-100 rounded-lg px-3 py-2 stagger-item" style={{ animationDelay: `${i * 60}ms` }}>
                    <span className="text-blue-400 mt-0.5">📄</span>
                    <div>
                      <p className="text-sm font-medium text-slate-700">{d.filename}</p>
                      <p className="text-xs text-slate-400">{d.relevance}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-800 leading-relaxed">
            {data.disclaimer}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ComplianceTracker() {
  const [query, setQuery] = useState("CDU-1 P-101A");
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("all");
  const [evidenceModal, setEvidenceModal] = useState(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);

  async function runAnalysis(e) {
    if (e) e.preventDefault();
    if (!query.trim() || loading) return;
    setLoading(true);
    setError(null);
    setReport(null);
    try {
      const res = await fetch(`${API_BASE}/compliance/gap-analysis`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query.trim() }),
      });
      if (!res.ok) throw new Error(`Server error ${res.status}`);
      const data = await res.json();
      setReport(data);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  async function fetchEvidencePackage(regulationId) {
    setEvidenceLoading(true);
    try {
      const res = await fetch(`${API_BASE}/compliance/evidence-package`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ regulation_id: regulationId }),
      });
      if (!res.ok) throw new Error(`Server error ${res.status}`);
      const data = await res.json();
      setEvidenceModal(data);
    } catch (err) {
      alert(`Failed to generate evidence package: ${err}`);
    } finally {
      setEvidenceLoading(false);
    }
  }

  const filteredItems = report ? report.items.filter((i) => filter === "all" || i.status === filter) : [];

  return (
    <div className="flex flex-col flex-1 min-h-0 max-w-4xl mx-auto w-full">
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-6">
        <PageHeader
          badge="Regulatory Compliance"
          title="Compliance Gap Tracker"
          subtitle="Cross-references ingested procedures & inspection records against Indian regulatory requirements (Factory Act, OISD, PESO)."
          gradient="from-slate-800 via-slate-700 to-indigo-800"
        >
          <div className="mt-3 bg-amber-500/20 border border-amber-400/40 rounded-lg px-3 py-2 text-xs text-amber-200 leading-relaxed">
            ⚠ <strong>Disclaimer:</strong> This is an AI decision-support tool only — NOT legal or regulatory advice.
          </div>
        </PageHeader>

        {!report && !loading && !error && (
          <div className="card p-5 animate-slide-up">
            <p className="text-sm text-slate-600">
              Enter a facility area or equipment tag below to run a regulatory gap analysis against
              Factory Act, OISD, and PESO requirements.
            </p>
          </div>
        )}

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm animate-slide-up">
          ⚠ <strong>Error:</strong> {error}
        </div>
      )}

      {loading && (
        <div className="space-y-3">
          <SkeletonCard lines={2} />
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-14 bg-slate-200 rounded-xl animate-shimmer" />
          ))}
        </div>
      )}

      {report && (
        <div className="space-y-5 animate-page-enter">
          <div className="card p-5 space-y-4">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <h2 className="text-sm font-bold text-slate-800">
                Analysis for: <span className="text-indigo-600">{report.facility_area}</span>
              </h2>
              <span className="text-xs text-slate-400">{report.total_requirements} regulations assessed</span>
            </div>
            <SummaryBar covered={report.covered} partial={report.partial} gaps={report.gaps} total={report.total_requirements} />
          </div>

          <div className="flex gap-2 flex-wrap">
            {["all", "gap", "partial", "covered"].map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-3.5 py-1.5 rounded-full text-xs font-semibold border transition-all duration-200 active:scale-95 ${
                  filter === f
                    ? "bg-indigo-600 text-white border-indigo-600 shadow-md shadow-indigo-600/25"
                    : "bg-white text-slate-600 border-slate-200 hover:border-indigo-300"
                }`}
              >
                {f === "all"
                  ? `All (${report.total_requirements})`
                  : f === "gap"
                  ? `Gaps (${report.gaps})`
                  : f === "partial"
                  ? `Partial (${report.partial})`
                  : `Covered (${report.covered})`}
              </button>
            ))}
          </div>

          <div className="space-y-2">
            {filteredItems.map((item, i) => (
              <RegulationRow key={item.regulation_id} item={item} onEvidencePackage={fetchEvidencePackage} index={i} />
            ))}
            {filteredItems.length === 0 && (
              <p className="text-sm text-slate-400 text-center py-6">No regulations match this filter.</p>
            )}
          </div>

          <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 text-xs text-amber-800 leading-relaxed">
            {report.disclaimer}
          </div>
        </div>
      )}

      {evidenceLoading && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm animate-fade-in">
          <div className="bg-white rounded-2xl px-8 py-6 shadow-xl animate-scale-in">
            <LoadingDots label="Generating evidence package" />
          </div>
        </div>
      )}
      {evidenceModal && <EvidenceModal data={evidenceModal} onClose={() => setEvidenceModal(null)} />}
      </div>

      <footer className="shrink-0 bg-white border-t border-slate-200 p-3">
        <form onSubmit={runAnalysis} className="max-w-4xl mx-auto space-y-2">
          <label htmlFor="compliance-query" className="text-xs font-semibold text-slate-600">
            Facility area / equipment tag
          </label>
          <div className="flex gap-2.5">
            <input
              id="compliance-query"
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. CDU-1, P-101A, crude distillation unit"
              className="flex-1 input-field focus:ring-indigo-500"
            />
            <button
              type="submit"
              disabled={loading || !query.trim()}
              className="btn-primary shrink-0 bg-indigo-600 hover:bg-indigo-700"
            >
              {loading ? "Analysing…" : "Run Analysis"}
            </button>
          </div>
        </form>
      </footer>
    </div>
  );
}
