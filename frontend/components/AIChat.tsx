"use client";

import { useEffect, useRef, useState } from "react";
import { api, post } from "@/lib/api";

type Msg = { role: "user" | "assistant"; content: string };

const SUGGESTIONS = ["حلّل السهم لي باختصار", "ما أبرز المخاطر الآن؟", "لخّص آخر الأخبار وأثرها"];

export default function AIChat({ symbol }: { symbol: string }) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [configured, setConfigured] = useState<boolean | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api<{ configured: boolean }>("/ai/status")
      .then((r) => setConfigured(r.configured))
      .catch(() => setConfigured(null));
  }, []);

  // a new symbol starts a new conversation
  useEffect(() => {
    setMessages([]);
    setInput("");
  }, [symbol]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, busy]);

  const send = async (text: string) => {
    const content = text.trim();
    if (!content || busy) return;
    const next: Msg[] = [...messages, { role: "user", content }];
    setMessages(next);
    setInput("");
    setBusy(true);
    try {
      const r = await post<{ reply: string; configured: boolean }>("/ai/chat", { symbol, messages: next });
      setConfigured(r.configured);
      setMessages([...next, { role: "assistant", content: r.reply }]);
    } catch (e) {
      setMessages([
        ...next,
        { role: "assistant", content: e instanceof Error ? `تعذّر الحصول على رد: ${e.message}` : "تعذّر الحصول على رد" },
      ]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card flex h-[460px] flex-col">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <div className="font-bold">🤖 محلل الذكاء الاصطناعي</div>
        <span className="num text-xs text-muted">{symbol}</span>
      </div>

      <div className="flex-1 space-y-3 overflow-auto px-4 py-3">
        {configured === false && messages.length === 0 && (
          <div className="rounded-lg border border-line bg-panel2 p-3 text-xs leading-6 text-muted">
            لم يُضبط مفتاح الذكاء الاصطناعي بعد. أضف <span className="num">ANTHROPIC_API_KEY</span> في متغيرات البيئة
            على Render وأعد التشغيل، وستعمل الدردشة مباشرة.
          </div>
        )}

        {messages.length === 0 && (
          <div className="flex flex-wrap gap-2">
            {SUGGESTIONS.map((s) => (
              <button key={s} className="btn text-xs" onClick={() => send(s)} disabled={busy}>
                {s}
              </button>
            ))}
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-start" : "justify-end"}`}>
            <div
              className={`max-w-[92%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm leading-7 ${
                m.role === "user" ? "bg-brand text-white" : "border border-line bg-panel2"
              }`}
              dir="auto"
            >
              {m.content}
            </div>
          </div>
        ))}

        {busy && (
          <div className="flex justify-end">
            <div className="rounded-2xl border border-line bg-panel2 px-3 py-2 text-sm text-muted">يحلّل…</div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form
        className="flex gap-2 border-t border-line p-3"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <input
          className="input"
          placeholder={`اسأل عن ${symbol}…`}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={busy}
          dir="auto"
        />
        <button className="btn-primary" disabled={busy || !input.trim()}>
          إرسال
        </button>
      </form>
    </div>
  );
}
