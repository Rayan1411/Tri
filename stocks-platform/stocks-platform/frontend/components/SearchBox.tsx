"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, SearchHit } from "@/lib/api";

export default function SearchBox() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const term = q.trim();
    if (!term) {
      setHits([]);
      return;
    }
    let cancelled = false;
    const t = setTimeout(async () => {
      try {
        const r = await api<SearchHit[]>(`/search?q=${encodeURIComponent(term)}`);
        if (!cancelled) setHits(r);
      } catch {
        if (!cancelled) setHits([]);
      }
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [q]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const go = (symbol: string) => {
    setOpen(false);
    setQ("");
    router.push(`/symbol/${encodeURIComponent(symbol.toUpperCase())}`);
  };

  return (
    <div ref={box} className="relative w-full max-w-md">
      <input
        className="input"
        placeholder="ابحث عن سهم… (AAPL أو Apple)"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && q.trim()) go(hits[0]?.symbol ?? q.trim());
          if (e.key === "Escape") setOpen(false);
        }}
        dir="auto"
      />
      {open && hits.length > 0 && (
        <ul className="absolute inset-x-0 top-full z-30 mt-1 max-h-80 overflow-auto rounded-lg border border-line bg-panel shadow-xl">
          {hits.map((h) => (
            <li key={h.symbol}>
              <button
                className="flex w-full items-center justify-between gap-3 px-3 py-2 text-start text-sm hover:bg-panel2"
                onClick={() => go(h.symbol)}
              >
                <span className="num font-bold">{h.symbol}</span>
                <span className="flex-1 truncate text-xs text-muted" dir="ltr">
                  {h.name}
                </span>
                <span className="text-[10px] text-muted">{h.exchange}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
