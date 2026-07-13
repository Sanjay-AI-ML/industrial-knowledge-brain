import { useEffect, useState } from "react";

const API_BASE = "http://localhost:8000/api";
const HEALTH_URL = API_BASE.replace(/\/api$/, "/health");

/** Polls GET /health every `intervalMs` and exposes the latest reading. */
export default function useHealth(intervalMs = 15000) {
  const [health, setHealth] = useState({ status: "checking" });

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const res = await fetch(HEALTH_URL);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!cancelled) setHealth({ status: "ok", ...data });
      } catch (err) {
        if (!cancelled) setHealth({ status: "unreachable", error: String(err) });
      }
    }

    poll();
    const id = setInterval(poll, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [intervalMs]);

  return health;
}
