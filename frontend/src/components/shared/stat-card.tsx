import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * A single number with its label and, where useful, what it should make you do.
 * No sparklines, no gradients: these are operational counters, read at a glance,
 * many times a day. The tone tints the icon chip and the value only — the label
 * and hint always stay in text ink so colour is never the thing being read.
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

  const chipClass = {
    default: "border-border bg-surface text-muted-foreground",
    primary: "border-primary/20 bg-primary/10 text-primary",
    low: "border-risk-low/20 bg-risk-low/10 text-risk-low",
    review: "border-risk-review/20 bg-risk-review/10 text-risk-review",
    high: "border-risk-high/20 bg-risk-high/10 text-risk-high",
  }[tone];

  const body = (
    <div className="flex h-full items-start justify-between gap-3 p-5">
      <div className="min-w-0 space-y-2">
        {/* Two lines are reserved for the label so the numbers land on the same
            baseline across a row of tiles, however long the labels are. */}
        <p className="eyebrow line-clamp-2 min-h-[2.125rem]">{label}</p>
        <p className={cn("tabular text-2xl font-semibold leading-none", toneClass)}>{value}</p>
        {hint && <p className="text-2xs leading-snug text-muted-foreground">{hint}</p>}
      </div>
      {icon && (
        <span
          className={cn(
            "inline-flex size-9 shrink-0 items-center justify-center rounded-lg border",
            chipClass,
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
        "rounded-xl border bg-card shadow-card transition-[border-color,box-shadow,background-color]",
        href && "hover:border-primary/35 hover:shadow-raised",
      )}
    >
      {href ? (
        <a href={href} className="block h-full rounded-xl focus-visible:outline-none">
          {body}
        </a>
      ) : (
        body
      )}
    </div>
  );
}
