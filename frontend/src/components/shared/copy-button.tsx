"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function CopyButton({
  value,
  label,
  className,
}: {
  value: string;
  label?: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-sm"
      className={cn("text-muted-foreground", className)}
      title={label ?? "Copy"}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setCopied(true);
          setTimeout(() => setCopied(false), 1400);
        } catch {
          /* clipboard unavailable */
        }
      }}
    >
      {copied ? <Check className="size-3.5 text-risk-low" /> : <Copy className="size-3.5" />}
      <span className="sr-only">{label ?? "Copy value"}</span>
    </Button>
  );
}

export function HashValue({ value, className }: { value?: string | null; className?: string }) {
  if (!value) return <span className="text-muted-foreground">—</span>;
  return (
    <span className={cn("inline-flex items-center gap-1", className)}>
      <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-2xs">{value.slice(0, 16)}…</code>
      <CopyButton value={value} label="Copy full hash" />
    </span>
  );
}
