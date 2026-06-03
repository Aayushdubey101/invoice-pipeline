import { cn } from "@/lib/utils";

interface ConfidenceBadgeProps {
  confidence: number;
  className?: string;
}

export function ConfidenceBadge({ confidence, className }: ConfidenceBadgeProps) {
  const pct = Math.round(confidence * 100);
  const color =
    confidence >= 0.9
      ? "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300"
      : confidence >= 0.75
        ? "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300"
        : "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300";

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium tabular-nums",
        color,
        className
      )}
      title={`Confidence: ${pct}%`}
    >
      {pct}%
    </span>
  );
}
