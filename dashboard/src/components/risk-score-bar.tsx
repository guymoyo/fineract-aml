import { cn } from "@/lib/utils";

interface RiskScoreBarProps {
  score: number | null;
  showLabel?: boolean;
}

export function RiskScoreBar({ score, showLabel = true }: RiskScoreBarProps) {
  if (score === null) {
    return <span className="text-sm text-gray-400">N/A</span>;
  }

  const percent = Math.round(score * 100);

  const barColor =
    score >= 0.8
      ? "bg-red-500"
      : score >= 0.5
        ? "bg-amber-500"
        : "bg-green-500";

  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-20 overflow-hidden rounded-full bg-gray-200">
        <div
          className={cn("h-full rounded-full transition-all", barColor)}
          style={{ width: `${percent}%` }}
        />
      </div>
      {showLabel && (
        <span className="text-xs font-medium text-gray-600">{percent}%</span>
      )}
    </div>
  );
}
