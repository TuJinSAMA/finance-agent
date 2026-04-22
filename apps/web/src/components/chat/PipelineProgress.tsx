"use client";

import type { PipelineStageUpdate } from "@/types/chat";

const STAGE_LIST: Record<string, string> = {
  market_analyst: "Market Analyst",
  social_analyst: "Social Analyst",
  news_analyst: "News Analyst",
  fundamentals_analyst: "Fundamentals",
  bull_researcher: "Bull Researcher",
  bear_researcher: "Bear Researcher",
  research_manager: "Research Manager",
  trader: "Trader",
  aggressive_analyst: "Risk Aggressive",
  conservative_analyst: "Risk Conservative",
  neutral_analyst: "Risk Neutral",
  portfolio_manager: "Portfolio Manager",
};

interface PipelineProgressProps {
  stages: PipelineStageUpdate[];
}

export function PipelineProgress({ stages }: PipelineProgressProps) {
  if (stages.length === 0) return null;

  const stageNames = Object.keys(STAGE_LIST);

  return (
    <div className="mb-4 p-3 bg-ink/5 rounded-xl">
      <p className="text-xs font-medium text-warm-gray mb-2">
        Pipeline Progress ({stages.length}/{stageNames.length})
      </p>
      <div className="flex flex-wrap gap-1.5">
        {stageNames.map((stage, idx) => {
          const completed = stages.some((s) => s.stage === stage);
          const isCurrent = !completed && stages.length === idx;
          return (
            <div
              key={stage}
              className={`px-2 py-1 rounded text-xs font-medium transition-colors
                ${completed
                  ? "bg-sage-muted/30 text-sage-muted"
                  : isCurrent
                    ? "bg-terracotta/20 text-terracotta animate-pulse"
                    : "bg-warm-gray/10 text-warm-gray"
                }`}
            >
              {STAGE_LIST[stage]}
            </div>
          );
        })}
      </div>
    </div>
  );
}