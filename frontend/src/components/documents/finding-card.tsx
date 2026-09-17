"use client";

import { useState } from "react";
import { ChevronDown, Crosshair, MapPin, UserCheck } from "lucide-react";

import { DemoBadge } from "@/components/shared/demo-notice";
import { ConfidenceBar, SeverityBadge } from "@/components/shared/severity-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { PROVENANCE_LABEL, humanise } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Finding } from "@/lib/types";

const STATUS_STYLE: Record<string, { label: string; variant: "muted" | "success" | "high" | "review" }> = {
  open: { label: "Awaiting review", variant: "muted" },
  confirmed: { label: "Confirmed by reviewer", variant: "high" },
  dismissed: { label: "Dismissed by reviewer", variant: "success" },
  information_requested: { label: "Information requested", variant: "review" },
};

/**
 * One finding, with its full evidence contract visible.
 *
 * Everything an investigator needs to weigh the signal is on the card: what was
 * measured, how confident the detector is, which detector and model version
 * produced it, where on the page it sits, and what a reviewer has already
 * decided about it.
 */
export function FindingCard({
  finding,
  active,
  onSelect,
  actions,
  compact = false,
}: {
  finding: Finding;
  active?: boolean;
  onSelect?: (id: string | null) => void;
  actions?: React.ReactNode;
  compact?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const status = STATUS_STYLE[finding.status] ?? STATUS_STYLE.open;
  const evidenceEntries = Object.entries(finding.evidence ?? {}).filter(
    ([key]) => !["provider_disclaimer", "uncertainty_note"].includes(key),
  );

  return (
    <article
      className={cn(
        "rounded-md border bg-card transition-colors",
        active ? "border-primary/60 ring-1 ring-primary/25" : "hover:border-border",
        finding.status === "dismissed" && "opacity-70",
      )}
    >
      <div className="space-y-2 p-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <SeverityBadge severity={finding.severity} />
          <Badge variant="outline">{finding.kind_label}</Badge>
          <Badge variant="muted" title={`Provenance: ${finding.provenance}`}>
            {PROVENANCE_LABEL[finding.provenance] ?? humanise(finding.provenance)}
          </Badge>
          {finding.is_demo_provider && <DemoBadge />}
          {finding.status !== "open" && (
            <Badge variant={status.variant}>
              <UserCheck className="size-3" />
              {status.label}
            </Badge>
          )}
          <div className="ml-auto flex items-center gap-2">
            <ConfidenceBar value={finding.confidence} />
            {finding.page && finding.region && onSelect && (
              <Button
                variant={active ? "secondary" : "ghost"}
                size="xs"
                onClick={() => onSelect(active ? null : finding.finding_id)}
              >
                <Crosshair className="size-3" />
                {active ? "Clear" : `Page ${finding.page}`}
              </Button>
            )}
            {finding.page && !finding.region && (
              <span className="flex items-center gap-1 text-2xs text-muted-foreground">
                <MapPin className="size-3" /> p{finding.page}
              </span>
            )}
          </div>
        </div>

        <h3 className="text-xs font-semibold leading-snug">{finding.title}</h3>

        {!compact && (
          <p className="text-2xs leading-relaxed text-muted-foreground">{finding.description}</p>
        )}

        {finding.affected_field && (
          <p className="rounded border border-dashed bg-muted/40 px-2 py-1.5 text-2xs">
            <span className="text-muted-foreground">Region covers </span>
            <span className="font-medium">{humanise(finding.affected_field)}</span>
            {finding.affected_value && (
              <>
                <span className="text-muted-foreground"> = </span>
                <span className="font-mono">{finding.affected_value}</span>
              </>
            )}
          </p>
        )}

        {(finding.expected || finding.actual) && (
          <dl className="grid grid-cols-2 gap-2 rounded border bg-muted/30 p-2">
            <div>
              <dt className="text-2xs uppercase tracking-wider text-muted-foreground">Expected</dt>
              <dd className="font-mono text-2xs">{finding.expected ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-2xs uppercase tracking-wider text-muted-foreground">Found</dt>
              <dd className="font-mono text-2xs">{finding.actual ?? "—"}</dd>
            </div>
          </dl>
        )}

        {(finding.value_a || finding.value_b) && (
          <dl className="grid grid-cols-2 gap-2 rounded border bg-muted/30 p-2">
            <div>
              <dt className="text-2xs uppercase tracking-wider text-muted-foreground">
                This document
              </dt>
              <dd className="break-words font-mono text-2xs">{finding.value_a ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-2xs uppercase tracking-wider text-muted-foreground">
                Counterpart
              </dt>
              <dd className="break-words font-mono text-2xs">{finding.value_b ?? "—"}</dd>
            </div>
          </dl>
        )}

        {finding.recommendation && (
          <p className="text-2xs leading-relaxed">
            <span className="font-semibold">Next step: </span>
            <span className="text-muted-foreground">{finding.recommendation}</span>
          </p>
        )}

        {finding.review_reason && (
          <p className="rounded border-l-2 border-primary/50 bg-muted/40 px-2 py-1.5 text-2xs italic leading-relaxed">
            “{finding.review_reason}”
          </p>
        )}

        <div className="flex flex-wrap items-center justify-between gap-2 pt-0.5">
          <p className="font-mono text-2xs text-muted-foreground">
            {finding.code} · {finding.detector} · {finding.model_version}
          </p>
          <div className="flex items-center gap-1">
            {evidenceEntries.length > 0 && (
              <Collapsible open={open} onOpenChange={setOpen}>
                <CollapsibleTrigger asChild>
                  <Button variant="ghost" size="xs">
                    <ChevronDown className={cn("size-3 transition-transform", open && "rotate-180")} />
                    Evidence
                  </Button>
                </CollapsibleTrigger>
              </Collapsible>
            )}
            {actions}
          </div>
        </div>

        {open && evidenceEntries.length > 0 && (
          <div className="rounded border bg-muted/40 p-2">
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono text-2xs leading-relaxed text-muted-foreground scrollbar-thin">
              {JSON.stringify(Object.fromEntries(evidenceEntries), null, 2)}
            </pre>
          </div>
        )}
      </div>
    </article>
  );
}
