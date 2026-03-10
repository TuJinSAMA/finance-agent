"use client";

import {
  TrendingUp,
  TrendingDown,
  RefreshCw,
  ChevronRight,
} from "lucide-react";
import { useTranslations } from "next-intl";

type RiskLevel = "green" | "amber" | "red";

interface RiskItemDef {
  key: string;
  level: RiskLevel;
}

type Action = "BUY" | "SELL" | "REBALANCE";
type Confidence = "HIGH" | "MEDIUM" | "LOW";
type Status = "Pending Review" | "Scheduled" | "Executed";

interface RecommendationDef {
  stockKey: string;
  code: string;
  action: Action;
  confidence: Confidence;
  status: Status;
  faded?: boolean;
}

const riskItemDefs: RiskItemDef[] = [
  { key: "liquidityStress", level: "green" },
  { key: "varLimit", level: "green" },
  { key: "sectorConcentration", level: "green" },
  { key: "volSpikeDetection", level: "amber" },
  { key: "leverageRatio", level: "red" },
];

const recommendationDefs: RecommendationDef[] = [
  { stockKey: "moutai", code: "600519.SH", action: "BUY", confidence: "HIGH", status: "Pending Review" },
  { stockKey: "longi", code: "601012.SH", action: "SELL", confidence: "MEDIUM", status: "Pending Review" },
  { stockKey: "catl", code: "300750.SZ", action: "REBALANCE", confidence: "MEDIUM", status: "Scheduled", faded: true },
];

const riskColorMap: Record<RiskLevel, { bg: string; border: string; dot: string; text: string }> = {
  green: {
    bg: "bg-accent-green/10",
    border: "border-accent-green/20",
    dot: "bg-accent-green",
    text: "text-accent-green",
  },
  amber: {
    bg: "bg-accent-amber/10",
    border: "border-accent-amber/20",
    dot: "bg-accent-amber",
    text: "text-accent-amber",
  },
  red: {
    bg: "bg-accent-red/10",
    border: "border-accent-red/20",
    dot: "bg-accent-red",
    text: "text-accent-red",
  },
};

const actionMap: Record<Action, string> = { BUY: "buy", SELL: "sell", REBALANCE: "rebalance" };
const confidenceMap: Record<Confidence, string> = { HIGH: "high", MEDIUM: "medium", LOW: "low" };
const statusMap: Record<Status, string> = { "Pending Review": "pendingReview", Scheduled: "scheduled", Executed: "executed" };

function SnapshotCard({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="bg-white border border-cream-dark p-5 rounded-xl flex flex-col gap-1 shadow-sm">
      <p className="text-xs font-medium text-warm-gray uppercase tracking-wider">{label}</p>
      {children}
    </div>
  );
}

function RiskStatusBar() {
  const t = useTranslations("product.dashboard");

  return (
    <section className="bg-white border border-cream-dark p-4 rounded-xl shadow-sm flex items-center gap-6">
      <h3 className="text-xs font-bold text-warm-gray uppercase tracking-widest px-2 border-r border-cream-dark whitespace-nowrap">
        {t("riskStatus")}
      </h3>
      <div className="flex flex-wrap gap-3">
        {riskItemDefs.map((item) => {
          const colors = riskColorMap[item.level];
          return (
            <div
              key={item.key}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-full ${colors.bg} border ${colors.border}`}
            >
              <span className={`w-2 h-2 rounded-full ${colors.dot}`} />
              <span className={`text-xs font-semibold ${colors.text}`}>
                {t(`risk.${item.key}`)}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function ActionIcon({ action }: { action: Action }) {
  if (action === "BUY") {
    return (
      <div className="w-12 h-12 rounded-lg bg-accent-red/10 flex items-center justify-center text-accent-red">
        <TrendingUp className="w-7 h-7" />
      </div>
    );
  }
  if (action === "SELL") {
    return (
      <div className="w-12 h-12 rounded-lg bg-accent-green/10 flex items-center justify-center text-accent-green">
        <TrendingDown className="w-7 h-7" />
      </div>
    );
  }
  return (
    <div className="w-12 h-12 rounded-lg bg-slate-100 flex items-center justify-center text-slate-400">
      <RefreshCw className="w-7 h-7" />
    </div>
  );
}

function actionColor(action: Action) {
  if (action === "BUY") return "text-accent-red";
  if (action === "SELL") return "text-accent-green";
  return "text-slate-500";
}

function statusStyle(status: Status) {
  if (status === "Pending Review") return "text-accent-amber bg-accent-amber/5 border-accent-amber/20";
  if (status === "Scheduled") return "text-slate-400 bg-slate-50 border-slate-200";
  return "text-accent-green bg-accent-green/5 border-accent-green/20";
}

function RecommendationCard({ rec }: { rec: RecommendationDef }) {
  const t = useTranslations("product.dashboard");

  return (
    <div
      className={`bg-white border border-cream-dark rounded-xl p-6 shadow-sm flex items-center justify-between hover:border-accent-green/50 transition-colors cursor-pointer ${
        rec.faded ? "opacity-60 bg-white/50" : ""
      }`}
    >
      <div className="flex items-center gap-6">
        <ActionIcon action={rec.action} />
        <div>
          <div className="flex items-center gap-3">
            <h4 className="text-lg font-bold text-charcoal">
              {t(`stocks.${rec.stockKey}.name`)}
            </h4>
            <span className="text-xs font-medium text-warm-gray bg-cream px-2 py-0.5 rounded border border-cream-dark">
              {rec.code}
            </span>
          </div>
          <p className="text-sm text-warm-gray mt-1 italic">
            {t(`stocks.${rec.stockKey}.sector`)}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-12">
        <div className="text-right">
          <p className="text-xs font-medium text-warm-gray uppercase tracking-tighter">
            {t("action")}
          </p>
          <p className={`text-lg font-bold uppercase ${actionColor(rec.action)}`}>
            {t(actionMap[rec.action])}
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs font-medium text-warm-gray uppercase tracking-tighter">
            {t("confidence")}
          </p>
          <p className="text-lg font-bold text-charcoal">
            {t(confidenceMap[rec.confidence])}
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs font-medium text-warm-gray uppercase tracking-tighter">
            {t("status")}
          </p>
          <p className={`text-sm font-bold px-3 py-1 rounded-full border ${statusStyle(rec.status)}`}>
            {t(statusMap[rec.status])}
          </p>
        </div>
        <button className="w-10 h-10 rounded-full bg-cream hover:bg-cream-dark flex items-center justify-center transition-colors">
          <ChevronRight className="w-5 h-5 text-warm-gray" />
        </button>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const t = useTranslations("product.dashboard");
  const totalRecommendations = 5;
  const pendingCount = recommendationDefs.filter((r) => r.status === "Pending Review").length;

  return (
    <div className="p-8 space-y-8">
      {/* Portfolio Snapshot */}
      <section className="grid grid-cols-4 gap-4">
        <SnapshotCard label={t("totalAum")}>
          <p className="text-2xl font-bold text-charcoal tabular-nums">¥ 234.5M</p>
        </SnapshotCard>
        <SnapshotCard label={t("todaysPnL")}>
          <p className="text-2xl font-bold text-accent-red tabular-nums">
            +¥ 3.28M <span className="text-lg font-medium ml-1">(+1.42%)</span>
          </p>
        </SnapshotCard>
        <SnapshotCard label={t("netExposure")}>
          <p className="text-2xl font-bold text-charcoal tabular-nums">
            67.3% <span className="text-lg font-normal text-warm-gray">{t("netLong")}</span>
          </p>
        </SnapshotCard>
        <SnapshotCard label={t("positions")}>
          <p className="text-2xl font-bold text-charcoal tabular-nums">47</p>
        </SnapshotCard>
      </section>

      {/* Risk Status */}
      <RiskStatusBar />

      {/* Recommendations */}
      <section className="space-y-6">
        <div className="flex items-end justify-between border-b border-cream-dark pb-4">
          <h2 className="text-2xl font-semibold text-charcoal">
            {t("recommendations")}{" "}
            <span className="text-warm-gray font-normal text-lg ml-2">
              · {totalRecommendations} {t("total")} · {pendingCount} {t("pendingReviewCount")}
            </span>
          </h2>
          <button className="text-xs font-bold text-accent-green uppercase tracking-widest hover:underline">
            {t("viewAll")}
          </button>
        </div>
        <div className="grid grid-cols-1 gap-4">
          {recommendationDefs.map((rec) => (
            <RecommendationCard key={rec.code} rec={rec} />
          ))}
        </div>
      </section>

      <div className="h-12" />
    </div>
  );
}
