export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    credentials: "same-origin",
    cache: "no-store",
  });

  if (res.status === 401 && typeof window !== "undefined" && !location.pathname.startsWith("/login")) {
    location.href = "/login";
    throw new ApiError(401, "انتهت الجلسة");
  }

  if (!res.ok) {
    let msg: string = res.statusText;
    try {
      const j = await res.json();
      const d = j.detail;
      msg = typeof d === "string" ? d : Array.isArray(d) ? "بيانات غير صالحة" : msg;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, msg || "حدث خطأ");
  }

  return (res.status === 204 ? undefined : await res.json()) as T;
}

export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const del = <T>(path: string) => api<T>(path, { method: "DELETE" });

// ---------------------------------------------------------------- types
export type Quote = {
  symbol: string;
  price: number | null;
  prev_close: number | null;
  change: number | null;
  change_pct: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  volume: number | null;
  bid: number | null;
  ask: number | null;
  time: string | null;
};

export type Bar = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type NewsItem = {
  id: number;
  headline: string;
  summary: string;
  source: string;
  url: string;
  created_at: string;
  symbols: string[];
};

export type MoverRow = {
  symbol: string;
  price: number | null;
  change: number | null;
  change_pct: number | null;
  volume?: number | null;
};

export type Movers = { gainers: MoverRow[]; losers: MoverRow[]; actives: MoverRow[] };

export type AlertRow = {
  id: number;
  symbol: string;
  direction: "above" | "below";
  target_price: number;
  active: boolean;
  triggered_at: string | null;
  triggered_price: number | null;
  created_at: string;
};

export type Account = {
  equity: number | null;
  last_equity: number | null;
  cash: number | null;
  buying_power: number | null;
  portfolio_value: number | null;
  status: string;
  paper: boolean;
};

export type Position = {
  symbol: string;
  ui_symbol?: string;
  side: string;
  qty: number;
  avg_entry_price: number;
  current_price: number;
  market_value: number;
  unrealized_pl: number;
  unrealized_plpc: number;
};

export type OrderRow = {
  id: string;
  symbol: string;
  side: string;
  type: string;
  qty: string | null;
  filled_qty: string | null;
  status: string;
  limit_price: string | null;
  filled_avg_price: string | null;
  submitted_at: string | null;
};

export type PortfolioResponse = {
  account: Account;
  positions: Position[];
  orders: OrderRow[];
};

export type SearchHit = { symbol: string; name: string; exchange: string };
