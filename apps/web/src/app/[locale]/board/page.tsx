"use client";

import { AlertCircle, ArrowRight, Loader2, LogIn } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useApi } from "@/hooks/useApi";
import type { MarketGroupSnapshotResponse, MarketMetric } from "@/types/api";
import { Link } from "../../../../navigation";

type BoardCopy = {
  eyebrow: string;
  title: string;
  summary: string;
  asOf: string;
  lastSuccess: string;
  source: string;
  sections: {
    macro: string;
    assets: string;
  };
  availability: (macroAvailable: number, macroTotal: number, assetsAvailable: number, assetsTotal: number) => string;
  partialAvailability: (section: string, available: number, total: number) => string;
  status: Record<MarketMetric["status"], string>;
  groupStatus: Record<MarketGroupSnapshotResponse["status"], string>;
  unavailable: string;
  noChange: string;
  loginEyebrow: string;
  loginTitle: string;
  loginBody: string;
  loginCta: string;
};

const EN_COPY: BoardCopy = {
  eyebrow: "Public market board",
  title: "Macro and asset snapshots",
  summary: "A quick read on broad market inputs from the public data feed.",
  asOf: "As of",
  lastSuccess: "Last successful refresh",
  source: "Source",
  sections: {
    macro: "Macro",
    assets: "Assets",
  },
  availability: (macroAvailable, macroTotal, assetsAvailable, assetsTotal) =>
    `Coverage: macro ${macroAvailable}/${macroTotal}, assets ${assetsAvailable}/${assetsTotal}.`,
  partialAvailability: (section, available, total) =>
    `Coverage: ${section.toLowerCase()} ${available}/${total}.`,
  status: {
    ok: "Live",
    unavailable: "Unavailable",
    stale: "Stale",
  },
  groupStatus: {
    ok: "Ready",
    stale: "Stale",
    empty: "Empty",
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
  title: "宏观与资产快照",
  summary: "来自公开数据源的宏观与跨资产市场快照。",
  asOf: "更新时间",
  lastSuccess: "最近成功刷新",
  source: "数据源",
  sections: {
    macro: "宏观",
    assets: "资产",
  },
  availability: (macroAvailable, macroTotal, assetsAvailable, assetsTotal) =>
    `当前可用数据：宏观 ${macroAvailable}/${macroTotal}，资产 ${assetsAvailable}/${assetsTotal}。`,
  partialAvailability: (section, available, total) =>
    `当前可用数据：${section} ${available}/${total}。`,
  status: {
    ok: "正常",
    unavailable: "不可用",
    stale: "缓存",
  },
  groupStatus: {
    ok: "可用",
    stale: "过期",
    empty: "空快照",
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

function countAvailableMetrics(snapshot: MarketGroupSnapshotResponse): number {
  return snapshot.items.filter((metric) => metric.status === "ok").length;
}

function getAvailabilitySummary(
  snapshots: {
    macro: MarketGroupSnapshotResponse | null;
    assets: MarketGroupSnapshotResponse | null;
  },
  copy: BoardCopy,
): string | null {
  const macro = snapshots.macro;
  const assets = snapshots.assets;

  if (macro && assets) {
    return copy.availability(
      countAvailableMetrics(macro),
      macro.items.length,
      countAvailableMetrics(assets),
      assets.items.length,
    );
  }

  if (macro) {
    return copy.partialAvailability(
      copy.sections.macro,
      countAvailableMetrics(macro),
      macro.items.length,
    );
  }

  if (assets) {
    return copy.partialAvailability(
      copy.sections.assets,
      countAvailableMetrics(assets),
      assets.items.length,
    );
  }

  return null;
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

function getGroupStatusTone(status: MarketGroupSnapshotResponse["status"]): string {
  if (status === "ok") {
    return "bg-dark-green/10 text-dark-green border-dark-green/15";
  }
  if (status === "stale") {
    return "bg-gold/10 text-ochre border-gold/20";
  }

  return "bg-cream text-warm-gray border-divider";
}

function getLatestSnapshot(
  snapshots: readonly MarketGroupSnapshotResponse[],
  field: "as_of" | "last_success_at",
): string | null {
  if (snapshots.length === 0) {
    return null;
  }

  return snapshots.reduce((latest, snapshot) => {
    if (!latest) {
      return snapshot[field];
    }

    return new Date(snapshot[field]) >= new Date(latest) ? snapshot[field] : latest;
  }, "");
}

function getCombinedSource(snapshots: readonly MarketGroupSnapshotResponse[]): string {
  if (snapshots.length === 0) {
    return "";
  }

  const sources = Array.from(new Set(snapshots.map((snapshot) => snapshot.source)));
  return sources.join(" / ");
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
  snapshot,
  copy,
  locale,
}: Readonly<{
  snapshot: MarketGroupSnapshotResponse;
  copy: BoardCopy;
  locale: string;
}>): React.JSX.Element {
  return (
    <section className="rounded-2xl border border-divider bg-white p-5 shadow-sm md:p-6">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-serif font-medium text-ink">
            {copy.sections[snapshot.group]}
          </h2>
          <p className="mt-1 text-xs text-warm-gray">
            {copy.asOf} {formatAsOf(locale, snapshot.as_of)}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs uppercase tracking-[0.16em] text-warm-gray">
            {snapshot.items.length}
          </span>
          <span
            className={`shrink-0 rounded-full border px-2 py-1 text-[11px] font-medium ${getGroupStatusTone(snapshot.status)}`}
          >
            {copy.groupStatus[snapshot.status]}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {snapshot.items.map((metric) => (
          <MetricCard
            key={`${snapshot.group}-${metric.symbol}`}
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

function SectionUnavailableState({
  title,
  message,
  onRetry,
  retryLabel,
}: Readonly<{
  title: string;
  message: string;
  onRetry: () => void;
  retryLabel: string;
}>): React.JSX.Element {
  return (
    <section className="rounded-2xl border border-divider bg-white p-5 shadow-sm md:p-6">
      <div className="flex min-h-56 flex-col items-center justify-center gap-4 rounded-xl border border-dashed border-divider bg-cream/40 px-6 text-center">
        <AlertCircle className="h-8 w-8 text-accent-red" />
        <div className="space-y-2">
          <h2 className="text-lg font-serif font-medium text-ink">{title}</h2>
          <p className="text-sm text-warm-gray">{message}</p>
        </div>
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-2 rounded-xl bg-terracotta px-4 py-2 text-sm font-medium text-white transition-all duration-200 hover:-translate-y-0.5 hover:bg-terracotta-dark hover:shadow-lg"
        >
          {retryLabel}
        </button>
      </div>
    </section>
  );
}

function SectionLoadingState({
  title,
  message,
}: Readonly<{
  title: string;
  message: string;
}>): React.JSX.Element {
  return (
    <section className="rounded-2xl border border-divider bg-white p-5 shadow-sm md:p-6">
      <div className="flex min-h-56 flex-col items-center justify-center gap-4 rounded-xl border border-dashed border-divider bg-cream/40 px-6 text-center">
        <Loader2 className="h-8 w-8 animate-spin text-terracotta" />
        <div className="space-y-2">
          <h2 className="text-lg font-serif font-medium text-ink">{title}</h2>
          <p className="text-sm text-warm-gray">{message}</p>
        </div>
      </div>
    </section>
  );
}

export default function BoardPage(): React.JSX.Element {
  const locale = useLocale();
  const boardT = useTranslations("board");
  const copy = getCopy(locale);
  const macroSnapshot = useApi<MarketGroupSnapshotResponse>(
    "/api/v1/public/market-macro",
  );
  const assetsSnapshot = useApi<MarketGroupSnapshotResponse>(
    "/api/v1/public/market-assets",
  );
  const snapshots = {
    macro: macroSnapshot.data,
    assets: assetsSnapshot.data,
  };
  const availableSnapshots = Object.values(snapshots).filter(
    (snapshot): snapshot is MarketGroupSnapshotResponse => snapshot !== null,
  );
  const hasAnyData = availableSnapshots.length > 0;
  const latestAsOf = getLatestSnapshot(availableSnapshots, "as_of");
  const latestLastSuccess = getLatestSnapshot(availableSnapshots, "last_success_at");
  const combinedSource = getCombinedSource(availableSnapshots);
  const loading = !hasAnyData && (macroSnapshot.loading || assetsSnapshot.loading);
  const availabilitySummary = getAvailabilitySummary(snapshots, copy);

  return (
    <main className="min-h-screen bg-cream px-4 py-8 md:px-8 md:py-10">
      <div className="mx-auto max-w-6xl space-y-5">
        {loading ? (
          <LoadingState message={boardT("loading")} />
        ) : (
          <>
            <header className="rounded-2xl border border-divider bg-white p-6 shadow-sm">
              <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                <div className="max-w-3xl">
                  <p className="text-xs font-medium uppercase tracking-[0.24em] text-warm-gray">
                    {copy.eyebrow}
                  </p>
                  <h1 className="mt-1 text-3xl font-serif font-medium tracking-tight text-ink md:text-4xl">
                    {copy.title}
                  </h1>
                  <p className="mt-3 max-w-2xl text-sm leading-relaxed text-charcoal/80 md:text-base">
                    {copy.summary}
                  </p>
                  <p className="mt-2 max-w-2xl text-sm leading-relaxed text-charcoal/70">
                    {availabilitySummary}
                  </p>
                  <p className="mt-3 text-sm text-warm-gray">
                    {latestAsOf ? formatAsOf(locale, latestAsOf) : boardT("unavailable")}
                  </p>
                </div>

                <div className="rounded-xl border border-divider bg-cream/60 p-4 lg:min-w-72">
                  <p className="text-xs uppercase tracking-[0.16em] text-warm-gray">
                    {copy.asOf}
                  </p>
                  <p className="mt-1 text-sm font-medium text-charcoal">
                    {latestAsOf ? formatAsOf(locale, latestAsOf) : boardT("unavailable")}
                  </p>
                  <p className="mt-4 text-xs uppercase tracking-[0.16em] text-warm-gray">
                    {copy.lastSuccess}
                  </p>
                  <p className="mt-1 text-sm font-medium text-charcoal">
                    {latestLastSuccess
                      ? formatAsOf(locale, latestLastSuccess)
                      : boardT("unavailable")}
                  </p>
                  <p className="mt-4 text-xs uppercase tracking-[0.16em] text-warm-gray">
                    {copy.source}
                  </p>
                  <p className="mt-1 text-sm font-medium text-charcoal">
                    {combinedSource || boardT("unavailable")}
                  </p>
                </div>
              </div>
            </header>

            {snapshots.macro ? (
              <MetricSection snapshot={snapshots.macro} copy={copy} locale={locale} />
            ) : macroSnapshot.loading ? (
              <SectionLoadingState title={copy.sections.macro} message={boardT("loading")} />
            ) : (
              <SectionUnavailableState
                title={copy.sections.macro}
                message={boardT("sectionUnavailable")}
                onRetry={macroSnapshot.refetch}
                retryLabel={boardT("retry")}
              />
            )}
            {snapshots.assets ? (
              <MetricSection snapshot={snapshots.assets} copy={copy} locale={locale} />
            ) : assetsSnapshot.loading ? (
              <SectionLoadingState title={copy.sections.assets} message={boardT("loading")} />
            ) : (
              <SectionUnavailableState
                title={copy.sections.assets}
                message={boardT("sectionUnavailable")}
                onRetry={assetsSnapshot.refetch}
                retryLabel={boardT("retry")}
              />
            )}

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
