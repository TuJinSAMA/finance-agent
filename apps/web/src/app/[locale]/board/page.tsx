"use client";

import { AlertCircle, ArrowRight, Loader2, LogIn } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useApi } from "@/hooks/useApi";
import type { MarketMetric, PublicMarketBoardResponse } from "@/types/api";
import { Link } from "../../../../navigation";

type BoardCopy = {
  eyebrow: string;
  asOf: string;
  source: string;
  sections: {
    macro: string;
    assets: string;
    custom: string;
  };
  marketState: {
    riskOn: string;
    riskOff: string;
    neutral: string;
    dataIncomplete: string;
  };
  summary: {
    riskOn: string;
    riskOff: string;
    neutral: string;
    dataIncomplete: string;
    availability: (macroAvailable: number, macroTotal: number, assetsAvailable: number, assetsTotal: number) => string;
  };
  status: Record<MarketMetric["status"], string>;
  unavailable: string;
  noChange: string;
  loginEyebrow: string;
  loginTitle: string;
  loginBody: string;
  loginCta: string;
};

const EN_COPY: BoardCopy = {
  eyebrow: "Public market board",
  asOf: "As of",
  source: "Source",
  sections: {
    macro: "Macro",
    assets: "Assets",
    custom: "China & FX",
  },
  marketState: {
    riskOn: "Risk-On",
    riskOff: "Risk-Off",
    neutral: "Neutral",
    dataIncomplete: "Data Incomplete",
  },
  summary: {
    riskOn: "Risk appetite is improving across core signals.",
    riskOff: "Defensive positioning is leading across core signals.",
    neutral: "Core signals are mixed and do not point to a strong regime shift.",
    dataIncomplete: "Some core signals are missing, so the market read is provisional.",
    availability: (macroAvailable, macroTotal, assetsAvailable, assetsTotal) =>
      `Coverage: macro ${macroAvailable}/${macroTotal}, assets ${assetsAvailable}/${assetsTotal}.`,
  },
  status: {
    ok: "Live",
    unavailable: "Unavailable",
    stale: "Stale",
  },
  unavailable: "Unavailable",
  noChange: "No daily change",
  loginEyebrow: "Personalization",
  loginTitle: "Want recommendations tailored to your portfolio?",
  loginBody:
    "This board stays public. Sign in to continue into the recommendations workspace and personalized context.",
  loginCta: "Go to recommendations",
};

const ZH_COPY: BoardCopy = {
  eyebrow: "公开市场看板",
  asOf: "更新时间",
  source: "数据源",
  sections: {
    macro: "宏观",
    assets: "资产",
    custom: "中国与汇率",
  },
  marketState: {
    riskOn: "偏风险",
    riskOff: "偏避险",
    neutral: "中性",
    dataIncomplete: "数据不足",
  },
  summary: {
    riskOn: "核心信号整体偏积极，市场风险偏好有所抬升。",
    riskOff: "核心信号整体偏谨慎，防御情绪正在占优。",
    neutral: "核心信号相互分化，暂未显示出明确的风格切换。",
    dataIncomplete: "部分核心信号缺失，因此当前判断仅供参考。",
    availability: (macroAvailable, macroTotal, assetsAvailable, assetsTotal) =>
      `当前可用数据：宏观 ${macroAvailable}/${macroTotal}，资产 ${assetsAvailable}/${assetsTotal}。`,
  },
  status: {
    ok: "正常",
    unavailable: "不可用",
    stale: "缓存",
  },
  unavailable: "暂无数据",
  noChange: "暂无日内变化",
  loginEyebrow: "个性化",
  loginTitle: "想看更贴合你组合的推荐？",
  loginBody:
    "这个市场看板对所有人开放。登录后可进入推荐工作台，查看个性化建议与组合上下文。",
  loginCta: "前往推荐页",
};

function getCopy(locale: string): BoardCopy {
  return locale.startsWith("zh") ? ZH_COPY : EN_COPY;
}

function getMarketStateKey(label: string): keyof BoardCopy["marketState"] {
  switch (label) {
    case "Risk-On 偏风险":
      return "riskOn";
    case "Risk-Off 偏避险":
      return "riskOff";
    case "Data Incomplete 数据不足":
      return "dataIncomplete";
    default:
      return "neutral";
  }
}

function getLocalizedMarketState(
  label: string,
  copy: BoardCopy,
): {
  title: string;
  summary: string;
} {
  const stateKey = getMarketStateKey(label);

  return {
    title: copy.marketState[stateKey],
    summary: copy.summary[stateKey],
  };
}

function getAvailabilitySummary(data: PublicMarketBoardResponse, copy: BoardCopy): string {
  const macroAvailable = data.macro.filter((metric) => metric.status === "ok").length;
  const assetsAvailable = data.assets.filter((metric) => metric.status === "ok").length;

  return copy.summary.availability(
    macroAvailable,
    data.macro.length,
    assetsAvailable,
    data.assets.length,
  );
}

function formatBoardDate(locale: string, value: string): string {
  const parsed = new Date(`${value}T00:00:00`);

  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "short",
  }).format(parsed);
}

function formatAsOf(locale: string, value: string): string {
  const parsed = new Date(value);

  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

function formatMetricChange(change: number): string {
  const prefix = change > 0 ? "+" : "";

  return `${prefix}${change.toFixed(2)}%`;
}

function getChangeTone(change: number): string {
  if (change > 0) return "text-accent-red";
  if (change < 0) return "text-accent-green";

  return "text-warm-gray";
}

function getStatusTone(status: MarketMetric["status"]): string {
  if (status === "ok") {
    return "bg-dark-green/10 text-dark-green border-dark-green/15";
  }
  if (status === "stale") {
    return "bg-gold/10 text-ochre border-gold/20";
  }

  return "bg-cream text-warm-gray border-divider";
}

function MetricCard({
  metric,
  copy,
}: Readonly<{
  metric: MarketMetric;
  copy: BoardCopy;
}>): React.JSX.Element {
  const value = metric.display ?? (metric.value !== null ? `${metric.value}` : copy.unavailable);

  return (
    <article
      className={`rounded-xl border p-4 transition-colors ${
        metric.status === "unavailable"
          ? "border-divider bg-cream/60"
          : "border-divider bg-white"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-warm-gray">
            {metric.name}
          </p>
          <p className="mt-1 text-[11px] font-mono text-warm-gray/80">{metric.symbol}</p>
        </div>
        <span
          className={`shrink-0 rounded-full border px-2 py-1 text-[11px] font-medium ${getStatusTone(metric.status)}`}
        >
          {copy.status[metric.status]}
        </span>
      </div>

      <p
        className={`mt-4 text-2xl font-semibold tracking-tight tabular-nums ${
          metric.status === "unavailable" ? "text-warm-gray" : "text-ink"
        }`}
      >
        {value}
      </p>

      {metric.change_pct !== null ? (
        <p className={`mt-2 text-sm font-medium tabular-nums ${getChangeTone(metric.change_pct)}`}>
          {formatMetricChange(metric.change_pct)}
        </p>
      ) : metric.status === "unavailable" ? (
        <p className="mt-2 text-sm text-warm-gray">{copy.unavailable}</p>
      ) : (
        <p className="mt-2 text-sm text-warm-gray">{copy.noChange}</p>
      )}
    </article>
  );
}

function MetricSection({
  title,
  metrics,
  copy,
}: Readonly<{
  title: string;
  metrics: MarketMetric[];
  copy: BoardCopy;
}>): React.JSX.Element {
  return (
    <section className="rounded-2xl border border-divider bg-white p-5 shadow-sm md:p-6">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-lg font-serif font-medium text-ink">{title}</h2>
        <span className="text-xs uppercase tracking-[0.16em] text-warm-gray">
          {metrics.length}
        </span>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {metrics.map((metric) => (
          <MetricCard
            key={`${title}-${metric.symbol}`}
            metric={metric}
            copy={copy}
          />
        ))}
      </div>
    </section>
  );
}

function LoadingState({ message }: Readonly<{ message: string }>): React.JSX.Element {
  return (
    <div className="rounded-2xl border border-divider bg-white px-6 py-16 shadow-sm">
      <div className="flex flex-col items-center justify-center gap-3">
        <Loader2 className="h-8 w-8 animate-spin text-terracotta" />
        <p className="text-sm text-warm-gray">{message}</p>
      </div>
    </div>
  );
}

function ErrorState({
  message,
  onRetry,
  retryLabel,
}: Readonly<{
  message: string;
  onRetry: () => void;
  retryLabel: string;
}>): React.JSX.Element {
  return (
    <div className="rounded-2xl border border-divider bg-white px-6 py-16 shadow-sm">
      <div className="flex flex-col items-center justify-center gap-4">
        <AlertCircle className="h-8 w-8 text-accent-red" />
        <p className="text-sm text-warm-gray">{message}</p>
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-2 rounded-xl bg-terracotta px-4 py-2 text-sm font-medium text-white transition-all duration-200 hover:-translate-y-0.5 hover:bg-terracotta-dark hover:shadow-lg"
        >
          {retryLabel}
        </button>
      </div>
    </div>
  );
}

export default function BoardPage(): React.JSX.Element {
  const locale = useLocale();
  const dashboardT = useTranslations("dashboard");
  const copy = getCopy(locale);
  const { data, loading, error, refetch } = useApi<PublicMarketBoardResponse>(
    "/api/v1/public/market-board",
  );
  const marketState = data ? getLocalizedMarketState(data.market_state.label, copy) : null;
  const availabilitySummary = data ? getAvailabilitySummary(data, copy) : null;

  return (
    <main className="min-h-screen bg-cream px-4 py-8 md:px-8 md:py-10">
      <div className="mx-auto max-w-6xl space-y-5">
        {loading ? (
          <LoadingState message={dashboardT("loading")} />
        ) : error || !data ? (
          <ErrorState
            message={dashboardT("errorLoad")}
            onRetry={refetch}
            retryLabel={dashboardT("retry")}
          />
        ) : (
          <>
            <header className="rounded-2xl border border-divider bg-white p-6 shadow-sm">
              <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                <div className="max-w-3xl">
                  <p className="text-xs font-medium uppercase tracking-[0.24em] text-warm-gray">
                    {copy.eyebrow}
                  </p>
                  <p className="mt-3 text-sm text-warm-gray">
                    {formatBoardDate(locale, data.market_state.date)}
                  </p>
                  <h1 className="mt-1 text-3xl font-serif font-medium tracking-tight text-ink md:text-4xl">
                    {marketState?.title}
                  </h1>
                  <p className="mt-3 max-w-2xl text-sm leading-relaxed text-charcoal/80 md:text-base">
                    {marketState?.summary}
                  </p>
                  <p className="mt-2 max-w-2xl text-sm leading-relaxed text-charcoal/70">
                    {availabilitySummary}
                  </p>
                </div>

                <div className="rounded-xl border border-divider bg-cream/60 p-4 lg:min-w-72">
                  <p className="text-xs uppercase tracking-[0.16em] text-warm-gray">
                    {copy.asOf}
                  </p>
                  <p className="mt-1 text-sm font-medium text-charcoal">
                    {formatAsOf(locale, data.as_of)}
                  </p>
                  <p className="mt-4 text-xs uppercase tracking-[0.16em] text-warm-gray">
                    {copy.source}
                  </p>
                  <p className="mt-1 text-sm font-medium text-charcoal">{data.source}</p>
                </div>
              </div>
            </header>

            <MetricSection title={copy.sections.macro} metrics={data.macro} copy={copy} />
            <MetricSection title={copy.sections.assets} metrics={data.assets} copy={copy} />
            <MetricSection title={copy.sections.custom} metrics={data.custom} copy={copy} />

            <section className="rounded-2xl border border-divider bg-white p-6 shadow-sm">
              <div className="flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
                <div className="max-w-2xl">
                  <p className="text-xs font-medium uppercase tracking-[0.24em] text-warm-gray">
                    {copy.loginEyebrow}
                  </p>
                  <h2 className="mt-2 text-2xl font-serif font-medium text-ink">
                    {copy.loginTitle}
                  </h2>
                  <p className="mt-2 text-sm leading-relaxed text-charcoal/80">
                    {copy.loginBody}
                  </p>
                </div>

                <Link
                  href="/recommendations"
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-terracotta px-5 py-3 text-sm font-medium text-white transition-all duration-200 hover:-translate-y-0.5 hover:bg-terracotta-dark hover:shadow-lg"
                >
                  <LogIn className="h-4 w-4" />
                  <span>{copy.loginCta}</span>
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </div>
            </section>
          </>
        )}
      </div>
    </main>
  );
}
