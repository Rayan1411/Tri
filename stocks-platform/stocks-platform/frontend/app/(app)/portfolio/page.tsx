"use client";

import Link from "next/link";
import { useState } from "react";
import { Account, del, OrderRow, Position, post } from "@/lib/api";
import { usePoll } from "@/lib/hooks";
import { dir, fmtDateTime, fmtMoney, fmtPct, fmtPrice, fmtSigned } from "@/lib/format";

const STATUS_AR: Record<string, string> = {
  new: "جديد",
  accepted: "مقبول",
  pending_new: "قيد الإرسال",
  partially_filled: "منفّذ جزئيًا",
  filled: "منفّذ",
  canceled: "ملغي",
  expired: "منتهي",
  rejected: "مرفوض",
  pending_cancel: "قيد الإلغاء",
};
const OPEN = new Set(["new", "accepted", "pending_new", "partially_filled", "pending_cancel"]);

function Card({ label, value, cls = "" }: { label: string; value: string; cls?: string }) {
  return (
    <div className="card p-4">
      <div className="text-xs text-muted">{label}</div>
      <div className={`num mt-1 text-xl font-extrabold ${cls}`}>{value}</div>
    </div>
  );
}

export default function PortfolioPage() {
  const account = usePoll<Account>("/trade/account", 15000);
  const positions = usePoll<Position[]>("/trade/positions", 15000);
  const orders = usePoll<OrderRow[]>("/trade/orders", 15000);

  const [symbol, setSymbol] = useState("");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [type, setType] = useState<"market" | "limit">("market");
  const [qty, setQty] = useState("");
  const [limit, setLimit] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = () => {
    account.reload();
    positions.reload();
    orders.reload();
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const s = symbol.trim().toUpperCase();
    const label = `${side === "buy" ? "شراء" : "بيع"} ${qty} × ${s} (${type === "market" ? "سوقي" : "محدد @ " + limit})`;
    if (!window.confirm(`تأكيد الأمر؟\n${label}`)) return;
    setBusy(true);
    setMsg(null);
    try {
      await post("/trade/orders", {
        symbol: s,
        qty: parseFloat(qty),
        side,
        type,
        limit_price: type === "limit" ? parseFloat(limit) : undefined,
      });
      setMsg({ ok: true, text: "تم إرسال الأمر ✓" });
      setQty("");
      setTimeout(refresh, 800);
    } catch (er) {
      setMsg({ ok: false, text: er instanceof Error ? er.message : "تعذّر إرسال الأمر" });
    } finally {
      setBusy(false);
    }
  };

  const cancel = async (id: string) => {
    try {
      await del(`/trade/orders/${id}`);
      setTimeout(refresh, 500);
    } catch (er) {
      setMsg({ ok: false, text: er instanceof Error ? er.message : "تعذّر الإلغاء" });
    }
  };

  const closePos = async (s: string) => {
    if (!window.confirm(`إغلاق مركز ${s} بالكامل؟`)) return;
    try {
      await post(`/trade/positions/${s}/close`);
      setTimeout(refresh, 800);
    } catch (er) {
      setMsg({ ok: false, text: er instanceof Error ? er.message : "تعذّر الإغلاق" });
    }
  };

  const a = account.data;
  const dayPl = a && a.equity != null && a.last_equity != null ? a.equity - a.last_equity : null;

  if (account.error && !a) {
    return (
      <div className="card mx-auto max-w-xl p-6 text-sm leading-7">
        <div className="down mb-2 font-bold">تعذّر الاتصال بحساب Alpaca</div>
        <div className="text-muted">{account.error}</div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-extrabold">المحفظة</h1>
        {a && (
          <span
            className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${
              a.paper ? "bg-brand/15 text-brand" : "bg-down/15 down"
            }`}
          >
            {a.paper ? "حساب تجريبي (Paper)" : "حساب حقيقي ⚠️"}
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Card label="قيمة المحفظة" value={fmtMoney(a?.equity)} />
        <Card label="الربح/الخسارة اليوم" value={dayPl == null ? "—" : fmtSigned(dayPl)} cls={dir(dayPl)} />
        <Card label="السيولة النقدية" value={fmtMoney(a?.cash)} />
        <Card label="القوة الشرائية" value={fmtMoney(a?.buying_power)} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <div className="card overflow-hidden">
            <div className="border-b border-line px-4 py-3 font-bold">المراكز المفتوحة</div>
            {!positions.data?.length ? (
              <div className="p-4 text-sm text-muted">{positions.loading ? "جارٍ التحميل…" : "لا توجد مراكز مفتوحة"}</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px]">
                  <thead>
                    <tr className="border-b border-line">
                      <th className="th">الرمز</th>
                      <th className="th text-end">الكمية</th>
                      <th className="th text-end">متوسط الدخول</th>
                      <th className="th text-end">السعر</th>
                      <th className="th text-end">القيمة</th>
                      <th className="th text-end">الربح/الخسارة</th>
                      <th className="th" />
                    </tr>
                  </thead>
                  <tbody>
                    {positions.data.map((p) => (
                      <tr key={p.symbol} className="border-b border-line/60 last:border-0 hover:bg-panel2">
                        <td className="td">
                          <Link href={`/symbol/${p.symbol}`} className="num font-bold">
                            {p.symbol}
                          </Link>
                        </td>
                        <td className="td text-end">
                          <span className="num">{p.qty}</span>
                        </td>
                        <td className="td text-end">
                          <span className="num">{fmtPrice(p.avg_entry_price)}</span>
                        </td>
                        <td className="td text-end">
                          <span className="num">{fmtPrice(p.current_price)}</span>
                        </td>
                        <td className="td text-end">
                          <span className="num">{fmtMoney(p.market_value)}</span>
                        </td>
                        <td className={`td text-end ${dir(p.unrealized_pl)}`}>
                          <span className="num">{fmtSigned(p.unrealized_pl)}</span>{" "}
                          <span className="num text-xs">({fmtPct(p.unrealized_plpc * 100)})</span>
                        </td>
                        <td className="td text-end">
                          <button className="btn !px-2 !py-1 text-xs" onClick={() => closePos(p.symbol)}>
                            إغلاق
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="card overflow-hidden">
            <div className="border-b border-line px-4 py-3 font-bold">آخر الأوامر</div>
            {!orders.data?.length ? (
              <div className="p-4 text-sm text-muted">{orders.loading ? "جارٍ التحميل…" : "لا توجد أوامر"}</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px]">
                  <thead>
                    <tr className="border-b border-line">
                      <th className="th">الرمز</th>
                      <th className="th">الجهة</th>
                      <th className="th">النوع</th>
                      <th className="th text-end">الكمية</th>
                      <th className="th text-end">السعر</th>
                      <th className="th">الحالة</th>
                      <th className="th">الوقت</th>
                      <th className="th" />
                    </tr>
                  </thead>
                  <tbody>
                    {orders.data.map((o) => (
                      <tr key={o.id} className="border-b border-line/60 last:border-0 hover:bg-panel2">
                        <td className="td">
                          <span className="num font-bold">{o.symbol}</span>
                        </td>
                        <td className={`td ${o.side === "buy" ? "up" : "down"}`}>{o.side === "buy" ? "شراء" : "بيع"}</td>
                        <td className="td">{o.type === "market" ? "سوقي" : "محدد"}</td>
                        <td className="td text-end">
                          <span className="num">
                            {o.filled_qty ?? 0}/{o.qty}
                          </span>
                        </td>
                        <td className="td text-end">
                          <span className="num">{fmtPrice(parseFloat(o.filled_avg_price ?? o.limit_price ?? "NaN"))}</span>
                        </td>
                        <td className="td">{STATUS_AR[o.status] ?? o.status}</td>
                        <td className="td text-xs text-muted">{fmtDateTime(o.submitted_at)}</td>
                        <td className="td text-end">
                          {OPEN.has(o.status) && (
                            <button className="text-muted hover:down" onClick={() => cancel(o.id)}>
                              إلغاء
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        <form onSubmit={submit} className="card h-fit space-y-3 p-4">
          <div className="font-bold">أمر جديد</div>

          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setSide("buy")}
              className={`rounded-lg py-2 text-sm font-bold ${side === "buy" ? "bg-up text-white" : "bg-panel2 text-muted"}`}
            >
              شراء
            </button>
            <button
              type="button"
              onClick={() => setSide("sell")}
              className={`rounded-lg py-2 text-sm font-bold ${side === "sell" ? "bg-down text-white" : "bg-panel2 text-muted"}`}
            >
              بيع
            </button>
          </div>

          <label className="block space-y-1.5 text-sm">
            <span className="text-muted">الرمز</span>
            <input className="input" value={symbol} onChange={(e) => setSymbol(e.target.value)} dir="ltr" required />
          </label>

          <div className="grid grid-cols-2 gap-2">
            <label className="block space-y-1.5 text-sm">
              <span className="text-muted">الكمية</span>
              <input
                className="input"
                type="number"
                step="any"
                min="0"
                value={qty}
                onChange={(e) => setQty(e.target.value)}
                dir="ltr"
                required
              />
            </label>
            <label className="block space-y-1.5 text-sm">
              <span className="text-muted">النوع</span>
              <select className="input" value={type} onChange={(e) => setType(e.target.value as "market" | "limit")}>
                <option value="market">سوقي</option>
                <option value="limit">محدد</option>
              </select>
            </label>
          </div>

          {type === "limit" && (
            <label className="block space-y-1.5 text-sm">
              <span className="text-muted">سعر الحد</span>
              <input
                className="input"
                type="number"
                step="any"
                min="0"
                value={limit}
                onChange={(e) => setLimit(e.target.value)}
                dir="ltr"
                required
              />
            </label>
          )}

          <button className="btn-primary w-full" disabled={busy}>
            {busy ? "جارٍ الإرسال…" : "إرسال الأمر"}
          </button>
          {msg && <p className={`text-sm ${msg.ok ? "up" : "down"}`}>{msg.text}</p>}
          <p className="text-xs leading-6 text-muted">الأوامر صالحة ليوم التداول فقط (Day).</p>
        </form>
      </div>
    </div>
  );
}
