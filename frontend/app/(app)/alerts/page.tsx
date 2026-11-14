"use client";

import Link from "next/link";
import { useState } from "react";
import { AlertRow, del, post } from "@/lib/api";
import { usePoll } from "@/lib/hooks";
import { fmtDateTime, fmtPrice } from "@/lib/format";

function Row({ a, onDelete }: { a: AlertRow; onDelete: (id: number) => void }) {
  return (
    <tr className="border-b border-line/60 last:border-0 hover:bg-panel2">
      <td className="td">
        <Link href={`/symbol/${a.symbol}`} className="num font-bold">
          {a.symbol}
        </Link>
      </td>
      <td className="td">{a.direction === "above" ? "يتجاوز" : "ينزل عن"}</td>
      <td className="td">
        <span className="num">${fmtPrice(a.target_price)}</span>
      </td>
      <td className="td text-muted">
        {a.triggered_at ? (
          <>
            {fmtDateTime(a.triggered_at)}
            {a.triggered_price != null && (
              <>
                {" · "}
                <span className="num">${fmtPrice(a.triggered_price)}</span>
              </>
            )}
          </>
        ) : (
          "بانتظار التحقق"
        )}
      </td>
      <td className="td text-end">
        <button className="text-muted hover:down" onClick={() => onDelete(a.id)} aria-label="حذف">
          ✕
        </button>
      </td>
    </tr>
  );
}

export default function AlertsPage() {
  const alerts = usePoll<AlertRow[]>("/alerts", 20000);
  const [symbol, setSymbol] = useState("");
  const [direction, setDirection] = useState<"above" | "below">("above");
  const [price, setPrice] = useState("");
  const [err, setErr] = useState("");

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    try {
      await post("/alerts", { symbol: symbol.trim().toUpperCase(), direction, target_price: parseFloat(price) });
      setSymbol("");
      setPrice("");
      alerts.reload();
    } catch (er) {
      setErr(er instanceof Error ? er.message : "تعذّر إنشاء التنبيه");
    }
  };

  const remove = async (id: number) => {
    await del(`/alerts/${id}`);
    alerts.reload();
  };

  const active = (alerts.data ?? []).filter((a) => a.active);
  const done = (alerts.data ?? []).filter((a) => !a.active);

  return (
    <div className="flex-1 overflow-y-auto p-4">
    <div className="mx-auto max-w-4xl space-y-4">
      <form onSubmit={create} className="card flex flex-wrap items-end gap-3 p-4">
        <label className="space-y-1.5 text-sm">
          <span className="text-muted">الرمز</span>
          <input className="input !w-32" value={symbol} onChange={(e) => setSymbol(e.target.value)} dir="ltr" required />
        </label>
        <label className="space-y-1.5 text-sm">
          <span className="text-muted">الشرط</span>
          <select
            className="input !w-36"
            value={direction}
            onChange={(e) => setDirection(e.target.value as "above" | "below")}
          >
            <option value="above">السعر فوق</option>
            <option value="below">السعر تحت</option>
          </select>
        </label>
        <label className="space-y-1.5 text-sm">
          <span className="text-muted">السعر</span>
          <input
            className="input !w-36"
            type="number"
            step="any"
            min="0"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            dir="ltr"
            required
          />
        </label>
        <button className="btn-primary">إنشاء تنبيه</button>
        {err && <span className="down text-sm">{err}</span>}
      </form>

      <p className="text-xs leading-6 text-muted">
        يفحص الخادم الأسعار كل 30 ثانية ما دام يعمل. إن كنت على خطة Render المجانية فالخادم ينام عند الخمول، وقد يتأخر
        التنبيه حتى يستيقظ.
      </p>

      <div className="card overflow-hidden">
        <div className="border-b border-line px-4 py-3 font-bold">نشطة ({active.length})</div>
        {active.length === 0 ? (
          <div className="p-4 text-sm text-muted">لا توجد تنبيهات نشطة</div>
        ) : (
          <table className="w-full">
            <tbody>
              {active.map((a) => (
                <Row key={a.id} a={a} onDelete={remove} />
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card overflow-hidden">
        <div className="border-b border-line px-4 py-3 font-bold">تحقّقت ({done.length})</div>
        {done.length === 0 ? (
          <div className="p-4 text-sm text-muted">لا توجد تنبيهات محقّقة بعد</div>
        ) : (
          <table className="w-full">
            <tbody>
              {done.map((a) => (
                <Row key={a.id} a={a} onDelete={remove} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
    </div>
  );
}
