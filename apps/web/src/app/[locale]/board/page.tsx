"use client";

import { AlertCircle, Loader2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useApi } from "@/hooks/useApi";
import type { MarketGroupSnapshotResponse, MarketMetric } from "@/types/api";
import GeoNewsSection from "@/components/geo-news/GeoNewsSection";

type BoardCopy = {
  eyebrow: string;
  title: string;
  combinedTitle: string;
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
};

const EN_COPY: BoardCopy = {
  eyebrow: "Public market board",
  title: "Macro and asset snapshots",
  combinedTitle: "Macro & assets",
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
};

const ZH_COPY: BoardCopy = {
  eyebrow: "公开市场看板",
  title: "宏观与资产快照",
  combinedTitle: "宏观与资产",
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
      className={`rounded-lg border px-3 py-3 transition-colors ${
        metric.status === "unavailable"
          ? "border-divider bg-cream/60"
          : "border-divider bg-white"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-[11px] font-medium uppercase tracking-[0.14em] text-warm-gray">
            {metric.name}
          </p>
          <p className="mt-0.5 truncate text-[10px] font-mono text-warm-gray/80">
            {metric.symbol}
          </p>
        </div>
        {metric.status !== "ok" && (
          <span
            className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium ${getStatusTone(metric.status)}`}
          >
            {copy.status[metric.status]}
          </span>
        )}
      </div>

      <p
        className={`mt-3 text-xl font-semibold tracking-tight tabular-nums ${
          metric.status === "unavailable" ? "text-warm-gray" : "text-ink"
        }`}
      >
        {value}
      </p>

      {metric.change_pct !== null ? (
        <p className={`mt-1 text-xs font-medium tabular-nums ${getChangeTone(metric.change_pct)}`}>
          {formatMetricChange(metric.change_pct)}
        </p>
      ) : metric.status === "unavailable" ? (
        <p className="mt-1 text-xs text-warm-gray">{copy.unavailable}</p>
      ) : (
        <p className="mt-1 text-xs text-warm-gray">{copy.noChange}</p>
      )}
    </article>
  );
}

function MetricGroup({
  snapshot,
  copy,
  locale,
}: Readonly<{
  snapshot: MarketGroupSnapshotResponse;
  copy: BoardCopy;
  locale: string;
}>): React.JSX.Element {
  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-serif font-medium text-ink">
            {copy.sections[snapshot.group]}
          </h3>
          <p className="mt-1 text-xs text-warm-gray">
            {copy.asOf} {formatAsOf(locale, snapshot.as_of)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs uppercase tracking-[0.16em] text-warm-gray">
            {snapshot.items.length}
          </span>
          {snapshot.status !== "ok" && (
            <span
              className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium ${getGroupStatusTone(snapshot.status)}`}
            >
              {copy.groupStatus[snapshot.status]}
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-[repeat(auto-fit,minmax(136px,1fr))] gap-2">
        {snapshot.items.map((metric) => (
          <MetricCard
            key={`${snapshot.group}-${metric.symbol}`}
            metric={metric}
            copy={copy}
          />
        ))}
      </div>
    </div>
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
    <div className="rounded-xl border border-dashed border-divider bg-cream/40 px-4 py-6 text-center">
      <div className="flex flex-col items-center justify-center gap-3">
        <AlertCircle className="h-6 w-6 text-accent-red" />
        <div className="space-y-1">
          <h3 className="text-base font-serif font-medium text-ink">{title}</h3>
          <p className="text-xs text-warm-gray">{message}</p>
        </div>
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-2 rounded-lg bg-terracotta px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-terracotta-dark"
        >
          {retryLabel}
        </button>
      </div>
    </div>
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
    <div className="rounded-xl border border-dashed border-divider bg-cream/40 px-4 py-6 text-center">
      <div className="flex flex-col items-center justify-center gap-3">
        <Loader2 className="h-6 w-6 animate-spin text-terracotta" />
        <div className="space-y-1">
          <h3 className="text-base font-serif font-medium text-ink">{title}</h3>
          <p className="text-xs text-warm-gray">{message}</p>
        </div>
      </div>
    </div>
  );
}

function CombinedMetricSection({
  snapshots,
  macroLoading,
  assetsLoading,
  onRetryMacro,
  onRetryAssets,
  copy,
  locale,
  loadingLabel,
  unavailableLabel,
  retryLabel,
}: Readonly<{
  snapshots: {
    macro: MarketGroupSnapshotResponse | null;
    assets: MarketGroupSnapshotResponse | null;
  };
  macroLoading: boolean;
  assetsLoading: boolean;
  onRetryMacro: () => void;
  onRetryAssets: () => void;
  copy: BoardCopy;
  locale: string;
  loadingLabel: string;
  unavailableLabel: string;
  retryLabel: string;
}>): React.JSX.Element {
  return (
    <section className="rounded-2xl border border-divider bg-white p-4 shadow-sm md:p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-lg font-serif font-medium text-ink">{copy.combinedTitle}</h2>
      </div>

      <div className="space-y-5">
        {snapshots.macro ? (
          <MetricGroup snapshot={snapshots.macro} copy={copy} locale={locale} />
        ) : macroLoading ? (
          <SectionLoadingState title={copy.sections.macro} message={loadingLabel} />
        ) : (
          <SectionUnavailableState
            title={copy.sections.macro}
            message={unavailableLabel}
            onRetry={onRetryMacro}
            retryLabel={retryLabel}
          />
        )}

        {snapshots.assets ? (
          <MetricGroup snapshot={snapshots.assets} copy={copy} locale={locale} />
        ) : assetsLoading ? (
          <SectionLoadingState title={copy.sections.assets} message={loadingLabel} />
        ) : (
          <SectionUnavailableState
            title={copy.sections.assets}
            message={unavailableLabel}
            onRetry={onRetryAssets}
            retryLabel={retryLabel}
          />
        )}
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
    <main className="min-h-screen bg-cream px-4 py-4 md:px-8 md:py-6">
      <div className="mx-auto max-w-6xl space-y-4">
        {loading ? (
          <LoadingState message={boardT("loading")} />
        ) : (
          <>
            <header className="rounded-2xl border border-divider bg-white px-4 py-3 shadow-sm md:px-5">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div className="min-w-0">
                  <p className="text-xs font-medium uppercase tracking-[0.24em] text-warm-gray">
                    {copy.eyebrow}
                  </p>
                  <h1 className="mt-1 text-2xl font-serif font-medium tracking-tight text-ink md:text-3xl">
                    {copy.title}
                  </h1>
                </div>

                <div className="grid gap-2 text-sm text-charcoal sm:grid-cols-2 lg:flex lg:flex-wrap lg:items-center lg:justify-end">
                  <span>
                    <span className="text-warm-gray">{copy.asOf}: </span>
                    <span className="font-medium">
                      {latestAsOf ? formatAsOf(locale, latestAsOf) : boardT("unavailable")}
                    </span>
                  </span>
                  <span>
                    <span className="text-warm-gray">{copy.lastSuccess}: </span>
                    <span className="font-medium">
                      {latestLastSuccess
                        ? formatAsOf(locale, latestLastSuccess)
                        : boardT("unavailable")}
                    </span>
                  </span>
                  <span>
                    <span className="text-warm-gray">{copy.source}: </span>
                    <span className="font-medium">{combinedSource || boardT("unavailable")}</span>
                  </span>
                  {availabilitySummary && (
                    <span className="text-charcoal/75">{availabilitySummary}</span>
                  )}
                </div>
              </div>
            </header>

            <CombinedMetricSection
              snapshots={snapshots}
              macroLoading={macroSnapshot.loading}
              assetsLoading={assetsSnapshot.loading}
              onRetryMacro={macroSnapshot.refetch}
              onRetryAssets={assetsSnapshot.refetch}
              copy={copy}
              locale={locale}
              loadingLabel={boardT("loading")}
              unavailableLabel={boardT("sectionUnavailable")}
              retryLabel={boardT("retry")}
            />
            <GeoNewsSection />
          </>
        )}
      </div>
    </main>
  );
}
