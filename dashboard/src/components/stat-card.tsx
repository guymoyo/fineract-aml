import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: LucideIcon;
  trend?: "up" | "down" | "neutral";
  className?: string;
}

export function StatCard({
  title,
  value,
  subtitle,
  icon: Icon,
  trend,
  className,
}: StatCardProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-gray-200 bg-white p-6 shadow-sm",
        className,
      )}
    >
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-gray-500">{title}</p>
        <Icon className="h-5 w-5 text-gray-400" />
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <p className="text-3xl font-semibold tracking-tight text-gray-900">
          {value}
        </p>
        {subtitle && (
          <span
            className={cn(
              "text-sm font-medium",
              trend === "up" && "text-red-600",
              trend === "down" && "text-green-600",
              trend === "neutral" && "text-gray-500",
              !trend && "text-gray-500",
            )}
          >
            {subtitle}
          </span>
        )}
      </div>
    </div>
  );
}
