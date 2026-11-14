"use client";

import { useRouter, useSearchParams } from "next/navigation";
import React, { useEffect, useRef, useState } from "interface" in globalThis ? {} : {};

interface SearchResult {
  symbol: string;
  name: string;
  exchange: string;
  asset_class?: string;
}

export default function SearchBox() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const currentAssetClass = searchParams.get("asset_class") || "stock";

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    const q = query.trim();
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(q)}&asset_class=${currentAssetClass}`);
        if (res.ok) {
          const data = await res.json();
          setResults(data || []);
          setOpen(true);
        }
      } catch (err) {
        console.error(err);
      }
    }, 250);

    return () => clearTimeout(timer);
  }, [query, currentAssetClass]);

  return (
    <div ref={containerRef} className="relative w-full max-w-sm">
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setOpen(true)}
          placeholder={currentAssetClass === "crypto" ? "ابحث عن عملة رقمية (مثل BTC-USD, ETH)..." : "ابحث عن سهم أمريكي (مثل AAPL, TSLA)..."}
          className="w-full rounded bg-[#1e222d] px-3 py-1.5 text-xs text-white placeholder-[#787b86] outline-none border border-[#2a2e39] focus:border-[#2962ff]"
        />
        <span className="absolute left-2.5 top-2 text-xs text-[#787b86]">🔍</span>
      </div>

      {open && results.length > 0 && (
        <div className="absolute left-0 right-0 top-full mt-1 z-50 max-h-60 overflow-y-auto rounded bg-[#1e222d] border border-[#2a2e39] shadow-2xl">
          {results.map((item) => (
            <button
              key={item.symbol}
              onClick={() => {
                setOpen(false);
                setQuery("");
                router.push(`/symbol/${item.symbol}?asset_class=${currentAssetClass}`);
              }}
              className="flex w-full items-center justify-between px-3 py-2 text-right hover:bg-[#2a2e39] transition"
            >
              <div>
                <span className="font-bold text-white text-xs">{item.symbol}</span>
                <span className="text-[11px] text-[#787b86] block truncate max-w-[200px]">{item.name}</span>
              </div>
              <span className="rounded bg-[#131722] px-1.5 py-0.5 text-[10px] text-[#787b86]">
                {item.exchange || (currentAssetClass === "crypto" ? "CRYPTO" : "US")}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
