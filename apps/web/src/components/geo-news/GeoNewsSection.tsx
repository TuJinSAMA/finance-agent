"use client";

import { AlertCircle, Loader2 } from "lucide-react";
import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";

import { useApi } from "@/hooks/useApi";
import type { GeoEventListResponse } from "@/types/geo-news";
import GeoEventCard from "./GeoEventCard";
import GeoNewsFilter from "./GeoNewsFilter";

type FilterLevel = "all" | "high";

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

  const impactParam = filter === "high" ? "3" : undefined;
  const events = useApi<GeoEventListResponse>(
    `/api/v1/geo-news/events?limit=20${impactParam ? `&impact_level=${impactParam}` : ""}`,
  );

  const data = events.data;

  if (events.loading) {
    return (
      <section className="rounded-2xl border border-divider bg-white p-5 shadow-sm md:p-6">
        <div className="flex min-h-48 flex-col items-center justify-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-terracotta" />
          <p className="text-sm text-warm-gray">{t("loading")}</p>
        </div>
      </section>
    );
  }

  if (events.error || !data) {
    return (
      <section className="rounded-2xl border border-divider bg-white p-5 shadow-sm md:p-6">
        <div className="flex min-h-48 flex-col items-center justify-center gap-3">
          <AlertCircle className="h-8 w-8 text-accent-red" />
          <p className="text-sm text-warm-gray">{t("sectionUnavailable")}</p>
        </div>
      </section>
    );
  }

  return (
    <section className="rounded-2xl border border-divider bg-white p-5 shadow-sm md:p-6">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.24em] text-warm-gray">
            {t("eyebrow")}
          </p>
          <h2 className="mt-1 text-2xl font-serif font-medium tracking-tight text-ink">
            {t("title")}
          </h2>
          <p className="mt-1 text-xs text-warm-gray">
            {t("lastUpdated")}: {formatDate(locale, data.last_updated)} · {data.total} {t("activeEvents")}
          </p>
        </div>
        <GeoNewsFilter
          level={filter}
          onChange={setFilter}
          allLabel={t("allEvents")}
          highLabel={t("filterHighImpact")}
        />
      </div>

      {data.events.length === 0 ? (
        <p className="py-8 text-center text-sm text-warm-gray">{t("unavailable")}</p>
      ) : (
        <div className="space-y-3">
          {data.events.map((event) => (
            <GeoEventCard key={event.id} event={event} locale={locale} />
          ))}
        </div>
      )}
    </section>
  );
}