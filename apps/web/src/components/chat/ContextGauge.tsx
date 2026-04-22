"use client";

import type { ContextUsage } from "@/types/chat";

interface ContextGaugeProps {
  usage: ContextUsage;
}

export function ContextGauge({ usage }: ContextGaugeProps) {
  const pct = Math.min(100, Math.round((usage.used_tokens / usage.max_tokens) * 100));

  const barColor =
    pct > 85 ? "bg-red-500" :
    pct > 60 ? "bg-yellow-500" :
    "bg-sage-muted";

  return (
    <div className="flex items-center gap-2 text-xs text-warm-gray px-2 py-1">
      <span>Context</span>
      <div className="flex-1 h-2 bg-warm-gray/20 rounded-full overflow-hidden max-w-32">
        <div
          className={`h-full ${barColor} rounded-full transition-all duration-300`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span>{pct}%</span>
      {pct > 85 && (
        <span className="text-red-500 font-medium animate-pulse">!</span>
      )}
    </div>
  );
}