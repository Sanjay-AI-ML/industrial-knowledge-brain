import { useState } from "react";
import PageHeader from "../components/ui/PageHeader.jsx";
import { SkeletonCard } from "../components/ui/Skeleton.jsx";

const API_BASE = "http://localhost:8000/api";

const CATEGORY_COLORS = {
  Machine: "border-blue-200 bg-blue-50 text-blue-800",
  Man: "border-purple-200 bg-purple-50 text-purple-800",
  Method: "border-orange-200 bg-orange-50 text-orange-800",
  Material: "border-teal-200 bg-teal-50 text-teal-800",
  Environment: "border-emerald-200 bg-emerald-50 text-emerald-800",
};

const RISK_LEVELS = {
  low: { color: "text-green-600 bg-green-50 border-green-200", label: "Low Risk", ring: "#10b981" },
  medium: { color: "text-amber-600 bg-amber-50 border-amber-200", label: "Medium Risk", ring: "#f59e0b" },
  high: { color: "text-red-600 bg-red-50 border-red-200", label: "High Risk", ring: "#ef4444" },
};

const QUICK_QUERIES = ["P-101A", "V-203", "vibration trip on Crude Charge Pump"];

export default function MaintenanceRCA() {
  const [query, setQuery] = useState("P-101A");
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState(null);
  const [risk, setRisk] = useState(null);
  const [error, setError] = useState(null);

  async function handleAnalyze(e, overrideQuery) {
    if (e) e.preventDefault();
    const q = (overrideQuery || query).trim();
    if (!q || loading) return;
    if (overrideQuery) setQuery(overrideQuery);

    setLoading(true);
    setError(null);
    setReport(null);
    setRisk(null);

    try {
      const rcaRes = await fetch(`${API_BASE}/maintenance/rca`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q }),
      });
      if (!rcaRes.ok) throw new Error("RCA generation failed.");
      const rcaData = await rcaRes.json();

      const resolvedTag = rcaData.equipment_tag || q;
      let riskData = null;
      try {
        const riskRes = await fetch(`${API_BASE}/maintenance/risk-score/${resolvedTag}`);
        if (riskRes.ok) riskData = await riskRes.json();
      } catch (err) {
        console.warn("Failed to retrieve risk score:", err);
      }

      setReport(rcaData);
      setRisk(riskData);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col flex-1 min-h-0 max-w-4xl mx-auto w-full">
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-6">
        <PageHeader
          badge="Maintenance Intelligence"
          title="Maintenance Intelligence & RCA"
          subtitle="Perform digital 5-Whys Root Cause Analyses and calculate asset health risk indicators."
          gradient="from-blue-700 via-indigo-700 to-indigo-800"
        />

        {!report && !loading && !error && (
          <div className="card p-5 animate-slide-up space-y-3">
            <p className="text-sm text-slate-600">
              Enter an equipment tag or describe an incident below to run a fishbone-style root cause analysis
              and risk score.
            </p>
            <div className="flex flex-wrap gap-2">
              {QUICK_QUERIES.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => handleAnalyze(null, q)}
                  disabled={loading}
                  className="text-xs bg-slate-50 border border-slate-200 text-slate-500 rounded-full px-3 py-1
                             hover:border-blue-300 hover:text-blue-600 hover:bg-blue-50 transition-all active:scale-95
                             disabled:opacity-40"
                >
                  Try: {q}
                </button>
              ))}
            </div>
          </div>
        )}

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm animate-slide-up">
          ⚠ <strong>Analysis Error:</strong> {error}
        </div>
      )}

      {loading && (
        <div className="space-y-4">
          <SkeletonCard lines={2} />
          <SkeletonCard lines={5} />
        </div>
      )}

      {report && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 animate-page-enter">
          <div className="md:col-span-1 space-y-6">
            <div className="card p-5 space-y-4">
              <div>
                <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wider">Asset Identity</h3>
                <div className="text-lg font-bold text-slate-800 mt-1">
                  Tag: {report.equipment_tag || "Unknown"}
                </div>
              </div>

              {risk && (
                <div className="pt-2 border-t border-slate-100 space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-slate-600">Heuristic Risk Score</span>
                    <span className={`text-xs px-2.5 py-0.5 rounded-full font-bold border ${RISK_LEVELS[risk.level]?.color || "text-slate-600 bg-slate-50 border-slate-200"}`}>
                      {RISK_LEVELS[risk.level]?.label || "Low"}
                    </span>
                  </div>

                  <div className="flex justify-center py-2">
                    <div className="relative w-28 h-28 flex items-center justify-center rounded-full bg-slate-50 border-4 border-slate-100 transition-all duration-500">
                      <div className="text-center">
                        <span className="text-3xl font-extrabold text-slate-800">{risk.score}</span>
                        <span className="text-xs text-slate-400 block font-semibold">/ 100</span>
                      </div>
                      <div
                        className="absolute inset-0 rounded-full border-4 border-transparent pointer-events-none transition-all duration-700"
                        style={{
                          borderColor: RISK_LEVELS[risk.level]?.ring || "#10b981",
                          clipPath: `polygon(50% 50%, -50% -50%, ${risk.score}% -50%, ${risk.score}% 150%, -50% 150%)`,
                        }}
                      />
                    </div>
                  </div>

                  <div className="space-y-1.5 pt-2 border-t border-slate-100">
                    <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Heuristic Breakdown</h4>
                    {risk.breakdown.map((item, idx) => (
                      <p key={idx} className="text-xs text-slate-600 leading-relaxed flex items-start gap-1 stagger-item" style={{ animationDelay: `${idx * 60}ms` }}>
                        <span className="text-blue-500 shrink-0 select-none">•</span>
                        <span>{item}</span>
                      </p>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="md:col-span-2 space-y-6">
            <div className="card p-5 space-y-4">
              <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wide border-b border-slate-100 pb-2">
                Probable Root Causes (Fishbone Layout)
              </h3>
              <div className="space-y-4">
                {report.probable_root_causes.map((c, idx) => (
                  <div
                    key={idx}
                    className="border border-slate-100 rounded-xl p-4 space-y-2 hover:border-slate-200 hover:shadow-sm transition-all duration-200 stagger-item"
                    style={{ animationDelay: `${idx * 80}ms` }}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className={`text-xs px-2.5 py-0.5 rounded-full font-bold border ${CATEGORY_COLORS[c.category] || "border-slate-200 bg-slate-50"}`}>
                        {c.category} Category
                      </span>
                      <span className="text-xs text-slate-400 font-medium capitalize">
                        Confidence: <strong className="text-slate-600 font-semibold">{c.confidence}</strong>
                      </span>
                    </div>
                    <p className="text-sm text-slate-800 font-medium">{c.cause}</p>
                    <div className="text-xs text-slate-500 bg-slate-50 border border-slate-100 rounded-lg p-2.5 italic">
                      <strong>Evidence:</strong> "{c.supporting_evidence}"
                    </div>
                  </div>
                ))}
                {report.probable_root_causes.length === 0 && (
                  <p className="text-sm text-slate-400">No root causes identified.</p>
                )}
              </div>
            </div>

            <div className="card p-5 space-y-3">
              <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wide border-b border-slate-100 pb-2">
                Recommended Actions
              </h3>
              <ul className="space-y-2">
                {report.recommended_actions.map((act, idx) => (
                  <li key={idx} className="text-sm text-slate-700 flex items-start gap-2.5 leading-relaxed stagger-item" style={{ animationDelay: `${idx * 50}ms` }}>
                    <span className="text-blue-500 font-bold shrink-0 mt-0.5">✓</span>
                    <span>{act}</span>
                  </li>
                ))}
                {report.recommended_actions.length === 0 && (
                  <li className="text-sm text-slate-400">No specific actions recommended.</li>
                )}
              </ul>
            </div>

            <div className="card p-5 space-y-3">
              <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wide border-b border-slate-100 pb-2">
                Similar Past Incidents
              </h3>
              <div className="space-y-3">
                {report.similar_past_incidents.map((inc, idx) => (
                  <div key={idx} className="border border-slate-100 rounded-xl p-3 bg-slate-50/50 space-y-1 hover:border-slate-200 transition-all stagger-item" style={{ animationDelay: `${idx * 60}ms` }}>
                    <div className="text-xs font-bold text-slate-700">ID: {inc.incident_id}</div>
                    <p className="text-xs text-slate-600">{inc.description}</p>
                    <p className="text-xs text-slate-500 italic">
                      <strong>Relevance:</strong> {inc.similarity}
                    </p>
                  </div>
                ))}
                {report.similar_past_incidents.length === 0 && (
                  <p className="text-xs text-slate-400">No past matching incidents found.</p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
      </div>

      <footer className="shrink-0 bg-white border-t border-slate-200 p-3 mx-0">
        <form onSubmit={handleAnalyze} className="max-w-4xl mx-auto space-y-2">
          <label htmlFor="maintenance-query" className="text-xs font-semibold text-slate-600">
            Equipment tag or incident description
          </label>
          <div className="flex gap-2.5">
            <input
              id="maintenance-query"
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. P-101A, V-203, or vibration trip on Crude Charge Pump"
              className="flex-1 input-field"
            />
            <button type="submit" disabled={loading || !query.trim()} className="btn-primary shrink-0">
              {loading ? "Analyzing…" : "Run Analysis"}
            </button>
          </div>
        </form>
      </footer>
    </div>
  );
}
