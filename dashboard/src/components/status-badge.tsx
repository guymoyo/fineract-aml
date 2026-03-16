import { cn, formatStatusLabel } from "@/lib/utils";

interface StatusBadgeProps {
  status: string;
  colorClass: string;
}

export function StatusBadge({ status, colorClass }: StatusBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium",
        colorClass,
      )}
    >
      {formatStatusLabel(status)}
    </span>
  );
}
