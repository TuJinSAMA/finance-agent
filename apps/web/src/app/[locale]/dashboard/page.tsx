"use client";

import { useState } from "react";
import {
  TrendingUp,
  ChevronDown,
  ChevronUp,
  Calendar,
  BarChart3,
  Zap,
  RefreshCw,
  AlertCircle,
  Loader2,
  Clock,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useApi } from "@/hooks/useApi";
import type {
  RecommendationListResponse,
  RecommendationRead,
} from "@/types/api";

function formatDate(dateStr: string) {
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "short",
  });
}

function formatReturn(val: number | null, t: ReturnType<typeof useTranslations>) {
  if (val === null || val === undefined) {
    return <span className="text-warm-gray text-sm">{t("noReturn")}</span>;
  }
  const n = Number(val);
  const pct = (n * 100).toFixed(2);
  const isPositive = n > 0;
  const color = isPositive ? "text-accent-red" : n < 0 ? "text-accent-green" : "text-charcoal";
  return (
    <span className={`font-semibold tabular-nums ${color}`}>
      {isPositive ? "+" : ""}{pct}%
    </span>
  );
}

function formatScore(val: number | null) {
  if (val === null || val === undefined) return "—";
  return (Number(val) * 100).toFixed(0);
}

function formatPrice(val: number | null) {
  if (val === null || val === undefined) return "—";
  return `¥${Number(val).toFixed(2)}`;
}

function LoadingState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-3">
      <Loader2 className="w-8 h-8 text-green animate-spin" />
      <p className="text-warm-gray text-sm">{message}</p>
    </div>
  );
}

function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  const t = useTranslations("dashboard");
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-3">
      <AlertCircle className="w-8 h-8 text-accent-red" />
      <p className="text-warm-gray text-sm">{message}</p>
      <button
        onClick={onRetry}
        className="text-sm font-medium text-green hover:text-green-dark transition-colors"
      >
        {t("retry")}
      </button>
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3">
      <BarChart3 className="w-10 h-10 text-cream-dark" />
      <p className="text-warm-gray">{message}</p>
    </div>
  );
}

function ScoreBadge({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon: React.ComponentType<{ className?: string }>;
}) {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-cream border border-cream-dark">
      <Icon className="w-3.5 h-3.5 text-warm-gray" />
      <span className="text-xs text-warm-gray">{label}</span>
      <span className="text-sm font-bold text-charcoal tabular-nums">{value}</span>
    </div>
  );
}

function RecommendationCard({ rec }: { rec: RecommendationRead }) {
  const [expanded, setExpanded] = useState(false);
  const t = useTranslations("dashboard");

  return (
    <div className="bg-white border border-cream-dark rounded-xl shadow-sm overflow-hidden transition-all">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left p-4 md:p-6 hover:bg-cream/30 transition-colors"
      >
        <div className="flex flex-col md:flex-row md:items-center gap-4">
          {/* Left: Rank + Stock info */}
          <div className="flex items-start gap-4 flex-1 min-w-0">
            <div className="w-10 h-10 md:w-12 md:h-12 rounded-lg bg-accent-green/10 flex items-center justify-center text-accent-green font-bold text-lg shrink-0">
              #{rec.rank ?? "—"}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h4 className="text-base md:text-lg font-bold text-charcoal truncate">
                  {rec.stock?.name ?? `Stock #${rec.stock_id}`}
                </h4>
                <span className="text-xs font-medium text-warm-gray bg-cream px-2 py-0.5 rounded border border-cream-dark whitespace-nowrap">
                  {rec.stock?.code ?? ""}
                </span>
              </div>
              {rec.stock?.industry && (
                <p className="text-sm text-warm-gray mt-0.5">{rec.stock.industry}</p>
              )}
              {rec.reason_short && (
                <p className="text-sm text-charcoal/80 mt-2 line-clamp-2">
                  {rec.reason_short}
                </p>
              )}
            </div>
          </div>

          {/* Right: Scores + Price + Expand toggle */}
          <div className="flex items-center gap-3 md:gap-4 flex-wrap md:flex-nowrap shrink-0">
            <div className="flex flex-wrap gap-2">
              <ScoreBadge
                label={t("score")}
                value={formatScore(rec.final_score)}
                icon={TrendingUp}
              />
              <ScoreBadge
                label={t("quantScore")}
                value={formatScore(rec.quant_score)}
                icon={BarChart3}
              />
              <ScoreBadge
                label={t("catalystScore")}
                value={formatScore(rec.catalyst_score)}
                icon={Zap}
              />
            </div>
            <div className="text-right hidden sm:block">
              <p className="text-xs text-warm-gray">{t("priceAtRec")}</p>
              <p className="text-base font-semibold text-charcoal tabular-nums">
                {formatPrice(rec.price_at_rec)}
              </p>
            </div>
            <div className="w-8 h-8 rounded-full bg-cream flex items-center justify-center shrink-0">
              {expanded ? (
                <ChevronUp className="w-4 h-4 text-warm-gray" />
              ) : (
                <ChevronDown className="w-4 h-4 text-warm-gray" />
              )}
            </div>
          </div>
        </div>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="px-4 md:px-6 pb-4 md:pb-6 border-t border-cream-dark">
          <div className="pt-4 space-y-4">
            {/* Price at rec for mobile */}
            <div className="sm:hidden flex items-center gap-4">
              <span className="text-xs text-warm-gray">{t("priceAtRec")}</span>
              <span className="text-sm font-semibold text-charcoal tabular-nums">
                {formatPrice(rec.price_at_rec)}
              </span>
            </div>

            {/* Performance tracking */}
            <div className="flex flex-wrap gap-6">
              <div>
                <span className="text-xs text-warm-gray block">{t("returnT1")}</span>
                {formatReturn(rec.return_t1, t)}
              </div>
              <div>
                <span className="text-xs text-warm-gray block">{t("returnT5")}</span>
                {formatReturn(rec.return_t5, t)}
              </div>
            </div>

            {/* Detailed reason */}
            {rec.reason_detail && (
              <div className="bg-cream/50 border border-cream-dark rounded-lg p-4">
                <p className="text-sm text-charcoal/90 whitespace-pre-wrap leading-relaxed">
                  {rec.reason_detail}
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function HistorySection({
  data,
  loading,
}: {
  data: RecommendationListResponse[] | null;
  loading: boolean;
}) {
  const t = useTranslations("dashboard");

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-8 justify-center">
        <Loader2 className="w-5 h-5 text-green animate-spin" />
        <span className="text-sm text-warm-gray">{t("loading")}</span>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="text-center py-8">
        <p className="text-warm-gray text-sm">{t("noHistory")}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {data.map((dayGroup) => (
        <div key={dayGroup.rec_date} className="bg-white border border-cream-dark rounded-xl overflow-hidden">
          <div className="px-4 md:px-6 py-3 border-b border-cream-dark bg-cream/30 flex items-center gap-2">
            <Calendar className="w-4 h-4 text-warm-gray" />
            <span className="text-sm font-medium text-charcoal">
              {formatDate(dayGroup.rec_date)}
            </span>
            <span className="text-xs text-warm-gray ml-2">
              {dayGroup.count} {t("recommendCount", { count: dayGroup.count }).replace(/\d+\s*/, "")}
            </span>
          </div>

          {/* Desktop table */}
          <div className="hidden md:block overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-warm-gray uppercase tracking-wider">
                  <th className="text-left px-6 py-3 font-medium">{t("rank")}</th>
                  <th className="text-left px-6 py-3 font-medium">{t("stockLabel")}</th>
                  <th className="text-right px-6 py-3 font-medium">{t("score")}</th>
                  <th className="text-right px-6 py-3 font-medium">{t("priceAtRec")}</th>
                  <th className="text-right px-6 py-3 font-medium">{t("returnT1")}</th>
                  <th className="text-right px-6 py-3 font-medium">{t("returnT5")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-cream-dark">
                {dayGroup.recommendations.map((rec) => (
                  <tr key={rec.id} className="hover:bg-cream/30 transition-colors">
                    <td className="px-6 py-3 font-bold text-charcoal">#{rec.rank ?? "—"}</td>
                    <td className="px-6 py-3">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-charcoal">
                          {rec.stock?.name ?? "—"}
                        </span>
                        <span className="text-xs text-warm-gray">{rec.stock?.code}</span>
                      </div>
                    </td>
                    <td className="px-6 py-3 text-right font-semibold text-charcoal tabular-nums">
                      {formatScore(rec.final_score)}
                    </td>
                    <td className="px-6 py-3 text-right tabular-nums">
                      {formatPrice(rec.price_at_rec)}
                    </td>
                    <td className="px-6 py-3 text-right">
                      {formatReturn(rec.return_t1, t)}
                    </td>
                    <td className="px-6 py-3 text-right">
                      {formatReturn(rec.return_t5, t)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <div className="md:hidden divide-y divide-cream-dark">
            {dayGroup.recommendations.map((rec) => (
              <div key={rec.id} className="p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-charcoal">#{rec.rank}</span>
                    <span className="font-medium text-charcoal">{rec.stock?.name}</span>
                    <span className="text-xs text-warm-gray">{rec.stock?.code}</span>
                  </div>
                  <span className="text-sm font-semibold tabular-nums">{formatScore(rec.final_score)}</span>
                </div>
                <div className="flex items-center gap-4 text-sm">
                  <div>
                    <span className="text-xs text-warm-gray">{t("returnT1")} </span>
                    {formatReturn(rec.return_t1, t)}
                  </div>
                  <div>
                    <span className="text-xs text-warm-gray">{t("returnT5")} </span>
                    {formatReturn(rec.return_t5, t)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function DashboardPage() {
  const t = useTranslations("dashboard");
  const today = new Date().toISOString().split("T")[0];

  const {
    data: todayData,
    loading: todayLoading,
    error: todayError,
    refetch: refetchToday,
  } = useApi<RecommendationListResponse>(
    `/api/v1/recommendations/today?rec_date=${today}`,
  );

  const {
    data: historyData,
    loading: historyLoading,
    error: historyError,
    refetch: refetchHistory,
  } = useApi<RecommendationListResponse[]>(
    "/api/v1/recommendations/history?days=7",
  );

  return (
    <div className="p-4 md:p-8 space-y-6 md:space-y-8 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <div>
          <div className="flex items-center gap-2 text-sm text-warm-gray">
            <Calendar className="w-4 h-4" />
            <span>{formatDate(today)}</span>
          </div>
        </div>
        <button
          onClick={() => {
            refetchToday();
            refetchHistory();
          }}
          className="flex items-center gap-2 text-sm font-medium text-green hover:text-green-dark transition-colors self-start sm:self-auto"
        >
          <RefreshCw className="w-4 h-4" />
          {t("retry")}
        </button>
      </div>

      {/* Today's Recommendations */}
      <section className="space-y-4">
        <div className="flex items-center gap-3">
          <TrendingUp className="w-5 h-5 text-green" />
          <h2 className="text-xl md:text-2xl font-semibold text-charcoal">
            {t("title")}
          </h2>
          {todayData && (
            <span className="text-sm text-warm-gray">
              {todayData.count} {t("recommendCount", { count: todayData.count }).replace(/\d+\s*/, "")}
            </span>
          )}
        </div>

        {todayLoading && <LoadingState message={t("loading")} />}

        {todayError && (
          <ErrorState message={t("errorLoad")} onRetry={refetchToday} />
        )}

        {!todayLoading && !todayError && todayData?.recommendations.length === 0 && (
          <EmptyState message={t("noData")} />
        )}

        {todayData && todayData.recommendations.length > 0 && (
          <div className="grid grid-cols-1 gap-4">
            {todayData.recommendations.map((rec) => (
              <RecommendationCard key={rec.id} rec={rec} />
            ))}
          </div>
        )}
      </section>

      {/* History */}
      <section className="space-y-4">
        <div className="flex items-center gap-3 border-t border-cream-dark pt-6">
          <Clock className="w-5 h-5 text-warm-gray" />
          <h2 className="text-lg md:text-xl font-semibold text-charcoal">
            {t("historyTitle")}
          </h2>
        </div>

        {historyError && (
          <ErrorState message={t("errorLoad")} onRetry={refetchHistory} />
        )}

        {!historyError && (
          <HistorySection data={historyData} loading={historyLoading} />
        )}
      </section>

      <div className="h-8" />
    </div>
  );
}
