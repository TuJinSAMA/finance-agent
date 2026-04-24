"use client";

import { AlertCircle, ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";

import { useApi } from "@/hooks/useApi";
import type { GeoEventListResponse } from "@/types/geo-news";
import GeoEventCard from "./GeoEventCard";
import GeoNewsFilter from "./GeoNewsFilter";

type FilterLevel = "all" | "high";
const PAGE_SIZE = 5;

function formatDate(locale: string, value: string | null): string {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

export default function GeoNewsSection(): React.JSX.Element {
  const locale = useLocale();
  const t = useTranslations("board.geoNews");
  const [filter, setFilter] = useState<FilterLevel>("all");
  const [page, setPage] = useState(0);

  const impactParam = filter === "high" ? "3" : undefined;
  const offset = page * PAGE_SIZE;
  const events = useApi<GeoEventListResponse>(
    `/api/v1/geo-news/events?limit=${PAGE_SIZE}&offset=${offset}${impactParam ? `&impact_level=${impactParam}` : ""}`,
  );

  const data = events.data;
  const rangeStart = data && data.total > 0 ? offset + 1 : 0;
  const rangeEnd = data ? Math.min(offset + data.events.length, data.total) : 0;
  const canGoPrev = page > 0;
  const canGoNext = data ? offset + data.events.length < data.total : false;

  function handleFilterChange(nextFilter: FilterLevel): void {
    setFilter(nextFilter);
    setPage(0);
  }

  if (events.loading) {
    return (
      <section className="rounded-2xl border border-divider bg-white p-4 shadow-sm md:p-5">
        <div className="flex min-h-40 flex-col items-center justify-center gap-3">
          <Loader2 className="h-6 w-6 animate-spin text-terracotta" />
          <p className="text-sm text-warm-gray">{t("loading")}</p>
        </div>
      </section>
    );
  }

  if (events.error || !data) {
    return (
      <section className="rounded-2xl border border-divider bg-white p-4 shadow-sm md:p-5">
        <div className="flex min-h-40 flex-col items-center justify-center gap-3">
          <AlertCircle className="h-6 w-6 text-accent-red" />
          <p className="text-sm text-warm-gray">{t("sectionUnavailable")}</p>
        </div>
      </section>
    );
  }

  return (
    <section className="rounded-2xl border border-divider bg-white p-4 shadow-sm md:p-5">
      <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.24em] text-warm-gray">
            {t("eyebrow")}
          </p>
          <h2 className="mt-1 text-xl font-serif font-medium tracking-tight text-ink">
            {t("title")}
          </h2>
          <p className="mt-1 text-xs text-warm-gray">
            {t("lastUpdated")}: {formatDate(locale, data.last_updated)} · {data.total} {t("activeEvents")}
          </p>
        </div>
        <GeoNewsFilter
          level={filter}
          onChange={handleFilterChange}
          allLabel={t("allEvents")}
          highLabel={t("filterHighImpact")}
        />
      </div>

      {data.events.length === 0 ? (
        <p className="py-8 text-center text-sm text-warm-gray">{t("unavailable")}</p>
      ) : (
        <div className="space-y-2">
          {data.events.map((event) => (
            <GeoEventCard key={event.id} event={event} locale={locale} />
          ))}
        </div>
      )}

      {data.total > PAGE_SIZE && (
        <div className="mt-4 flex flex-col gap-3 border-t border-divider pt-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-warm-gray">
            {t("range", { start: rangeStart, end: rangeEnd, total: data.total })}
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPage((current) => Math.max(current - 1, 0))}
              disabled={!canGoPrev}
              className="inline-flex items-center gap-1 rounded-lg border border-divider px-3 py-1.5 text-xs font-medium text-charcoal transition-colors hover:bg-cream disabled:cursor-not-allowed disabled:opacity-40"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              {t("previous")}
            </button>
            <button
              type="button"
              onClick={() => setPage((current) => current + 1)}
              disabled={!canGoNext}
              className="inline-flex items-center gap-1 rounded-lg border border-divider px-3 py-1.5 text-xs font-medium text-charcoal transition-colors hover:bg-cream disabled:cursor-not-allowed disabled:opacity-40"
            >
              {t("next")}
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
