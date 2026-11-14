"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import React, { useEffect, useState } from "react";
import AIChat from "../../../../components/AIChat";
import StockChart from "../../../../components/StockChart";

export default function SymbolDetailPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const rawSymbol = params.symbol as string;
  const symbol = decodeURIComponent(rawSymbol || "").toUpperCase();
  const assetClass = searchParams.get("asset_class") || (symbol.includes("-") || symbol.includes("/") ? "crypto" : "stock");

  const [bars, setBars] = useState<any[]>([]);
  const [rangeKey, setRangeKey] = useState<string>("1M");
  const [tradePlans, setTradePlans] = useState<any[]>([]);
  const [snapshot, setSnapshot] = useState<any>(null);
  const [inWatch, setInWatch] = useState(false);

  const toggleWatch = async () => {
    const res = await fetch(inWatch ? `/api/watchlist/${encodeURIComponent(symbol)}` : "/api/watchlist", {
      method: inWatch ? "DELETE" : "POST",
      headers: { "Content-Type": "application/json" },
      body: inWatch ? undefined : JSON.stringify({ symbol, asset_class: assetClass }),
    });
    if (res.ok) setInWatch(!inWatch);
  };

  useEffect(() => {
    if (!symbol) return;
    const fetchData = async () => {
      try {
        const res = await fetch(`/api/stocks/${encodeURIComponent(symbol)}?range=${rangeKey}`);
        if (res.status === 401) {
          window.location.href = "/login";
          return;
        }
        if (res.ok) {
          const data = await res.json();
          setBars(data.bars || []);
          setTradePlans(data.trade_plans || []);
          setSnapshot(data.snapshot || null);
          setInWatch(!!data.in_watchlist);
        }
      } catch (err) {
        console.error(err);
      }
    };
    setBars([]);
    fetchData();
    const id = setInterval(() => {
      if (document.visibilityState === "visible") fetchData();
    }, 10000);
    return () => clearInterval(id);
  }, [symbol, rangeKey]);

  return (
    <div className="flex flex-1 overflow-hidden bg-[#121316] text-[#d1d4dc]">
      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="flex h-12 flex-none items-center justify-between border-b border-[#2a2e39] bg-[#1e222d] px-4">
          <div className="flex items-center space-x-3 space-x-reverse">
            <button
              onClick={() => router.push(`/?asset_class=${assetClass}`)}
              className="rounded bg-[#2a2e39] px-3 py-1 text-xs text-white hover:bg-[#363c4e] transition"
            >
              ⬅ العودة للرئيسية
            </button>
            <span className="text-sm font-bold text-white">{symbol}</span>
            <button
              onClick={toggleWatch}
              className="rounded bg-[#2a2e39] px-3 py-1 text-xs text-white hover:bg-[#363c4e] transition"
            >
              {inWatch ? "★ في المتابعة (إزالة)" : "☆ إضافة للمتابعة"}
            </button>
            {snapshot?.price != null && (
              <span className="text-xs font-bold text-green-400">
                {snapshot.price.toLocaleString()} USD
              </span>
            )}
          </div>
        </div>

        <div className="flex-1 overflow-hidden">
          <StockChart
            symbol={symbol}
            bars={bars}
            rangeKey={rangeKey}
            onRangeChange={setRangeKey}
            tradePlans={tradePlans}
          />
        </div>
      </div>

      <aside className="flex w-96 flex-none flex-col overflow-hidden">
        <AIChat symbol={symbol} rangeKey={rangeKey} />
      </aside>
    </div>
  );
}
