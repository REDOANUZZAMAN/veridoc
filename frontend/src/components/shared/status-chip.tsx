import {
  AlertOctagon, CheckCircle2, CircleDashed, Clock, FileSearch, Loader2, ShieldX, XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { CLAIM_STATUS_LABEL, PROCESSING_STATUS_LABEL, VERIFICATION_STATE_LABEL, humanise } from "@/lib/format";

type Variant = "default" | "secondary" | "outline" | "muted" | "low" | "review" | "high" | "success" | "destructive";

const PROCESSING: Record<string, { variant: Variant; icon: typeof Clock }> = {
  uploaded: { variant: "muted", icon: CircleDashed },
  queued: { variant: "secondary", icon: Clock },
  processing: { variant: "default", icon: Loader2 },
  analyzed: { variant: "low", icon: CheckCircle2 },
  partial: { variant: "review", icon: AlertOctagon },
  failed: { variant: "high", icon: XCircle },
  quarantined: { variant: "high", icon: ShieldX },
};

export function ProcessingStatusChip({ status }: { status: string }) {
  const config = PROCESSING[status] ?? { variant: "muted" as Variant, icon: CircleDashed };
  const Icon = config.icon;
  return (
    <Badge variant={config.variant}>
      <Icon className={status === "processing" ? "size-3 animate-spin" : "size-3"} />
      {PROCESSING_STATUS_LABEL[status] ?? humanise(status)}
    </Badge>
  );
}

const CLAIM: Record<string, Variant> = {
  submitted: "muted",
  processing: "secondary",
  verified: "low",
  review_required: "review",
  investigation: "high",
  resolved: "default",
};

export function ClaimStatusChip({ status }: { status: string }) {
  return (
    <Badge variant={CLAIM[status] ?? "muted"}>
      {CLAIM_STATUS_LABEL[status] ?? humanise(status)}
    </Badge>
  );
}

const VERIFICATION: Record<string, Variant> = {
  unverified: "muted",
  in_review: "secondary",
  verified: "low",
  information_requested: "review",
  rejected: "high",
};

export function VerificationStateChip({ state }: { state: string }) {
  return (
    <Badge variant={VERIFICATION[state] ?? "muted"}>
      {state === "verified" && <CheckCircle2 className="size-3" />}
      {VERIFICATION_STATE_LABEL[state] ?? humanise(state)}
    </Badge>
  );
}

const OUTCOME: Record<string, Variant> = {
  match: "low",
  partial_match: "review",
  mismatch: "high",
  not_found: "high",
  unavailable: "muted",
};

export function OutcomeChip({ outcome }: { outcome: string }) {
  return <Badge variant={OUTCOME[outcome] ?? "muted"}>{humanise(outcome)}</Badge>;
}

const INVESTIGATION: Record<string, Variant> = {
  open: "review",
  in_progress: "default",
  pending_information: "secondary",
  escalated: "high",
  closed: "muted",
};

export function InvestigationStatusChip({ status }: { status: string }) {
  return (
    <Badge variant={INVESTIGATION[status] ?? "muted"}>
      {status === "escalated" && <FileSearch className="size-3" />}
      {humanise(status)}
    </Badge>
  );
}

const PRIORITY: Record<string, Variant> = {
  low: "muted",
  medium: "secondary",
  high: "review",
  critical: "high",
};

export function PriorityChip({ priority }: { priority: string }) {
  return <Badge variant={PRIORITY[priority] ?? "muted"}>{humanise(priority)}</Badge>;
}
