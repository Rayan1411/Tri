"use client";

import { useEffect, useRef, useState } from "react";
import { ColorType, createChart } from "lightweight-charts";
import { api, Bar } from "@/lib/api";

export const TIMEFRAMES: { key: string; label: string }[] = [
  { key: "1m", label: "1د" },
  { key: "5m", label: "5د" },
  { key: "15m", label: "15د" },
  { key: "1h", label: "ساعة" },
  { key: "1d", label: "يوم" },
];

const UP = "#22c55e";
const DOWN = "#ef4444";

const NY = "America/New_York";
const fmtTime = new Intl.DateTimeFormat("en-US", { timeZone: NY, hour: "2-digit", minute: "2-digit", hour12: false });
const fmtDay = new Intl.DateTimeFormat("en-US", { timeZone: NY, month: "short", day: "numeric" });
const fmtMonth = new Intl.DateTimeFormat("en-US", { timeZone: NY, month: "short" });
const fmtYear = new Intl.DateTimeFormat("en-US", { timeZone: NY, year: "numeric" });
const fmtFull = new Intl.DateTimeFormat("en-US", {
  timeZone: NY,
  year: "numeric",
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

function useIsDark() {
  const [dark, setDark] = useState(true);
  useEffect(() => {
    const el = document.documentElement;
    const read = () => setDark(el.classList.contains("dark"));
    read();
    const mo = new MutationObserver(read);
    mo.observe(el, { attributes: true, attributeFilter: ["class"] });
    return () => mo.disconnect();
  }, []);
  return dark;
}

export default function StockChart({
  symbol,
  timeframe,
  height = 520,
}: {
  symbol: string;
  timeframe: string;
  height?: number;
}) {
  const host = useRef<HTMLDivElement>(null);
  const dark = useIsDark();
  const [status, setStatus] = useState<"loading" | "ready" | "empty" | "error">("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    const el = host.current;
    if (!el) return;

    const daily = timeframe === "1d";
    const toTime = (t: number): any => (daily ? new Date(t * 1000).toISOString().slice(0, 10) : t);

    const text = dark ? "#8793a8" : "#64708a";
    const grid = dark ? "#1b2230" : "#e8ecf3";
    const border = dark ? "#283042" : "#e0e5ee";

    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: text,
        fontFamily: "Tajawal, system-ui, sans-serif",
      },
      grid: { vertLines: { color: grid }, horzLines: { color: grid } },
      rightPriceScale: { borderColor: border },
      timeScale: {
        borderColor: border,
        timeVisible: !daily,
        secondsVisible: false,
        rightOffset: 6,
        ...(daily
          ? {}
          : {
              tickMarkFormatter: (time: any, type: number) => {
                const d = new Date(time * 1000);
                if (type === 0) return fmtYear.format(d);
                if (type === 1) return fmtMonth.format(d);
                if (type === 2) return fmtDay.format(d);
                return fmtTime.format(d);
              },
            }),
      },
      localization: daily ? {} : { timeFormatter: (time: any) => fmtFull.format(new Date(time * 1000)) },
      crosshair: { mode: 0 },
    });

    const series = chart.addCandlestickSeries({
      upColor: UP,
      downColor: DOWN,
      borderUpColor: UP,
      borderDownColor: DOWN,
      wickUpColor: UP,
      wickDownColor: DOWN,
      priceLineVisible: true,
    });

    let cancelled = false;
    let lastT = 0;
    let timer: ReturnType<typeof setInterval> | undefined;

    const toCandle = (b: Bar) => ({
      time: toTime(b.time),
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
    });

    setStatus("loading");
    setMessage("");

    (async () => {
      try {
        const bars = await api<Bar[]>(`/bars/${encodeURIComponent(symbol)}?timeframe=${timeframe}`);
        if (cancelled) return;
        if (!bars.length) {
          setStatus("empty");
          return;
        }
        series.setData(bars.map(toCandle));
        lastT = bars[bars.length - 1].time;
        // show the most recent stretch, not the entire history
        const visible = { "1m": 240, "5m": 160, "15m": 140, "1h": 120, "1d": 160 }[timeframe] ?? 160;
        const from = Math.max(0, bars.length - visible);
        chart.timeScale().setVisibleLogicalRange({ from, to: bars.length + 6 });
        setStatus("ready");

        timer = setInterval(async () => {
          if (document.visibilityState !== "visible") return;
          try {
            const recent = await api<Bar[]>(
              `/bars/${encodeURIComponent(symbol)}?timeframe=${timeframe}&recent=true`
            );
            if (cancelled) return;
            for (const b of recent) {
              if (b.time >= lastT) {
                series.update(toCandle(b));
                lastT = b.time;
              }
            }
          } catch {
            /* keep the last good candles on a transient error */
          }
        }, 10000);
      } catch (e) {
        if (cancelled) return;
        setMessage(e instanceof Error ? e.message : "تعذّر تحميل الشارت");
        setStatus("error");
      }
    })();

    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
      chart.remove();
    };
  }, [symbol, timeframe, dark]);

  return (
    <div className="relative" style={{ height }} dir="ltr">
      <div ref={host} className="absolute inset-0" />
      {status !== "ready" && (
        <div className="absolute inset-0 grid place-items-center text-sm text-muted" dir="rtl">
          {status === "loading" && "جارٍ تحميل الشارت…"}
          {status === "empty" && "لا توجد بيانات لهذا الإطار الزمني"}
          {status === "error" && <span className="down px-6 text-center">{message}</span>}
        </div>
      )}
    </div>
  );
}
