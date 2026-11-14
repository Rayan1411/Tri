"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

/**
 * Fetch `path` now and then every `intervalMs` (0 = once). Pass null to pause.
 * Polling is skipped while the tab is hidden.
 */
export function usePoll<T>(path: string | null, intervalMs = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const alive = useRef(true);

  const load = useCallback(async () => {
    if (path === null) return;
    try {
      const d = await api<T>(path);
      if (!alive.current) return;
      setData(d);
      setError(null);
    } catch (e) {
      if (!alive.current) return;
      setError(e instanceof Error ? e.message : "حدث خطأ");
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    alive.current = true;
    if (path === null) {
      setData(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    load();
    if (!intervalMs) return () => void (alive.current = false);
    const id = setInterval(() => {
      if (document.visibilityState === "visible") load();
    }, intervalMs);
    return () => {
      alive.current = false;
      clearInterval(id);
    };
  }, [path, intervalMs, load]);

  return { data, error, loading, reload: load };
}
