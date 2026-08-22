import { useState, useEffect, useRef, useCallback } from "react";
import { getDashboard } from "./useApi";

export function useDashboardData() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const sseRef = useRef(null);

  const fetchData = useCallback(async () => {
    try {
      const d = await getDashboard();
      setData(d);
    } catch (e) {
      console.error("dashboard fetch failed:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const poll = setInterval(fetchData, 2000);

    const sse = new EventSource("/events/stream");
    sse.addEventListener("score", () => fetchData());
    sse.onerror = () => {};
    sseRef.current = sse;

    return () => {
      clearInterval(poll);
      sse.close();
    };
  }, [fetchData]);

  return { data, loading, refresh: fetchData };
}
