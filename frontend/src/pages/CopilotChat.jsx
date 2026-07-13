import { useState, useRef, useEffect, useCallback } from "react";
import LoadingDots from "../components/ui/LoadingDots.jsx";

const API_BASE = "http://localhost:8000/api";

const ROLES = [
  { value: "technician", label: "Technician" },
  { value: "engineer", label: "Engineer" },
  { value: "auditor", label: "Auditor" },
];

const SUGGESTED_PROMPTS = [
  "What is the vibration trip limit for P-101A?",
  "Summarize recent maintenance on the crude charge pump",
  "Which safety procedures cover hot work permits?",
];

const CONFIDENCE_STYLES = {
  high: "bg-green-100 text-green-800 border-green-300",
  medium: "bg-yellow-100 text-yellow-800 border-yellow-300",
  low: "bg-red-100 text-red-800 border-red-300",
};

function ConfidenceBadge({ level }) {
  const style = CONFIDENCE_STYLES[level] || CONFIDENCE_STYLES.low;
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold border ${style}`}>
      {level?.toUpperCase() || "LOW"} confidence
    </span>
  );
}

function SourceCard({ source }) {
  const [open, setOpen] = useState(false);
  const pct = Math.round((source.relevance_score ?? 0) * 100);

  return (
    <div className="border border-slate-200 rounded-lg bg-white overflow-hidden transition-all duration-200 hover:border-blue-200">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-slate-50 transition-colors"
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-medium text-slate-700 truncate">{source.doc_name}</span>
          <span className="text-xs text-slate-400 shrink-0">{pct}% match</span>
        </div>
        <span className={`text-slate-400 text-sm shrink-0 ml-2 transition-transform duration-200 ${open ? "rotate-180" : ""}`}>
          ▼
        </span>
      </button>
      {open && (
        <div className="px-3 pb-3 pt-1 text-sm text-slate-600 border-t border-slate-100 bg-slate-50 animate-slide-down">
          {source.snippet}
        </div>
      )}
    </div>
  );
}

function RelatedEntities({ entities }) {
  if (!entities || entities.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5 mt-2">
      {entities.map((e, i) => (
        <span
          key={i}
          className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full border border-slate-200
                     transition-all duration-200 hover:bg-blue-50 hover:border-blue-200 hover:text-blue-700"
          title={e.relationship || undefined}
        >
          {e.label}: {e.value}
        </span>
      ))}
    </div>
  );
}

function VoiceInfoBar({ voiceInfo }) {
  if (!voiceInfo) return null;
  const { detected_language_name, translation_method, transcript } = voiceInfo;
  return (
    <div className="bg-indigo-50 border border-indigo-200 rounded-lg px-3 py-2 text-xs space-y-1 animate-slide-down">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-indigo-600 font-semibold">🎤 Voice Query</span>
        <span className="text-indigo-500">Detected: {detected_language_name}</span>
        {translation_method !== "none" && (
          <span className="text-indigo-400">(translated via {translation_method})</span>
        )}
      </div>
      <div className="text-indigo-700 italic truncate">"{transcript}"</div>
    </div>
  );
}

function AudioPlayButton({ base64Audio }) {
  if (!base64Audio) return null;

  const play = () => {
    const audio = new Audio(`data:audio/wav;base64,${base64Audio}`);
    audio.play().catch(() => {});
  };

  return (
    <button
      onClick={play}
      className="inline-flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 mt-1 transition-colors active:scale-95"
      title="Play spoken answer"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
        <path d="M8 5v14l11-7z" />
      </svg>
      Play audio response
    </button>
  );
}

function MessageBubble({ message, index }) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="space-y-1 animate-message-in" style={{ animationDelay: `${index * 30}ms` }}>
        {message.voiceInfo && <VoiceInfoBar voiceInfo={message.voiceInfo} />}
        <div className="flex justify-end">
          <div className="max-w-[85%] sm:max-w-[70%] bg-blue-600 text-white rounded-2xl rounded-br-sm px-4 py-2.5 shadow-md shadow-blue-600/20">
            {message.content}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start animate-message-in" style={{ animationDelay: `${index * 30}ms` }}>
      <div className="max-w-[90%] sm:max-w-[75%] w-full space-y-2">
        <div className="bg-white border border-slate-200 rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm">
          {message.error && (
            <div className="text-xs text-red-600 mb-1 font-medium">
              ⚠ System error — showing fallback response
            </div>
          )}
          <p className="text-slate-800 whitespace-pre-wrap leading-relaxed">{message.content}</p>
          <div className="mt-2">
            <ConfidenceBadge level={message.confidence} />
          </div>
          <AudioPlayButton base64Audio={message.audioBase64} />
          <RelatedEntities entities={message.related_entities} />
        </div>

        {message.sources && message.sources.length > 0 && (
          <div className="space-y-1.5 pl-1">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">Sources</p>
            {message.sources.map((s, i) => (
              <SourceCard key={i} source={s} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function RecordingIndicator() {
  return (
    <div className="flex items-center gap-1.5 animate-fade-in">
      <div className="flex items-end gap-0.5 h-5">
        {[1, 2, 3, 4, 5].map((i) => (
          <div
            key={i}
            className="w-1 bg-red-500 rounded-full"
            style={{
              animation: `waveBar 0.8s ease-in-out ${i * 0.1}s infinite alternate`,
              height: "4px",
            }}
          />
        ))}
      </div>
      <span className="text-xs font-medium text-red-600 animate-pulse">Recording…</span>
    </div>
  );
}

function MicButton({ recording, onStart, onStop, disabled }) {
  return (
    <button
      onClick={recording ? onStop : onStart}
      disabled={disabled && !recording}
      className={`shrink-0 rounded-xl px-3 py-2 text-sm font-medium transition-all duration-200 active:scale-95 ${
        recording
          ? "bg-red-500 text-white hover:bg-red-600 animate-glow-pulse"
          : "bg-slate-100 text-slate-600 hover:bg-slate-200 disabled:opacity-40 disabled:cursor-not-allowed"
      }`}
      title={recording ? "Stop recording" : "Record voice query"}
    >
      {recording ? (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
          <rect x="6" y="6" width="12" height="12" rx="2" />
        </svg>
      ) : (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
          <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
        </svg>
      )}
    </button>
  );
}

function SuggestedPrompts({ onSelect, disabled }) {
  return (
    <div className="flex flex-wrap gap-2 justify-center">
      {SUGGESTED_PROMPTS.map((prompt) => (
        <button
          key={prompt}
          onClick={() => onSelect(prompt)}
          disabled={disabled}
          className="text-xs bg-white border border-slate-200 text-slate-600 rounded-full px-3 py-1.5
                     hover:border-blue-300 hover:text-blue-600 hover:bg-blue-50 transition-all duration-200
                     active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {prompt}
        </button>
      ))}
    </div>
  );
}

export default function CopilotChat() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [role, setRole] = useState("engineer");
  const [sessionId, setSessionId] = useState(null);
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);
  const textareaRef = useRef(null);

  const [recording, setRecording] = useState(false);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 128)}px`;
  }, [input]);

  async function sendMessage(text) {
    const question = (text || input).trim();
    if (!question || loading) return;

    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, role, session_id: sessionId }),
      });

      if (!res.ok) throw new Error(`Server responded ${res.status}`);

      const data = await res.json();
      setSessionId(data.session_id);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.answer,
          sources: data.sources,
          confidence: data.confidence,
          related_entities: data.related_entities,
          error: data.error,
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Couldn't reach the Copilot backend. Check that the API server is running on localhost:8000.",
          confidence: "low",
          sources: [],
          related_entities: [],
          error: String(err),
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
          ? "audio/webm;codecs=opus"
          : "audio/webm",
      });
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        if (blob.size === 0) return;

        setLoading(true);
        const formData = new FormData();
        formData.append("audio", blob, "recording.webm");
        formData.append("role", role);
        if (sessionId) formData.append("session_id", sessionId);

        try {
          const res = await fetch(`${API_BASE}/voice/query`, { method: "POST", body: formData });
          if (!res.ok) throw new Error(`Server responded ${res.status}`);

          const data = await res.json();
          setSessionId(data.session_id);

          const displayText =
            data.detected_language === "en"
              ? data.transcript
              : data.query_english || data.transcript;

          setMessages((prev) => [
            ...prev,
            {
              role: "user",
              content: displayText,
              voiceInfo: {
                transcript: data.transcript,
                detected_language_name: data.detected_language_name,
                translation_method: data.translation_method,
              },
            },
          ]);

          const answerText =
            data.detected_language !== "en" && data.answer_translated
              ? `${data.answer_translated}\n\n--- English ---\n${data.answer_english}`
              : data.answer_english;

          setMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              content: answerText,
              sources: data.sources,
              confidence: data.confidence,
              related_entities: data.related_entities,
              audioBase64: data.audio_response_base64,
              error: data.error,
            },
          ]);
        } catch (err) {
          setMessages((prev) => [
            ...prev,
            {
              role: "user",
              content: "(Voice query)",
              voiceInfo: { transcript: "(processing failed)", detected_language_name: "Unknown", translation_method: "none" },
            },
            {
              role: "assistant",
              content: "Couldn't process voice query. Check that the API server is running.",
              confidence: "low",
              sources: [],
              related_entities: [],
              error: String(err),
            },
          ]);
        } finally {
          setLoading(false);
        }
      };

      mediaRecorder.start();
      setRecording(true);
    } catch (err) {
      console.error("Microphone access denied:", err);
      alert("Microphone access is required for voice queries. Please allow microphone access in your browser settings.");
    }
  }, [role, sessionId]);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && recording) {
      mediaRecorderRef.current.stop();
      setRecording(false);
    }
  }, [recording]);

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  return (
    <div className="flex flex-col flex-1 min-h-0 max-w-3xl mx-auto w-full">
      {/* Header */}
      <header className="shrink-0 bg-white border-b border-slate-200 px-4 py-3 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-base sm:text-lg font-semibold text-slate-900 truncate">
            Expert Knowledge Copilot
          </h1>
          <p className="text-xs text-slate-500 truncate">
            Industrial Knowledge Brain — Voice Enabled 🎤
          </p>
        </div>
        <select
          value={role}
          onChange={(e) => setRole(e.target.value)}
          className="text-sm border border-slate-300 rounded-lg px-2 py-1.5 bg-white shrink-0 transition-all focus:ring-2 focus:ring-blue-500 focus:outline-none"
        >
          {ROLES.map((r) => (
            <option key={r.value} value={r.value}>{r.label}</option>
          ))}
        </select>
      </header>

      {/* Messages */}
      <main className="flex-1 overflow-y-auto px-3 sm:px-4 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center mt-8 sm:mt-12 px-4 space-y-5 animate-fade-in">
            <div className="w-16 h-16 mx-auto rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-2xl shadow-lg shadow-blue-500/25 animate-float">
              💬
            </div>
            <div className="space-y-2">
              <p className="text-slate-500 text-sm">
                Ask a question about ingested maintenance records, safety procedures, or inspection reports.
              </p>
              <p className="text-xs text-slate-400">
                💡 Click the mic to ask in Hindi, Tamil, Telugu, or any Indian language.
              </p>
            </div>
            <SuggestedPrompts onSelect={(p) => sendMessage(p)} disabled={loading} />
          </div>
        )}
        {messages.map((m, i) => (
          <MessageBubble key={i} message={m} index={i} />
        ))}
        {loading && (
          <div className="flex justify-start animate-fade-in">
            <div className="bg-white border border-slate-200 rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm">
              <LoadingDots label="Thinking" />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </main>

      {/* Input */}
      <footer className="shrink-0 bg-white border-t border-slate-200 p-3">
        {recording && (
          <div className="mb-2 flex justify-center">
            <RecordingIndicator />
          </div>
        )}
        <div className="flex items-end gap-2">
          <MicButton
            recording={recording}
            onStart={startRecording}
            onStop={stopRecording}
            disabled={loading}
          />
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask the Copilot…"
            rows={1}
            className="flex-1 resize-none input-field max-h-32"
          />
          <button
            onClick={() => sendMessage()}
            disabled={loading || !input.trim()}
            className="btn-primary shrink-0 px-4 py-2"
          >
            Send
          </button>
        </div>
      </footer>
    </div>
  );
}
