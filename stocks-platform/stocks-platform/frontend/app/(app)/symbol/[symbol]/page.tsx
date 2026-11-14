"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import AIChat from "@/components/AIChat";
import StockChart, { TIMEFRAMES } from "@/components/StockChart";
import { del, NewsItem, post, Quote } from "@/lib/api";
import { usePoll } from "@/lib/hooks";
import { dir, fmtPct, fmtPrice, fmtSigned, fmtVol, timeAgo } from "@/lib/format";

type Asset = { symbol: string; name: string; exchange: string };

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-panel2 px-3 py-2">
      <div className="text-xs text-muted">{label}</div>
      <div className="num mt-0.5 text-sm font-bold">{value}</div>
    </div>
  );
}

export default function SymbolPage() {
  const params = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(params.symbol).toUpperCase();

  const [tf, setTf] = useState("5m");
  const quote = usePoll<Quote>(`/quote/${symbol}`, 5000);
  const asset = usePoll<Asset>(`/asset/${symbol}`);
  const news = usePoll<NewsItem[]>(`/news?symbol=${symbol}`, 120000);
  const wl = usePoll<string[]>("/watchlist");
  const inWatch = wl.data?.includes(symbol) ?? false;

  const toggleWatch = async () => {
    if (inWatch) await del(`/watchlist/${symbol}`);
    else await post("/watchlist", { symbol });
    wl.reload();
  };

  // ---- price alert form
  const [aDir, setADir] = useState<"above" | "below">("above");
  const [aPrice, setAPrice] = useState("");
  const [aMsg, setAMsg] = useState("");
  const createAlert = async (e: React.FormEvent) => {
    e.preventDefault();
    const price = parseFloat(aPrice);
    if (!(price > 0)) return;
    try {
      await post("/alerts", { symbol, direction: aDir, price });
      setAPrice("");
      setAMsg("تم إنشاء التنبيه ✓");
    } catch (er) {
      setAMsg(er instanceof Error ? er.message : "تعذّر إنشاء التنبيه");
    }
    setTimeout(() => setAMsg(""), 3000);
  };

  const q = quote.data;

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-2">
        {/* header */}
        <div className="card flex flex-wrap items-end justify-between gap-4 p-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="num text-2xl font-extrabold">{symbol}</h1>
              {asset.data?.exchange && (
                <span className="rounded bg-panel2 px-2 py-0.5 text-xs text-muted">{asset.data.exchange}</span>
              )}
            </div>
            <div className="mt-1 text-sm text-muted" dir="ltr">
              {asset.data?.name}
            </div>
          </div>

          <div className="text-end">
            {quote.error && !q ? (
              <div className="down text-sm">{quote.error}</div>
            ) : (
              <>
                <div className="num text-3xl font-extrabold">{q ? fmtPrice(q.price) : "…"}</div>
                <div className={`mt-1 text-sm font-bold ${dir(q?.change)}`}>
                  <span className="num">{fmtSigned(q?.change)}</span>{" "}
                  <span className="num">({fmtPct(q?.change_pct)})</span>
                </div>
              </>
            )}
          </div>

          <button className={inWatch ? "btn" : "btn-primary"} onClick={toggleWatch} disabled={wl.loading}>
            {inWatch ? "★ في المتابعة" : "☆ أضف للمتابعة"}
          </button>
        </div>

        {/* chart */}
        <div className="card p-3">
          <div className="mb-2 flex gap-1.5">
            {TIMEFRAMES.map((t) => (
              <button
                key={t.key}
                onClick={() => setTf(t.key)}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                  tf === t.key ? "bg-brand text-white" : "bg-panel2 text-muted hover:text-ink"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          <StockChart symbol={symbol} timeframe={tf} />
        </div>

        {/* stats */}
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat label="الافتتاح" value={fmtPrice(q?.open)} />
          <Stat label="الأعلى" value={fmtPrice(q?.high)} />
          <Stat label="الأدنى" value={fmtPrice(q?.low)} />
          <Stat label="الإغلاق السابق" value={fmtPrice(q?.prev_close)} />
          <Stat label="الحجم" value={fmtVol(q?.volume)} />
          <Stat label="العرض (Bid)" value={fmtPrice(q?.bid)} />
          <Stat label="الطلب (Ask)" value={fmtPrice(q?.ask)} />
          <Stat label="آخر صفقة" value={q?.time ? new Date(q.time).toLocaleTimeString("en-US") : "—"} />
        </div>

        {/* news */}
        <div className="card overflow-hidden">
          <div className="border-b border-line px-4 py-3 font-bold">📰 أخبار {symbol}</div>
          {news.loading ? (
            <div className="p-4 text-sm text-muted">جارٍ التحميل…</div>
          ) : !news.data?.length ? (
            <div className="p-4 text-sm text-muted">{news.error ?? "لا توجد أخبار حديثة"}</div>
          ) : (
            <ul>
              {news.data.map((n) => (
                <li key={n.id} className="border-b border-line/60 last:border-0">
                  <a href={n.url} target="_blank" rel="noopener noreferrer" className="block px-4 py-3 hover:bg-panel2">
                    <div className="text-sm font-medium leading-6" dir="ltr">
                      {n.headline}
                    </div>
                    <div className="mt-1 text-xs text-muted">
                      {n.source} · {timeAgo(n.created_at)}
                    </div>
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* side column */}
      <div className="space-y-4">
        <AIChat symbol={symbol} />

        <form onSubmit={createAlert} className="card space-y-3 p-4">
          <div className="font-bold">🔔 تنبيه سعري</div>
          <div className="flex gap-2">
            <select
              className="input !w-32"
              value={aDir}
              onChange={(e) => setADir(e.target.value as "above" | "below")}
            >
              <option value="above">فوق</option>
              <option value="below">تحت</option>
            </select>
            <input
              className="input"
              type="number"
              step="any"
              min="0"
              placeholder="السعر"
              value={aPrice}
              onChange={(e) => setAPrice(e.target.value)}
              dir="ltr"
            />
          </div>
          <button className="btn-primary w-full" disabled={!aPrice}>
            إنشاء التنبيه
          </button>
          {aMsg && <p className="text-xs text-muted">{aMsg}</p>}
        </form>
      </div>
    </div>
  );
}
