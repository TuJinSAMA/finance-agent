"use client";

import { ChevronDown, ExternalLink } from "lucide-react";
import { useState } from "react";

import type { GeoEvent, ImpactLevel } from "@/types/geo-news";

const CATEGORY_LABELS: Record<string, string> = {
  military: "Military",
  sanctions: "Sanctions",
  energy: "Energy",
  trade_policy: "Trade Policy",
  geopolitics: "Geopolitics",
  macro_economy: "Macro Economy",
  supply_disruption: "Supply Disruption",
  regulation: "Regulation",
};

const REGION_LABELS: Record<string, string> = {
  middle_east: "Middle East",
  east_asia: "East Asia",
  europe: "Europe",
  americas: "Americas",
  africa: "Africa",
  global: "Global",
};

function parseCategories(categories: string | null): string[] {
  if (!categories) return [];
  try {
    const parsed = JSON.parse(categories);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function formatEventDate(dateStr: string, locale: string): string {
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return dateStr;
  return new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function ImpactBadge({ level }: { level: ImpactLevel }): React.JSX.Element {
  if (level === 3) {
    return (
      <span className="inline-flex items-center rounded-full bg-terracotta px-2 py-0.5 text-[11px] font-medium uppercase tracking-[0.12em] text-white">
        High Impact
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-full bg-cream-light px-2 py-0.5 text-[11px] font-medium text-charcoal/80">
      Medium Impact
    </span>
  );
}

export default function GeoEventCard({
  event,
  locale,
}: Readonly<{
  event: GeoEvent;
  locale: string;
}>): React.JSX.Element {
  const [expanded, setExpanded] = useState(false);
  const isHighImpact = event.impact_level === 3;
  const cats = parseCategories(event.categories);

  return (
    <article
      className={`rounded-xl border bg-white transition-colors ${
        isHighImpact
          ? "border-l-[3px] border-l-terracotta border-t-0 border-r-0 border-b-0 border-divider"
          : "border-l-[2px] border-l-stone-gray border-t-0 border-r-0 border-b-0 border-divider"
      } ${isHighImpact ? "p-4" : "p-3"}`}
    >
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <ImpactBadge level={event.impact_level} />
              {event.region && (
                <span className="text-[11px] text-warm-gray">
                  {REGION_LABELS[event.region] || event.region}
                </span>
              )}
            </div>
            <h3
              className={`mt-1.5 leading-snug text-ink ${
                isHighImpact
                  ? "font-serif text-base font-medium"
                  : "text-sm font-medium"
              }`}
            >
              {event.title}
            </h3>
            <p className="mt-1 text-xs text-warm-gray">
              {event.source_name} · {formatEventDate(event.event_date, locale)}
            </p>
          </div>
          <ChevronDown
            className={`h-4 w-4 shrink-0 text-warm-gray transition-transform ${
              expanded ? "rotate-180" : ""
            }`}
          />
        </div>
      </button>

      {expanded && (
        <div className="mt-3 border-t border-divider pt-3 space-y-3">
          <p className="text-sm leading-relaxed text-charcoal/80">{event.summary}</p>

          {cats.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {cats.map((cat) => (
                <span
                  key={cat}
                  className="rounded-full bg-cream-light px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-charcoal/70"
                >
                  {CATEGORY_LABELS[cat] || cat}
                </span>
              ))}
            </div>
          )}

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 text-xs text-warm-gray">
              {event.region && (
                <span>
                  <span className="font-medium text-charcoal/70">Region: </span>
                  {REGION_LABELS[event.region] || event.region}
                </span>
              )}
            </div>
            <a
              href={event.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs font-medium text-terracotta hover:text-terracotta-dark"
            >
              Read original
              <ExternalLink className="h-3 w-3" />
            </a>
          </div>
        </div>
      )}
    </article>
  );
}
