import { useState, useRef, useCallback } from "react";
import PageHeader from "../components/ui/PageHeader.jsx";
import LoadingDots from "../components/ui/LoadingDots.jsx";

const API_BASE = "http://localhost:8000/api";

const SYMBOL_COLORS = {
  valve: { dot: "bg-orange-500", ring: "ring-orange-300", text: "text-orange-700", bg: "bg-orange-50", border: "border-orange-300" },
  pump: { dot: "bg-blue-600", ring: "ring-blue-300", text: "text-blue-700", bg: "bg-blue-50", border: "border-blue-300" },
  tank: { dot: "bg-green-600", ring: "ring-green-300", text: "text-green-700", bg: "bg-green-50", border: "border-green-300" },
  instrument_bubble: { dot: "bg-purple-600", ring: "ring-purple-300", text: "text-purple-700", bg: "bg-purple-50", border: "border-purple-300" },
  flow_arrow: { dot: "bg-cyan-600", ring: "ring-cyan-300", text: "text-cyan-700", bg: "bg-cyan-50", border: "border-cyan-300" },
  unknown_shape: { dot: "bg-slate-400", ring: "ring-slate-300", text: "text-slate-600", bg: "bg-slate-50", border: "border-slate-300" },
};

const SYMBOL_LABELS = {
  valve: "Valve",
  pump: "Pump",
  tank: "Tank / Vessel",
  instrument_bubble: "Instrument",
  flow_arrow: "Flow arrow",
  unknown_shape: "Unclassified shape",
};

function colorsFor(type) {
  return SYMBOL_COLORS[type] || SYMBOL_COLORS.unknown_shape;
}

function Legend() {
  return (
    <div className="flex flex-wrap gap-3 text-xs text-slate-600">
      {Object.entries(SYMBOL_LABELS).map(([type, label]) => (
        <span key={type} className="flex items-center gap-1.5 transition-transform hover:scale-105">
          <span className={`w-2.5 h-2.5 rounded-full ${colorsFor(type).dot}`} />
          {label}
        </span>
      ))}
    </div>
  );
}

function ConfidenceBar({ value }) {
  const pct = Math.round((value ?? 0) * 100);
  const color = pct >= 65 ? "bg-green-500" : pct >= 40 ? "bg-yellow-500" : "bg-red-400";
  return (
    <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
      <div
        className={`h-full ${color} transition-all duration-700 ease-out`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function EquipmentLookup({ tag }) {
  const [state, setState] = useState({ status: "idle" });

  async function runLookup() {
    setState({ status: "loading" });
    try {
      const res = await fetch(`${API_BASE}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: `What do we know about equipment ${tag}? Summarize any maintenance history, inspection findings, and related documents or regulations.`,
          role: "engineer",
        }),
      });
      if (!res.ok) throw new Error(`Server responded ${res.status}`);
      const data = await res.json();
      setState({ status: "done", data });
    } catch (err) {
      setState({ status: "error", message: String(err) });
    }
  }

  if (state.status === "idle") {
    return (
      <button onClick={runLookup} className="btn-primary w-full text-sm">
        Look up "{tag}" in Knowledge Copilot
      </button>
    );
  }

  if (state.status === "loading") {
    return (
      <div className="px-1 py-2">
        <LoadingDots label={`Searching for ${tag}`} />
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="text-sm text-red-600 px-1 py-2 animate-slide-up">
        Couldn't reach the Copilot backend ({state.message}). Is the API running on localhost:8000?
      </div>
    );
  }

  const { data } = state;
  return (
    <div className="space-y-2 animate-slide-up">
      <p className="text-sm text-slate-800 whitespace-pre-wrap">{data.answer}</p>
      {data.related_entities?.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {data.related_entities.map((e, i) => (
            <span
              key={i}
              className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full border border-slate-200"
              title={e.relationship || undefined}
            >
              {e.label}: {e.value}
            </span>
          ))}
        </div>
      )}
      {data.sources?.length > 0 && (
        <div className="space-y-1 pt-1">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">Related documents</p>
          {data.sources.map((s, i) => (
            <div key={i} className="text-xs border border-slate-200 rounded-md px-2 py-1.5 bg-slate-50 text-slate-600">
              <span className="font-medium text-slate-700">{s.doc_name}</span>
              {" — "}
              {s.snippet?.slice(0, 120)}
              {s.snippet?.length > 120 ? "…" : ""}
            </div>
          ))}
        </div>
      )}
      {(!data.sources || data.sources.length === 0) &&
        (!data.related_entities || data.related_entities.length === 0) && (
          <p className="text-xs text-slate-400">
            No linked documents or graph entities found yet for this tag — ingest a maintenance/inspection record mentioning it to build up history.
          </p>
        )}
    </div>
  );
}

function SymbolDetailPanel({ symbol, onClose }) {
  if (!symbol) return null;
  const c = colorsFor(symbol.symbol_type);
  return (
    <div className={`border rounded-xl p-4 space-y-3 ${c.bg} ${c.border} animate-scale-in`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className={`text-xs font-semibold uppercase tracking-wide ${c.text}`}>
            {SYMBOL_LABELS[symbol.symbol_type] || symbol.symbol_type}
          </p>
          <p className="text-lg font-semibold text-slate-900">
            {symbol.nearby_tag_text || "No tag detected"}
          </p>
        </div>
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-slate-600 text-sm shrink-0 transition-colors hover:rotate-90 duration-200"
        >
          ✕
        </button>
      </div>
      <div>
        <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
          <span>Shape-match confidence</span>
          <span>{Math.round(symbol.confidence * 100)}%</span>
        </div>
        <ConfidenceBar value={symbol.confidence} />
      </div>
      <p className="text-xs text-slate-500">
        Bounding box: {symbol.bounding_box.width}×{symbol.bounding_box.height}px
        at ({symbol.bounding_box.x}, {symbol.bounding_box.y})
      </p>
      {symbol.nearby_tag_text ? (
        <EquipmentLookup tag={symbol.nearby_tag_text} />
      ) : (
        <p className="text-xs text-slate-400 italic">
          No equipment tag was OCR'd near this symbol, so it wasn't linked into the knowledge graph — nothing to look up.
        </p>
      )}
    </div>
  );
}

export default function PIDViewer() {
  const [file, setFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [selectedIdx, setSelectedIdx] = useState(null);
  const [showAnnotated, setShowAnnotated] = useState(false);
  const inputRef = useRef(null);

  const pickFile = useCallback((f) => {
    if (!f) return;
    setFile(f);
    setPreviewUrl(URL.createObjectURL(f));
    setResult(null);
    setSelectedIdx(null);
    setError(null);
  }, []);

  function handleDrop(e) {
    e.preventDefault();
    setDragActive(false);
    const f = e.dataTransfer.files?.[0];
    if (f) pickFile(f);
  }

  async function analyze() {
    if (!file) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setSelectedIdx(null);

    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API_BASE}/pid/analyze?link_to_graph=true`, { method: "POST", body: form });
      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        throw new Error(detail?.detail || `Server responded ${res.status}`);
      }
      const data = await res.json();
      setResult(data);
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setLoading(false);
    }
  }

  const selected = result && selectedIdx !== null ? result.symbols[selectedIdx] : null;

  return (
    <div className="flex-1 flex flex-col">
      <div className="max-w-6xl mx-auto w-full px-4 py-6 space-y-4">
        <PageHeader
          badge="Computer Vision"
          title="P&ID Symbol Viewer"
          subtitle="Upload a P&ID drawing (PNG/JPG) to detect valves, pumps, tanks, instruments & flow arrows, and link tags into the knowledge graph."
          gradient="from-orange-600 via-amber-700 to-orange-800"
        />

        <main className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-4">
          <div className="space-y-3">
            {!previewUrl && (
              <div
                onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
                onDragLeave={() => setDragActive(false)}
                onDrop={handleDrop}
                onClick={() => inputRef.current?.click()}
                className={`border-2 border-dashed rounded-2xl h-64 flex flex-col items-center justify-center gap-3 cursor-pointer
                            transition-all duration-300 ${
                  dragActive
                    ? "border-blue-400 bg-blue-50 scale-[1.02] shadow-lg shadow-blue-500/10"
                    : "border-slate-300 bg-white hover:border-blue-300 hover:bg-slate-50"
                }`}
              >
                <div className={`text-4xl transition-transform duration-300 ${dragActive ? "scale-125" : "animate-float"}`}>
                  📐
                </div>
                <p className="text-sm text-slate-500">Drop a P&ID image here, or click to choose a file</p>
                <p className="text-xs text-slate-400">PNG, JPG, BMP or TIFF</p>
                <input
                  ref={inputRef}
                  type="file"
                  accept=".png,.jpg,.jpeg,.bmp,.tiff"
                  className="hidden"
                  onChange={(e) => pickFile(e.target.files?.[0])}
                />
              </div>
            )}

            {previewUrl && (
              <div className="card overflow-hidden animate-scale-in">
                <div className="flex items-center justify-between px-3 py-2 border-b border-slate-100">
                  <span className="text-sm text-slate-600 truncate">{file?.name}</span>
                  <div className="flex items-center gap-2 shrink-0">
                    {result && (
                      <button
                        onClick={() => setShowAnnotated((v) => !v)}
                        className="btn-secondary text-xs px-2 py-1"
                      >
                        {showAnnotated ? "Interactive view" : "CV-annotated"}
                      </button>
                    )}
                    <button
                      onClick={() => { setFile(null); setPreviewUrl(null); setResult(null); }}
                      className="text-xs text-slate-400 hover:text-slate-600 transition-colors"
                    >
                      Clear
                    </button>
                  </div>
                </div>

                <div className="p-3 bg-slate-50 flex justify-center">
                  {showAnnotated && result ? (
                    <img
                      src={`data:image/png;base64,${result.annotated_image_base64}`}
                      alt="Annotated P&ID"
                      className="max-w-full rounded-lg border border-slate-200 animate-fade-in"
                    />
                  ) : (
                    <div className="relative inline-block leading-none">
                      <img src={previewUrl} alt="Uploaded P&ID" className="max-w-full rounded-lg border border-slate-200 block" />
                      {result?.symbols.map((s, i) => {
                        const c = colorsFor(s.symbol_type);
                        const left = (s.position_x / result.image_width) * 100;
                        const top = (s.position_y / result.image_height) * 100;
                        const isSelected = i === selectedIdx;
                        return (
                          <button
                            key={i}
                            onClick={() => setSelectedIdx(i)}
                            title={`${SYMBOL_LABELS[s.symbol_type] || s.symbol_type}${s.nearby_tag_text ? ` — ${s.nearby_tag_text}` : ""}`}
                            style={{ left: `${left}%`, top: `${top}%`, animationDelay: `${i * 50}ms` }}
                            className={`absolute -translate-x-1/2 -translate-y-1/2 w-4 h-4 rounded-full ${c.dot} border-2 border-white shadow
                                        animate-scale-in transition-transform duration-200 ${
                              isSelected ? `ring-4 ${c.ring} scale-150` : "hover:scale-150"
                            }`}
                          />
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            )}

            {previewUrl && !result && (
              <button onClick={analyze} disabled={loading} className="btn-primary w-full">
                {loading ? (
                  <span className="flex items-center justify-center gap-2">
                    <LoadingDots label="Analyzing" />
                  </span>
                ) : (
                  "Analyze P&ID"
                )}
              </button>
            )}

            {error && (
              <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 animate-slide-up">
                {error}
              </div>
            )}

            {result && (
              <div className="card p-3 space-y-2 animate-slide-up">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-slate-700">
                    {result.symbols.length} symbol{result.symbols.length !== 1 ? "s" : ""} detected
                  </p>
                  {result.graph && (
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full border transition-all ${
                        result.graph.linked
                          ? "bg-green-50 text-green-700 border-green-200"
                          : "bg-slate-50 text-slate-500 border-slate-200"
                      }`}
                    >
                      {result.graph.linked ? `Graph: +${result.graph.nodes_created} nodes` : "Graph not linked"}
                    </span>
                  )}
                </div>
                <Legend />
                <p className="text-xs text-slate-400 pt-1">
                  Click a marker on the image to inspect a symbol and look up its equipment tag.
                </p>
              </div>
            )}
          </div>

          <div className="space-y-3">
            {selected ? (
              <SymbolDetailPanel symbol={selected} onClose={() => setSelectedIdx(null)} />
            ) : (
              <div className="card p-4 text-sm text-slate-400">
                {result
                  ? "Select a marker on the drawing to see its details."
                  : "Upload and analyze a P&ID to see detected symbols here."}
              </div>
            )}

            <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-xs text-amber-800 leading-relaxed">
              <p className="font-semibold mb-1">v1 accuracy note</p>
              <p>
                Detection uses OpenCV contour + shape matching, not a trained model — it works best on clean, high-contrast drawings with standard ISA-style symbols.
              </p>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
