import { AlertTriangle, CheckCircle2, CircleAlert, Info, ShieldAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { Severity } from "@/lib/types";

const CONFIG: Record<Severity, { label: string; variant: "high" | "review" | "default" | "muted"; icon: typeof Info }> = {
  critical: { label: "Critical", variant: "high", icon: ShieldAlert },
  high: { label: "High", variant: "high", icon: AlertTriangle },
  medium: { label: "Medium", variant: "review", icon: CircleAlert },
  low: { label: "Low", variant: "default", icon: Info },
  info: { label: "Info", variant: "muted", icon: CheckCircle2 },
};

export function SeverityBadge({
  severity,
  withIcon = true,
  className,
}: {
  severity: Severity;
  withIcon?: boolean;
  className?: string;
}) {
  const config = CONFIG[severity] ?? CONFIG.info;
  const Icon = config.icon;
  return (
    <Badge variant={config.variant} className={cn("uppercase tracking-wide", className)}>
      {withIcon && <Icon className="size-3" />}
      {config.label}
    </Badge>
  );
}

export function ConfidenceBar({ value, className }: { value: number; className?: string }) {
  const percentage = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-foreground/40" style={{ width: `${percentage}%` }} />
      </div>
      <span className="tabular text-2xs text-muted-foreground">{percentage}%</span>
    </div>
  );
}
