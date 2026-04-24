"use client";

type FilterLevel = "all" | "high";

export default function GeoNewsFilter({
  level,
  onChange,
  allLabel,
  highLabel,
}: Readonly<{
  level: FilterLevel;
  onChange: (level: FilterLevel) => void;
  allLabel: string;
  highLabel: string;
}>): React.JSX.Element {
  return (
    <div className="flex gap-2">
      <button
        type="button"
        onClick={() => onChange("all")}
        className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
          level === "all"
            ? "bg-ink text-warm-silver"
            : "bg-warm-sand text-charcoal-warm hover:bg-warm-sand/80"
        }`}
      >
        {allLabel}
      </button>
      <button
        type="button"
        onClick={() => onChange("high")}
        className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
          level === "high"
            ? "bg-terracotta text-white"
            : "bg-warm-sand text-charcoal-warm hover:bg-warm-sand/80"
        }`}
      >
        {highLabel}
      </button>
    </div>
  );
}