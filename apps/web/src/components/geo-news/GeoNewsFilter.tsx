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
    <div className="inline-flex rounded-lg border border-divider bg-cream p-1">
      <button
        type="button"
        onClick={() => onChange("all")}
        className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
          level === "all"
            ? "bg-ink text-white shadow-sm"
            : "text-charcoal/70 hover:bg-white hover:text-charcoal"
        }`}
      >
        {allLabel}
      </button>
      <button
        type="button"
        onClick={() => onChange("high")}
        className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
          level === "high"
            ? "bg-terracotta text-white shadow-sm"
            : "text-charcoal/70 hover:bg-white hover:text-charcoal"
        }`}
      >
        {highLabel}
      </button>
    </div>
  );
}
