import type { RiskBand, Severity } from "@/lib/types";

export const RISK_BAND_LABEL: Record<RiskBand, string> = {
  low_concern: "Low Concern",
  review_recommended: "Review Recommended",
  high_concern: "High Concern",
};

export const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low", "info"];

export function bandTone(band?: RiskBand | null) {
  switch (band) {
    case "high_concern":
      return { text: "text-risk-high", bg: "bg-risk-high/10", border: "border-risk-high/35", dot: "bg-risk-high" };
    case "review_recommended":
      return { text: "text-risk-review", bg: "bg-risk-review/10", border: "border-risk-review/35", dot: "bg-risk-review" };
    case "low_concern":
      return { text: "text-risk-low", bg: "bg-risk-low/10", border: "border-risk-low/35", dot: "bg-risk-low" };
    default:
      return { text: "text-muted-foreground", bg: "bg-muted", border: "border-border", dot: "bg-muted-foreground" };
  }
}

export function severityTone(severity?: Severity | string | null) {
  switch (severity) {
    case "critical":
      return { text: "text-risk-high", bg: "bg-risk-high/15", border: "border-risk-high/40" };
    case "high":
      return { text: "text-risk-high", bg: "bg-risk-high/10", border: "border-risk-high/30" };
    case "medium":
      return { text: "text-risk-review", bg: "bg-risk-review/10", border: "border-risk-review/30" };
    case "low":
      return { text: "text-primary", bg: "bg-primary/10", border: "border-primary/25" };
    default:
      return { text: "text-muted-foreground", bg: "bg-muted", border: "border-border" };
  }
}

export function humanise(value?: string | null): string {
  if (!value) return "—";
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function formatBytes(bytes?: number | null): string {
  if (!bytes && bytes !== 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatMoney(amount?: string | number | null, currency = "USD"): string {
  if (amount === null || amount === undefined || amount === "") return "—";
  const value = typeof amount === "string" ? Number.parseFloat(amount) : amount;
  if (Number.isNaN(value)) return String(amount);
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatDate(value?: string | null, withTime = false): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-GB", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  });
}

export function relativeTime(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value).getTime();
  if (Number.isNaN(date)) return value;
  const seconds = Math.round((date - Date.now()) / 1000);
  const units: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ["year", 31536000],
    ["month", 2592000],
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
    ["second", 1],
  ];
  const formatter = new Intl.RelativeTimeFormat("en-GB", { numeric: "auto" });
  for (const [unit, secondsInUnit] of units) {
    if (Math.abs(seconds) >= secondsInUnit || unit === "second") {
      return formatter.format(Math.round(seconds / secondsInUnit), unit);
    }
  }
  return value;
}

export function percent(value?: number | null, digits = 0): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function truncateHash(hash?: string | null, size = 10): string {
  if (!hash) return "—";
  return `${hash.slice(0, size)}…${hash.slice(-4)}`;
}

export const PROCESSING_STATUS_LABEL: Record<string, string> = {
  uploaded: "Uploaded",
  queued: "Queued",
  processing: "Processing",
  analyzed: "Analysed",
  partial: "Partial coverage",
  failed: "Failed",
  quarantined: "Quarantined",
};

export const CLAIM_STATUS_LABEL: Record<string, string> = {
  submitted: "Submitted",
  processing: "Processing",
  verified: "Verified",
  review_required: "Review Required",
  investigation: "Investigation",
  resolved: "Resolved",
};

export const VERIFICATION_STATE_LABEL: Record<string, string> = {
  unverified: "Unverified",
  in_review: "In review",
  verified: "Verified",
  information_requested: "Information requested",
  rejected: "Rejected",
};

export const OUTCOME_LABEL: Record<string, string> = {
  match: "Match",
  partial_match: "Partial match",
  mismatch: "Mismatch",
  not_found: "Not found",
  unavailable: "Unavailable",
};

export const PROVENANCE_LABEL: Record<string, string> = {
  model_inference: "Model inference",
  automated_measurement: "Measured",
  automated_correlation: "Correlated",
  deterministic_rule: "Rule",
};
