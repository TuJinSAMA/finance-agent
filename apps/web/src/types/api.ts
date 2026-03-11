export interface StockBrief {
  code: string;
  name: string;
  industry: string | null;
}

// ── Recommendations ─────────────────────────────────────

export interface RecommendationRead {
  id: number;
  rec_date: string;
  stock_id: number;
  stock: StockBrief | null;
  quant_score: number | null;
  catalyst_score: number | null;
  final_score: number | null;
  rank: number | null;
  reason_short: string | null;
  reason_detail: string | null;
  price_at_rec: number | null;
  price_t1: number | null;
  price_t5: number | null;
  return_t1: number | null;
  return_t5: number | null;
  created_at: string;
}

export interface RecommendationListResponse {
  rec_date: string;
  count: number;
  recommendations: RecommendationRead[];
}

// ── Portfolio ───────────────────────────────────────────

export interface PortfolioRead {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  holdings_count: number;
}

export interface HoldingRead {
  id: number;
  stock: StockBrief | null;
  quantity: number;
  avg_cost: number;
  added_date: string;
  notes: string | null;
  current_price: number | null;
  market_value: number | null;
  profit_loss: number | null;
  profit_pct: number | null;
}

export interface PortfolioSummary {
  total_market_value: number;
  total_cost: number;
  total_profit: number;
  total_profit_pct: number | null;
}

export interface PortfolioDetailRead {
  portfolio: PortfolioRead;
  holdings: HoldingRead[];
  summary: PortfolioSummary;
}

export interface HoldingCreate {
  stock_code: string;
  quantity: number;
  avg_cost: number;
  notes?: string | null;
}

export interface HoldingUpdate {
  quantity?: number;
  avg_cost?: number;
  notes?: string | null;
}

// ── Alerts ──────────────────────────────────────────────

export interface AlertRead {
  id: number;
  stock: StockBrief | null;
  alert_type: string;
  alert_date: string;
  title: string;
  content: string | null;
  is_read: boolean;
  created_at: string;
}

// ── Notifications ───────────────────────────────────────

export interface NotificationRead {
  id: string;
  type: "recommendation" | "alert";
  title: string;
  description: string | null;
  action_url: string | null;
  is_read: boolean;
  created_at: string;
}

export interface NotificationListResponse {
  count: number;
  notifications: NotificationRead[];
}

export interface UnreadCountResponse {
  count: number;
}
