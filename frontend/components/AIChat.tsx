"use client";

import React, { useEffect, useRef, useState } from "react";

interface TradePlan {
  symbol: string;
  action: string;
  order_type: string;
  entry: number;
  tp1: number;
  tp2: number;
  sl: number;
  qty: number;
  confidence: string;
  summary: string;
}

interface Message {
  id: number;
  role: string;
  content: string;
  trade_plan?: TradePlan;
  created_at?: string;
}

interface AIChatProps {
  symbol?: string;
  rangeKey?: string;
}

export default function AIChat({ symbol, rangeKey = "1M" }: AIChatProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [executingId, setExecutingId] = useState<number | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const fetchHistory = async () => {
    try {
      const url = symbol ? `/api/ai/history?symbol=${encodeURIComponent(symbol)}` : "/api/ai/history";
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        setMessages(data || []);
      }
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, [symbol]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMsg = input.trim();
    setInput("");
    const tempUserMsg: Message = { id: Date.now(), role: "user", content: userMsg };
    setMessages((prev) => [...prev, tempUserMsg]);
    setLoading(true);

    try {
      const res = await fetch("/api/ai/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMsg, symbol, range_key: rangeKey }),
      });
      if (res.ok) {
        const data = await res.json();
        const botMsg: Message = {
          id: Date.now() + 1,
          role: "assistant",
          content: data.reply,
          trade_plan: data.trade_plan,
        };
        setMessages((prev) => [...prev, botMsg]);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const executePlan = async (plan: TradePlan, msgId: number) => {
    setExecutingId(msgId);
    try {
      const res = await fetch("/api/trade-plans/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: plan.symbol || symbol,
          action: plan.action,
          order_type: plan.order_type || "market",
          qty: plan.qty || 1,
          entry: plan.entry,
          tp1: plan.tp1,
          tp2: plan.tp2,
          sl: plan.sl,
          summary: plan.summary,
        }),
      });
      if (res.ok) {
        alert("✨ تم اعتماد وتنفيذ خطة التداول بنجاح وإرسال الأوامر مع مراقبة الأهداف!");
      } else {
        const err = await res.json();
        alert(`فشل التنفيذ: ${err.detail || "خطأ غير معروف"}`);
      }
    } catch (err) {
      console.error(err);
      alert("حدث خطأ في الاتصال بالخادم أثناء التنفيذ.");
    } finally {
      setExecutingId(null);
    }
  };

  return (
    <div className="flex h-full w-full flex-col bg-[#131722] text-[#d1d4dc] border-l border-[#2a2e39]">
      {/* رأس لوحة الذكاء الاصطناعي */}
      <div className="flex h-10 flex-none items-center justify-between border-b border-[#2a2e39] bg-[#1e222d] px-3">
        <span className="text-xs font-bold text-white flex items-center space-x-1.5 space-x-reverse">
          <span>✨ مساعد Gemini الذكي</span>
          {symbol && <span className="text-blue-400">({symbol})</span>}
        </span>
        <button
          onClick={async () => {
            const url = symbol ? `/api/ai/history?symbol=${encodeURIComponent(symbol)}` : "/api/ai/history";
            await fetch(url, { method: "DELETE" });
            setMessages([]);
          }}
          className="text-[11px] text-[#787b86] hover:text-white transition"
          title="مسح المحادثة"
        >
          🧹 مسح
        </button>
      </div>

      {/* رسائل المحادثة */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {messages.length === 0 && (
          <div className="text-center text-xs text-[#787b86] mt-10">
            أهلاً بك! اسألني عن تحليل السهم أو العملة الرقمية الحالية وسيقوم Gemini بتحليل الشارت وفرض خطة تداول واضحة مع الأهداف.
          </div>
        )}

        {messages.map((m) => (
          <div
            key={m.id}
            className={`flex flex-col space-y-1 text-xs ${
              m.role === "user" ? "items-end" : "items-start"
            }`}
          >
            <div
              className={`max-w-[90%] rounded-lg p-2.5 leading-relaxed whitespace-pre-wrap ${
                m.role === "user"
                  ? "bg-[#2962ff] text-white"
                  : "bg-[#1e222d] text-[#d1d4dc] border border-[#2a2e39]"
              }`}
            >
              {m.content}
            </div>

            {/* بطاقة خطة التداول التفاعلية وأزرار التنفيذ */}
            {m.trade_plan && (
              <div className="w-full max-w-[95%] rounded-lg bg-[#1e222d] p-3 border border-amber-500/40 shadow-lg mt-1">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-bold text-amber-400 text-xs">
                    📊 خطة التداول المقترحة لـ {m.trade_plan.symbol || symbol}
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      m.trade_plan.action?.toUpperCase() === "BUY"
                        ? "bg-green-500/20 text-green-400"
                        : "bg-red-500/20 text-red-400"
                    }`}
                  >
                    {m.trade_plan.action?.toUpperCase()}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2 text-[11px] text-gray-300 bg-[#131722] p-2 rounded mb-2">
                  <div>سعر الدخول: <span className="text-white font-bold">{m.trade_plan.entry}</span></div>
                  <div>الكمية: <span className="text-white font-bold">{m.trade_plan.qty}</span></div>
                  <div>الهدف الأول (TP1): <span className="text-green-400 font-bold">{m.trade_plan.tp1}</span></div>
                  <div>الهدف الثاني (TP2): <span className="text-green-400 font-bold">{m.trade_plan.tp2}</span></div>
                  <div className="col-span-2">وقف الخسارة (SL): <span className="text-red-400 font-bold">{m.trade_plan.sl}</span></div>
                </div>

                {m.trade_plan.summary && (
                  <p className="text-[11px] text-gray-400 mb-2 italic">
                    💡 {m.trade_plan.summary}
                  </p>
                )}

                <button
                  disabled={executingId === m.id}
                  onClick={() => executePlan(m.trade_plan!, m.id)}
                  className="w-full rounded bg-gradient-to-r from-blue-600 to-indigo-600 py-1.5 text-xs font-bold text-white shadow hover:opacity-90 transition disabled:opacity-50"
                >
                  {executingId === m.id ? "⏳ جاري تنفيذ الصفقة..." : "🚀 اعتماد وتنفيذ الصفقة مع الأهداف ووقف الخسارة"}
                </button>
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="text-xs text-[#787b86] animate-pulse">
            Gemini يحلل الشارت والبيانات اللحظية...
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* صندوق الإدخال */}
      <form onSubmit={handleSend} className="flex h-12 flex-none items-center border-t border-[#2a2e39] bg-[#1e222d] px-3">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="اسأل Gemini عن تحليل الرمز أو فرصة الدخول..."
          className="flex-1 rounded bg-[#131722] px-3 py-2 text-xs text-white placeholder-[#787b86] outline-none border border-[#2a2e39] focus:border-[#2962ff]"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="mr-2 rounded bg-[#2962ff] px-4 py-2 text-xs font-bold text-white transition hover:bg-blue-600 disabled:opacity-50"
        >
          إرسال
        </button>
      </form>
    </div>
  );
}
