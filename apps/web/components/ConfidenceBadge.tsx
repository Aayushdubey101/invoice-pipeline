import { cn } from "@/lib/utils";

interface ConfidenceBadgeProps {
  confidence: number;
  breakdown?: Record<string, number> | null;
  className?: string;
}

export function ConfidenceBadge({ confidence, breakdown, className }: ConfidenceBadgeProps) {
  const pct = Math.round(confidence * 100);
  const color =
    confidence >= 0.9
      ? "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300"
      : confidence >= 0.75
        ? "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300"
        : "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300";

  let tooltip = `Confidence: ${pct}%`;
  if (breakdown) {
    tooltip += "\n\nBreakdown:";
    for (const [key, val] of Object.entries(breakdown)) {
      if (key !== "overall") {
        tooltip += `\n- ${key}: ${Math.round(val * 100)}%`;
      }
    }
  }

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium tabular-nums",
        breakdown ? "cursor-help" : "",
        color,
        className
      )}
      title={tooltip}
    >
      {pct}%
    </span>
  );
}
