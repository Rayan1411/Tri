"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import SearchBox from "./SearchBox";
import { AlertRow, post } from "@/lib/api";
import { usePoll } from "@/lib/hooks";
import { fmtPrice } from "@/lib/format";

const NAV = [
  { href: "/", label: "لوحة التحكم" },
  { href: "/portfolio", label: "المحفظة" },
  { href: "/alerts", label: "التنبيهات" },
];

type Clock = { is_open: boolean | null };

export default function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const clock = usePoll<Clock>("/market/clock", 60000);
  const alerts = usePoll<AlertRow[]>("/alerts", 30000);

  // ---- theme
  const [dark, setDark] = useState(true);
  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
  }, []);
  const toggleTheme = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("theme", next ? "dark" : "light");
    } catch {
      /* ignore */
    }
  };

  // ---- triggered-alert toasts
  const [toasts, setToasts] = useState<AlertRow[]>([]);
  useEffect(() => {
    if (!alerts.data) return;
    let seen: number[] = [];
    try {
      seen = JSON.parse(localStorage.getItem("seenAlerts") || "[]");
    } catch {
      /* ignore */
    }
    const fresh = alerts.data.filter((a) => a.triggered_at && !seen.includes(a.id));
    if (fresh.length) {
      setToasts((t) => [...t, ...fresh.filter((f) => !t.some((x) => x.id === f.id))]);
      try {
        localStorage.setItem("seenAlerts", JSON.stringify([...seen, ...fresh.map((a) => a.id)].slice(-200)));
      } catch {
        /* ignore */
      }
    }
  }, [alerts.data]);

  const logout = useCallback(async () => {
    try {
      await post("/auth/logout");
    } finally {
      router.push("/login");
      router.refresh();
    }
  }, [router]);

  const isOpen = clock.data?.is_open;

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 border-b border-line bg-panel/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1500px] flex-wrap items-center gap-3 px-4 py-2.5">
          <Link href="/" className="flex items-center gap-2 text-lg font-extrabold">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand text-white">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
                <path d="M3 17l6-6 4 4 8-8" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M15 7h6v6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            منصة الأسهم
          </Link>

          <nav className="flex items-center gap-1">
            {NAV.map((n) => {
              const active = n.href === "/" ? pathname === "/" : pathname.startsWith(n.href);
              return (
                <Link
                  key={n.href}
                  href={n.href}
                  className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                    active ? "bg-brand/15 text-brand" : "text-muted hover:text-ink"
                  }`}
                >
                  {n.label}
                </Link>
              );
            })}
          </nav>

          <div className="order-last w-full md:order-none md:flex-1 md:px-4">
            <SearchBox />
          </div>

          <div className="ms-auto flex items-center gap-2">
            {isOpen !== undefined && isOpen !== null && (
              <span
                className={`hidden items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-xs sm:flex ${
                  isOpen ? "up" : "text-muted"
                }`}
              >
                <span className={`h-2 w-2 rounded-full ${isOpen ? "bg-up" : "bg-muted"}`} />
                {isOpen ? "السوق مفتوح" : "السوق مغلق"}
              </span>
            )}
            <button className="btn" onClick={toggleTheme} aria-label="تبديل الوضع">
              {dark ? "☀️ فاتح" : "🌙 داكن"}
            </button>
            <button className="btn" onClick={logout}>
              خروج
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1500px] px-4 py-4">{children}</main>

      <div className="fixed bottom-4 start-4 z-50 flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2">
        {toasts.map((a) => (
          <div key={a.id} className="card border-brand/60 p-3 shadow-xl">
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="text-sm font-bold">🔔 تنبيه سعري</div>
                <Link href={`/symbol/${a.symbol}`} className="mt-1 block text-sm">
                  <span className="num font-bold">{a.symbol}</span>{" "}
                  {a.direction === "above" ? "تجاوز" : "نزل عن"}{" "}
                  <span className="num">${fmtPrice(a.price)}</span>
                  {a.triggered_price != null && (
                    <>
                      {" "}
                      (الآن <span className="num">${fmtPrice(a.triggered_price)}</span>)
                    </>
                  )}
                </Link>
              </div>
              <button
                className="text-muted hover:text-ink"
                onClick={() => setToasts((t) => t.filter((x) => x.id !== a.id))}
                aria-label="إغلاق"
              >
                ✕
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
