"use client";

import { createChart, ColorType, IChartApi, ISeriesApi } from "lightweight-charts";
import React, { useEffect, useRef, useState } from "react";

interface Bar {
  t: string;
  o: number;
  h: number;
  l: number;
  c: number;
  v?: number;
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

interface StockChartProps {
  symbol: string;
  bars: Bar[];
  rangeKey: string;
  onRangeChange: (r: string) => void;
  tradePlans?: TradePlan[];
}

export default function StockChart({
  symbol,
  bars,
  rangeKey,
  onRangeChange,
  tradePlans = [],
}: StockChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  const ranges = ["1M_TF", "5M_TF", "15M_TF", "1H_TF", "4H_TF", "1D", "1W", "1M", "3M", "6M", "1Y"];
  const rangeLabels: Record<string, string> = {
    "1M_TF": "1د",
    "5M_TF": "5د",
    "15M_TF": "15د",
    "1H_TF": "1س",
    "4H_TF": "4س",
    "1D": "يومي",
    "1W": "أسبوعي",
    "1M": "شهر",
    "3M": "3 أشهر",
    "6M": "6 أشهر",
    "1Y": "سنة",
  };

  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#131722" },
        textColor: "#d1d4dc",
      },
      grid: {
        vertLines: { color: "#1f2430" },
        horzLines: { color: "#1f2430" },
      },
      crosshair: {
        mode: 1,
      },
      timeScale: {
        borderColor: "#2a2e39",
        timeVisible: true,
      },
      rightPriceScale: {
        borderColor: "#2a2e39",
      },
    });

    chartRef.current = chart;
    const candlestickSeries = chart.addCandlestickSeries({
      upColor: "#26a69a",
      downColor: "#ef5350",
      borderVisible: false,
      wickUpColor: "#26a69a",
      wickDownColor: "#ef5350",
    });
    seriesRef.current = candlestickSeries;

    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight,
        });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, []);

  useEffect(() => {
    if (!seriesRef.current || !bars || bars.length === 0) return;

    const formatted = bars.map((b) => {
      const timeVal = Math.floor(new Date(b.t).getTime() / 1000);
      return {
        time: timeVal,
        open: Number(b.o),
        high: Number(b.h),
        low: Number(b.l),
        close: Number(b.c),
      };
    });

    formatted.sort((a, b) => (a.time as number) - (b.time as number));
    // إزالة التكرار في طوابع الزمن إن وجد
    const unique = formatted.filter(
      (item, index, arr) => index === 0 || item.time !== arr[index - 1].time
    );

    seriesRef.current.setData(unique);
    if (chartRef.current) {
      chartRef.current.timeScale().fitContent();
    }
  }, [bars]);

  return (
    <div className="flex h-full w-full flex-col bg-[#131722] select-none">
      {/* شريط الأدوات العلوي للشارت (الفواصل الزمنية والأداة) */}
      <div className="flex h-10 flex-none items-center justify-between border-b border-[#2a2e39] bg-[#1e222d] px-3">
        <div className="flex items-center space-x-1 space-x-reverse overflow-x-auto">
          <span className="text-xs font-bold text-white px-2">{symbol}</span>
          <div className="h-4 w-[1px] bg-[#2a2e39] mx-1"></div>
          {ranges.map((rk) => (
            <button
              key={rk}
              onClick={() => onRangeChange(rk)}
              className={`rounded px-2 py-1 text-xs font-medium transition ${
                rangeKey === rk
                  ? "bg-[#2962ff] text-white"
                  : "text-[#787b86] hover:bg-[#2a2e39] hover:text-white"
              }`}
            >
              {rangeLabels[rk] || rk}
            </button>
          ))}
        </div>
        <div className="text-xs text-[#787b86] hidden md:block">
          TradingView Supercharts Engine
        </div>
      </div>

      {/* منطقة رسم الشارت */}
      <div className="relative flex-1 w-full overflow-hidden">
        <div ref={chartContainerRef} className="absolute inset-0 h-full w-full" />

        {/* عرض خطوط التداول النشطة للذكاء الاصطناعي على الشارت */}
        {tradePlans.length > 0 && (
          <div className="absolute top-2 right-2 z-10 flex flex-col space-y-1 bg-[#1e222d]/90 p-2 rounded border border-[#2a2e39] text-xs">
            <span className="font-bold text-amber-400">🎯 خطط التداول النشطة:</span>
            {tradePlans.map((tp) => (
              <div key={tp.id} className="text-[11px] text-gray-300 border-t border-[#2a2e39] pt-1">
                <span className="text-blue-400 font-bold">{tp.side.toUpperCase()}</span> @ {tp.entry_price}
                {tp.tp1_price && <span className="text-green-400 mr-2">TP1: {tp.tp1_price}</span>}
                {tp.sl_price && <span className="text-red-400 mr-2">SL: {tp.sl_price}</span>}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
