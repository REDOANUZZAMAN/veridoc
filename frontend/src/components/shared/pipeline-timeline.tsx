import {
  AlertOctagon, CheckCircle2, ChevronRight, CircleDashed, Clock, MinusCircle, XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { InfoTip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { Stage } from "@/lib/types";

const STAGE_STYLE = {
  completed: { icon: CheckCircle2, tone: "text-risk-low", ring: "border-risk-low/40 bg-risk-low/10" },
  running: { icon: Clock, tone: "text-primary", ring: "border-primary/40 bg-primary/10" },
  unavailable: { icon: AlertOctagon, tone: "text-risk-review", ring: "border-risk-review/40 bg-risk-review/10" },
  failed: { icon: XCircle, tone: "text-risk-high", ring: "border-risk-high/40 bg-risk-high/10" },
  skipped: { icon: MinusCircle, tone: "text-muted-foreground", ring: "border-border bg-muted" },
  pending: { icon: CircleDashed, tone: "text-muted-foreground", ring: "border-border bg-muted" },
} as const;

/**
 * The processing pipeline, rendered as it actually ran.
 *
 * This is the product's core claim made visible: a decision is the output of
 * fourteen named stages, each of which either completed, degraded or was not
 * applicable - and the investigator can see which.
 */
export function PipelineTimeline({
  stages,
  compact = false,
  className,
}: {
  stages: Stage[];
  compact?: boolean;
  className?: string;
}) {
  if (!stages?.length) {
    return (
      <p className="px-4 py-6 text-xs text-muted-foreground">
        No analysis run has been recorded for this document yet.
      </p>
    );
  }

  if (compact) {
    return (
      <div className={cn("flex flex-wrap items-center gap-1", className)}>
        {stages.map((stage, index) => {
          const style = STAGE_STYLE[stage.status] ?? STAGE_STYLE.pending;
          const Icon = style.icon;
          return (
            <div key={stage.key} className="flex items-center gap-1">
              <InfoTip
                label={
                  <span>
                    <strong>{stage.label}</strong> — {stage.status}
                    {stage.message ? `: ${stage.message}` : ""}
                  </span>
                }
              >
                <span
                  className={cn(
                    "inline-flex size-6 items-center justify-center rounded-full border",
                    style.ring,
                    style.tone,
                  )}
                >
                  <Icon className="size-3.5" />
                </span>
              </InfoTip>
              {index < stages.length - 1 && (
                <ChevronRight className="size-3 text-muted-foreground/40" aria-hidden />
              )}
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <ol className={cn("divide-y", className)}>
      {stages.map((stage) => {
        const style = STAGE_STYLE[stage.status] ?? STAGE_STYLE.pending;
        const Icon = style.icon;
        const provider =
          (stage.provider?.label as string) ??
          (stage.provider?.key as string) ??
          null;
        return (
          <li key={stage.key} className="flex gap-3 px-4 py-2.5">
            <span
              className={cn(
                "mt-0.5 inline-flex size-6 shrink-0 items-center justify-center rounded-full border",
                style.ring,
                style.tone,
              )}
            >
              <Icon className="size-3.5" />
            </span>
            <div className="min-w-0 flex-1 space-y-0.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-medium">{stage.label}</span>
                <span className={cn("text-2xs uppercase tracking-wider", style.tone)}>
                  {stage.status}
                </span>
                {stage.findings > 0 && (
                  <Badge variant="muted">{stage.findings} finding{stage.findings === 1 ? "" : "s"}</Badge>
                )}
                {stage.duration_ms > 0 && (
                  <span className="tabular text-2xs text-muted-foreground">{stage.duration_ms} ms</span>
                )}
              </div>
              {stage.message && (
                <p className="text-2xs leading-relaxed text-muted-foreground">{stage.message}</p>
              )}
              {provider && (
                <p className="text-2xs text-muted-foreground/80">
                  Provider: <span className="font-medium">{provider}</span>
                  {stage.provider?.version ? ` v${stage.provider.version}` : ""}
                  {stage.provider?.is_demo ? " · demo" : ""}
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
