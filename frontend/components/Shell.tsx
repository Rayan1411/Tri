"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import React, { useState } from "react";

export default function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const currentAssetClass = searchParams.get("asset_class") || "stock";

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const switchAssetClass = (ac: string) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("asset_class", ac);
    router.push(`${pathname}?${params.toString()}`);
  };

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-[#121316] text-[#d1d4dc]">
      {/* الشريط العلوي الاحترافي المطابق لـ TradingView */}
      <header className="flex h-12 flex-none items-center justify-between border-b border-[#2a2e39] bg-[#1e222d] px-4 select-none">
        <div className="flex items-center space-x-4 space-x-reverse">
          <Link href="/" className="flex items-center space-x-2 space-x-reverse">
            <div className="flex h-7 w-7 items-center justify-center rounded bg-[#2962ff] font-bold text-white shadow">
              Tr
            </div>
            <span className="text-base font-bold tracking-wider text-white">TRIND</span>
          </Link>

          {/* مبدّل القسم: الأسهم الأمريكية vs العملات الرقمية */}
          <div className="flex rounded-md bg-[#131722] p-0.5 border border-[#2a2e39]">
            <button
              onClick={() => switchAssetClass("stock")}
              className={`rounded px-3 py-1 text-xs font-medium transition ${
                currentAssetClass === "stock"
                  ? "bg-[#2962ff] text-white shadow"
                  : "text-[#787b86] hover:text-white"
              }`}
            >
              🇺🇸 الأسهم الأمريكية
            </button>
            <button
              onClick={() => switchAssetClass("crypto")}
              className={`rounded px-3 py-1 text-xs font-medium transition ${
                currentAssetClass === "crypto"
                  ? "bg-[#f59e0b] text-white shadow"
                  : "text-[#787b86] hover:text-white"
              }`}
            >
              🪙 العملات الرقمية
            </button>
          </div>
        </div>

        {/* روابط التنقل السريع في الأعلى */}
        <div className="hidden items-center space-x-3 space-x-reverse md:flex">
          <Link
            href={`/?asset_class=${currentAssetClass}`}
            className={`px-3 py-1.5 text-xs font-medium transition rounded ${
              pathname === "/" ? "bg-[#2a2e39] text-white" : "text-[#787b86] hover:text-white"
            }`}
          >
            📊 الشارت ولوحة التداول
          </Link>
          <Link
            href="/portfolio"
            className={`px-3 py-1.5 text-xs font-medium transition rounded ${
              pathname === "/portfolio" ? "bg-[#2a2e39] text-white" : "text-[#787b86] hover:text-white"
            }`}
          >
            💼 المحفظة والصفقات
          </Link>
          <Link
            href="/alerts"
            className={`px-3 py-1.5 text-xs font-medium transition rounded ${
              pathname === "/alerts" ? "bg-[#2a2e39] text-white" : "text-[#787b86] hover:text-white"
            }`}
          >
            🔔 التنبيهات والبوت الذكي
          </Link>
        </div>

        {/* زر تسجيل الخروج */}
        <div className="flex items-center space-x-2 space-x-reverse">
          <button
            onClick={async () => {
              await fetch("/api/auth/logout", { method: "POST" });
              router.push("/login");
            }}
            className="rounded px-2.5 py-1 text-xs font-medium text-[#787b86] hover:bg-[#2a2e39] hover:text-white transition"
            title="تسجيل الخروج"
          >
            خروج 🚪
          </button>
        </div>
      </header>

      {/* المحتوى الرئيسي */}
      <main className="flex flex-1 overflow-hidden">{children}</main>
    </div>
  );
}
