import { Scale } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * The standing caveat. It is a component rather than copied prose so that the
 * platform's central limitation is stated identically on every screen that
 * shows a machine judgement.
 */
export function UncertaintyNote({
  children,
  className,
  icon = true,
}: {
  children?: React.ReactNode;
  className?: string;
  icon?: boolean;
}) {
  return (
    <p
      className={cn(
        "flex gap-2 rounded-md border border-dashed bg-muted/40 px-3 py-2 text-2xs leading-relaxed text-muted-foreground",
        className,
      )}
    >
      {icon && <Scale className="mt-0.5 size-3.5 shrink-0" aria-hidden />}
      <span>
        {children ??
          `Findings are investigative signals, not conclusions. Forensic and synthetic-media
           indicators are probabilistic and have legitimate alternative explanations; rule
           findings depend on extraction accuracy. No score here determines whether a document
           is genuine — that decision is recorded by a named reviewer.`}
      </span>
    </p>
  );
}

export function ProvenanceLegend({ className }: { className?: string }) {
  const items = [
    ["Measured", "Deterministic forensic measurement of the file"],
    ["Rule", "Deterministic rule over extracted values"],
    ["Model", "Probabilistic model inference"],
    ["External", "Answer from a trusted source (demo or production)"],
    ["Human", "Decision recorded by a named reviewer"],
  ];
  return (
    <div className={cn("flex flex-wrap gap-x-4 gap-y-1 text-2xs text-muted-foreground", className)}>
      {items.map(([label, description]) => (
        <span key={label}>
          <span className="font-semibold text-foreground/80">{label}</span> · {description}
        </span>
      ))}
    </div>
  );
}
