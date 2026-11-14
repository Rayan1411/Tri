"use client";

import Link from "next/link";
import { useState } from "react";
import { del, MoverRow, Movers, post, Quote } from "@/lib/api";
import { usePoll } from "@/lib/hooks";
import { dir, fmtPct, fmtPrice, fmtSigned, fmtVol } from "@/lib/format";

function MoversTable({ title, rows, showVolume }: { title: string; rows: MoverRow[]; showVolume?: boolean }) {
  return (
    <div className="card overflow-hidden">
      <div className="border-b border-line px-4 py-3 font-bold">{title}</div>
      {rows.length === 0 ? (
        <div className="p-4 text-sm text-muted">لا توجد بيانات حاليًا</div>
      ) : (
        <table className="w-full">
          <tbody>
            {rows.map((r) => (
              <tr key={r.symbol} className="border-b border-line/60 last:border-0 hover:bg-panel2">
                <td className="td">
                  <Link href={`/symbol/${r.symbol}`} className="num font-bold">
                    {r.symbol}
                  </Link>
                </td>
                <td className="td text-end">
                  <span className="num">{fmtPrice(r.price)}</span>
                </td>
                {showVolume && (
                  <td className="td text-end text-muted">
                    <span className="num">{fmtVol(r.volume)}</span>
                  </td>
                )}
                <td className={`td text-end ${dir(r.change_pct)}`}>
                  <span className="num">{fmtPct(r.change_pct)}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function Dashboard() {
  const wl = usePoll<string[]>("/watchlist");
  const symbols = wl.data ?? [];
  const quotes = usePoll<Record<string, Quote>>(symbols.length ? `/quotes?symbols=${symbols.join(",")}` : null, 10000);
  const movers = usePoll<Movers>("/market/movers", 30000);

  const [adding, setAdding] = useState("");
  const [err, setErr] = useState("");

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    const s = adding.trim().toUpperCase();
    if (!s) return;
    setErr("");
    try {
      await post("/watchlist", { symbol: s });
      setAdding("");
      wl.reload();
    } catch (er) {
      setErr(er instanceof Error ? er.message : "تعذّرت الإضافة");
    }
  };

  const remove = async (s: string) => {
    await del(`/watchlist/${s}`);
    wl.reload();
  };

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="card overflow-hidden lg:col-span-2">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
          <div className="font-bold">قائمة المتابعة</div>
          <form onSubmit={add} className="flex gap-2">
            <input
              className="input !w-36"
              placeholder="رمز السهم"
              value={adding}
              onChange={(e) => setAdding(e.target.value)}
              dir="ltr"
            />
            <button className="btn">إضافة</button>
          </form>
        </div>
        {err && <div className="down border-b border-line px-4 py-2 text-sm">{err}</div>}

        {wl.loading ? (
          <div className="p-6 text-sm text-muted">جارٍ التحميل…</div>
        ) : symbols.length === 0 ? (
          <div className="p-6 text-sm leading-7 text-muted">
            قائمتك فارغة. أضف رمزًا من الأعلى أو افتح أي سهم من البحث واضغط «أضف للمتابعة».
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px]">
              <thead>
                <tr className="border-b border-line">
                  <th className="th">الرمز</th>
                  <th className="th text-end">السعر</th>
                  <th className="th text-end">التغير</th>
                  <th className="th text-end">%</th>
                  <th className="th text-end">الحجم</th>
                  <th className="th" />
                </tr>
              </thead>
              <tbody>
                {symbols.map((s) => {
                  const q = quotes.data?.[s];
                  return (
                    <tr key={s} className="border-b border-line/60 last:border-0 hover:bg-panel2">
                      <td className="td">
                        <Link href={`/symbol/${s}`} className="num font-bold">
                          {s}
                        </Link>
                      </td>
                      <td className="td text-end">
                        <span className="num">{fmtPrice(q?.price)}</span>
                      </td>
                      <td className={`td text-end ${dir(q?.change)}`}>
                        <span className="num">{fmtSigned(q?.change)}</span>
                      </td>
                      <td className={`td text-end ${dir(q?.change_pct)}`}>
                        <span className="num">{fmtPct(q?.change_pct)}</span>
                      </td>
                      <td className="td text-end text-muted">
                        <span className="num">{fmtVol(q?.volume)}</span>
                      </td>
                      <td className="td text-end">
                        <button className="text-muted hover:down" onClick={() => remove(s)} aria-label="حذف">
                          ✕
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {quotes.error && <div className="down border-t border-line px-4 py-2 text-xs">{quotes.error}</div>}
      </div>

      <div className="space-y-4">
        <MoversTable title="🟢 الأكثر ارتفاعًا" rows={movers.data?.gainers ?? []} />
        <MoversTable title="🔴 الأكثر انخفاضًا" rows={movers.data?.losers ?? []} />
        <MoversTable title="🔥 الأكثر تداولًا" rows={movers.data?.actives ?? []} showVolume />
      </div>
    </div>
  );
}
