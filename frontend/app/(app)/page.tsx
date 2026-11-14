"use client";

import { useRouter, useSearchParams } from "next/navigation";
import React, { useEffect, useState } from "react";
import AIChat from "../../components/AIChat";
import SearchBox from "../../components/SearchBox";
import StockChart from "../../components/StockChart";

interface Snapshot {
  symbol?: string;
  price?: number;
  change?: number;
  change_pct?: number;
  asset_class?: string;
  [key: string]: any;
}

interface WatchlistItem {
  id: number;
  symbol: string;
  asset_class: string;
  snapshot?: Snapshot;
}

interface TradePlan {
  id: number;
  symbol: string;
  side: string;
  entry_price: number;
  tp1_price?: number;
  tp2_price?: number;
  sl_price?: number;
  status: string;
}

export default function DashboardPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const assetClass = searchParams.get("asset_class") || "stock";

  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string>("");
  const [bars, setBars] = useState<any[]>([]);
  const [rangeKey, setRangeKey] = useState<string>("1M");
  const [tradePlans, setTradePlans] = useState<TradePlan[]>([]);
  const [loadingBars, setLoadingBars] = useState<boolean>(false);

  useEffect(() => {
    const fetchDashboard = async () => {
      try {
        const res = await fetch(`/api/watchlist?asset_class=${assetClass}`);
        if (res.status === 401) {
          window.location.href = "/login";
          return;
        }
        if (res.ok) {
          const items: WatchlistItem[] = (await res.json()) || [];
          setWatchlist(items);

          if (items.length > 0) {
            const defaultSym = items[0].symbol;
            setSelectedSymbol((prev) => (prev && items.some((i) => i.symbol === prev) ? prev : defaultSym));
          } else {
            setSelectedSymbol("");
          }
        }
      } catch (err) {
        console.error(err);
      }
    };
    fetchDashboard();
    // تحديث الأسعار كل 10 ثوانٍ والتبويب ظاهر
    const id = setInterval(() => {
      if (document.visibilityState === "visible") fetchDashboard();
    }, 10000);
    return () => clearInterval(id);
  }, [assetClass]);

  useEffect(() => {
    if (!selectedSymbol) return;
    let first = true;
    const fetchSymbolData = async () => {
      if (first) setLoadingBars(true);
      try {
        const res = await fetch(`/api/stocks/${selectedSymbol}?range=${rangeKey}`);
        if (res.ok) {
          const data = await res.json();
          setBars(data.bars || []);
          setTradePlans(data.trade_plans || []);
        }
      } catch (err) {
        console.error(err);
      } finally {
        first = false;
        setLoadingBars(false);
      }
    };
    setBars([]);
    fetchSymbolData();
    const id = setInterval(() => {
      if (document.visibilityState === "visible") fetchSymbolData();
    }, 10000);
    return () => clearInterval(id);
  }, [selectedSymbol, rangeKey]);

  return (
    <div className="flex flex-1 overflow-hidden bg-[#121316] text-[#d1d4dc]">
      <aside className="flex w-64 flex-none flex-col border-r border-[#2a2e39] bg-[#1e222d]">
        <div className="p-3 border-b border-[#2a2e39]">
          <SearchBox />
        </div>
        <div className="flex h-9 items-center px-3 border-b border-[#2a2e39] text-xs font-bold text-[#787b86]">
          {assetClass === "crypto" ? "🪙 العملات الرقمية المفضلة" : "🇺🇸 الأسهم الأمريكية المفضلة"}
        </div>
        <div className="flex-1 overflow-y-auto divide-y divide-[#2a2e39]">
          {watchlist.map((item) => {
            const snap: Snapshot = item.snapshot || {};
            const price = snap.price;
            const changePct = snap.change_pct;
            const isSelected = item.symbol === selectedSymbol;

            return (
              <button
                key={item.symbol}
                onClick={() => setSelectedSymbol(item.symbol)}
                className={`flex w-full items-center justify-between p-3 text-right transition ${
                  isSelected ? "bg-[#2a2e39]" : "hover:bg-[#1a1e29]"
                }`}
              >
                <div>
                  <div className="font-bold text-white text-xs">{item.symbol}</div>
                  <div className="text-[10px] text-[#787b86]">
                    {assetClass === "crypto" ? "Crypto" : "US Stock"}
                  </div>
                </div>
                <div className="text-left">
                  <div className="text-xs font-bold text-white">
                    {price != null ? price.toLocaleString() : "---"}
                  </div>
                  {changePct != null && (
                    <div className={`text-[10px] font-bold ${changePct >= 0 ? "text-green-400" : "text-red-400"}`}>
                      {changePct >= 0 ? "+" : ""}
                      {changePct.toFixed(2)}%
                    </div>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      </aside>

      <section className="flex flex-1 flex-col overflow-hidden">
        {selectedSymbol ? (
          <StockChart
            symbol={selectedSymbol}
            bars={bars}
            rangeKey={rangeKey}
            onRangeChange={setRangeKey}
            tradePlans={tradePlans}
          />
        ) : (
          <div className="flex flex-1 items-center justify-center text-xs text-[#787b86]">
            اختر رمزاً من القائمة أو ابحث عنه لعرض الشارت
          </div>
        )}
      </section>

      <aside className="flex w-96 flex-none flex-col overflow-hidden">
        <AIChat symbol={selectedSymbol} rangeKey={rangeKey} />
      </aside>
    </div>
  );
}
