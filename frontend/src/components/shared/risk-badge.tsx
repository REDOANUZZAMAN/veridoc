import { cn } from "@/lib/utils";
import { RISK_BAND_LABEL, bandTone } from "@/lib/format";
import type { RiskBand } from "@/lib/types";

/**
 * The risk band, always shown with its score and never on its own as a verdict.
 * Wording comes from one place so "High Concern" can never drift into
 * "fraudulent" anywhere in the product.
 */
export function RiskBadge({
  band,
  score,
  size = "default",
  className,
}: {
  band?: RiskBand | null;
  score?: number | null;
  size?: "default" | "sm" | "lg";
  className?: string;
}) {
  const tone = bandTone(band);
  const label = band ? RISK_BAND_LABEL[band] : "Not assessed";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 whitespace-nowrap rounded-full border font-medium",
        tone.bg,
        tone.border,
        tone.text,
        size === "sm" && "px-2 py-0.5 text-2xs",
        size === "default" && "px-2.5 py-1 text-xs",
        size === "lg" && "px-3.5 py-1.5 text-sm",
        className,
      )}
    >
      <span className={cn("size-1.5 rounded-full", tone.dot)} aria-hidden />
      {label}
      {score !== null && score !== undefined && (
        <span className="tabular font-semibold opacity-90">{score}/100</span>
      )}
    </span>
  );
}

export function RiskScoreMeter({ score, band }: { score: number; band: RiskBand }) {
  const tone = bandTone(band);
  return (
    <div className="space-y-1.5">
      <div className="relative h-2.5 w-full overflow-hidden rounded-full bg-muted ring-1 ring-inset ring-border/60">
        <div
          className={cn("h-full rounded-full transition-all duration-500", tone.dot)}
          style={{ width: `${Math.max(2, Math.min(100, score))}%` }}
        />
        {/* Band thresholds sit on the track so the score reads against them. */}
        {[40, 75].map((threshold) => (
          <span
            key={threshold}
            aria-hidden
            className="absolute top-0 h-full w-px bg-card/70"
            style={{ left: `${threshold}%` }}
          />
        ))}
      </div>
      <div className="flex justify-between text-2xs text-muted-foreground">
        <span>0 · Low Concern</span>
        <span>40 · Review</span>
        <span>75 · High Concern</span>
      </div>
    </div>
  );
}
