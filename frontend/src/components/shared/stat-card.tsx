import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * A single number with its label and, where useful, what it should make you do.
 * No sparklines, no gradients: these are operational counters, read at a glance,
 * many times a day.
 */
export function StatCard({
  label,
  value,
  hint,
  icon,
  tone = "default",
  href,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  icon?: ReactNode;
  tone?: "default" | "low" | "review" | "high" | "primary";
  href?: string;
}) {
  const toneClass = {
    default: "text-foreground",
    primary: "text-primary",
    low: "text-risk-low",
    review: "text-risk-review",
    high: "text-risk-high",
  }[tone];

  const body = (
    <div className="flex h-full items-start justify-between gap-3 p-4">
      <div className="min-w-0 space-y-1">
        <p className="text-2xs font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
        <p className={cn("tabular text-2xl font-semibold leading-none", toneClass)}>{value}</p>
        {hint && <p className="text-2xs leading-snug text-muted-foreground">{hint}</p>}
      </div>
      {icon && (
        <span
          className={cn(
            "inline-flex size-8 shrink-0 items-center justify-center rounded-md border bg-muted/60",
            toneClass,
          )}
        >
          {icon}
        </span>
      )}
    </div>
  );

  return (
    <div
      className={cn(
        "rounded-lg border bg-card shadow-sm transition-colors",
        href && "hover:border-primary/40 hover:bg-accent/30",
      )}
    >
      {href ? (
        <a href={href} className="block h-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          {body}
        </a>
      ) : (
        body
      )}
    </div>
  );
}
