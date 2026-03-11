"use client";

import { DollarSign, Layers, TrendingUp, Wallet } from "lucide-react";
import { useTranslations } from "next-intl";
import type { PortfolioSummary as PortfolioSummaryType } from "@/types/api";

function formatCurrency(val: number) {
  const n = Number(val) || 0;
  if (Math.abs(n) >= 1e8) return `¥${(n / 1e8).toFixed(2)}亿`;
  if (Math.abs(n) >= 1e4) return `¥${(n / 1e4).toFixed(2)}万`;
  return `¥${n.toFixed(2)}`;
}

function SummaryCard({
  label,
  icon: Icon,
  children,
}: {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-white border border-cream-dark p-4 md:p-5 rounded-xl flex flex-col gap-1.5 shadow-sm">
      <div className="flex items-center gap-2">
        <Icon className="w-4 h-4 text-warm-gray" />
        <p className="text-xs font-medium text-warm-gray uppercase tracking-wider">
          {label}
        </p>
      </div>
      {children}
    </div>
  );
}

interface Props {
  summary: PortfolioSummaryType;
  holdingsCount: number;
}

export default function PortfolioSummaryCards({ summary, holdingsCount }: Props) {
  const t = useTranslations("portfolio");
  const profitIsPositive = summary.total_profit > 0;
  const profitIsNegative = summary.total_profit < 0;
  const profitColor = profitIsPositive
    ? "text-accent-red"
    : profitIsNegative
      ? "text-accent-green"
      : "text-charcoal";

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
      <SummaryCard label={t("totalMarketValue")} icon={Wallet}>
        <p className="text-xl md:text-2xl font-bold text-charcoal tabular-nums">
          {formatCurrency(summary.total_market_value)}
        </p>
      </SummaryCard>

      <SummaryCard label={t("totalCost")} icon={DollarSign}>
        <p className="text-xl md:text-2xl font-bold text-charcoal tabular-nums">
          {formatCurrency(summary.total_cost)}
        </p>
      </SummaryCard>

      <SummaryCard label={t("totalProfit")} icon={TrendingUp}>
        <p className={`text-xl md:text-2xl font-bold tabular-nums ${profitColor}`}>
          {profitIsPositive ? "+" : ""}
          {formatCurrency(summary.total_profit)}
          {summary.total_profit_pct !== null && (
            <span className="text-sm md:text-base font-medium ml-1.5">
              ({profitIsPositive ? "+" : ""}
              {(Number(summary.total_profit_pct) * 100).toFixed(2)}%)
            </span>
          )}
        </p>
      </SummaryCard>

      <SummaryCard label={t("holdingsCount")} icon={Layers}>
        <p className="text-xl md:text-2xl font-bold text-charcoal tabular-nums">
          {holdingsCount}
        </p>
      </SummaryCard>
    </div>
  );
}
