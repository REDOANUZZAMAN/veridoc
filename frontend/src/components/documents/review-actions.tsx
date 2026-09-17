"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  CheckCircle2, FileText, Gavel, Loader2, MessageSquareWarning, RefreshCw, ShieldAlert,
  ThumbsDown, ThumbsUp, XCircle,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { apiPost } from "@/lib/client";
import type { Finding } from "@/lib/types";

const MIN_REASON = 10;

type ActionKey =
  | "confirm_finding"
  | "dismiss_finding"
  | "request_information"
  | "mark_document_verified"
  | "reject_document"
  | "escalate_investigation";

const ACTION_COPY: Record<ActionKey, { title: string; description: string; verb: string }> = {
  confirm_finding: {
    title: "Confirm finding",
    description:
      "Records that you consider this signal established. It will be treated as confirmed by the " +
      "risk engine and printed as a human finding in the report.",
    verb: "Confirm",
  },
  dismiss_finding: {
    title: "Dismiss finding",
    description:
      "Records that this signal has a benign explanation. It stops contributing to the risk score, " +
      "and your reason is kept with the finding permanently.",
    verb: "Dismiss",
  },
  request_information: {
    title: "Request more information",
    description:
      "Marks the document as awaiting information from the claimant or provider. Nothing is " +
      "decided by this action.",
    verb: "Request information",
  },
  mark_document_verified: {
    title: "Mark document verified",
    description:
      "Your verdict, not the platform's: it states that you are satisfied this document is what " +
      "it claims to be. Required before a claim can be cleared.",
    verb: "Mark verified",
  },
  reject_document: {
    title: "Reject document",
    description: "Records that this document cannot be accepted as evidence for the claim.",
    verb: "Reject",
  },
  escalate_investigation: {
    title: "Escalate to investigation",
    description:
      "Opens or escalates a case on the parent claim and moves the claim into investigation.",
    verb: "Escalate",
  },
};

export function ReviewActionBar({
  documentId,
  permissions,
  verificationState,
  hasClaim,
  openHighFindings,
}: {
  documentId: string;
  permissions: string[];
  verificationState: string;
  hasClaim: boolean;
  openHighFindings: number;
}) {
  const router = useRouter();
  const [action, setAction] = useState<ActionKey | null>(null);
  const [reason, setReason] = useState("");
  const [priority, setPriority] = useState("high");
  const [busy, setBusy] = useState(false);
  const can = (permission: string) => permissions.includes(permission);

  async function submit() {
    if (!action) return;
    setBusy(true);
    try {
      await apiPost(`/documents/${documentId}/review`, {
        action,
        reason,
        ...(action === "escalate_investigation" ? { escalate_priority: priority } : {}),
      });
      toast.success(`${ACTION_COPY[action].title} recorded`);
      setAction(null);
      setReason("");
      router.refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "The action could not be recorded");
    } finally {
      setBusy(false);
    }
  }

  async function reassess() {
    setBusy(true);
    try {
      const result = await apiPost<{ risk: { score: number; band_label: string } }>(
        `/documents/${documentId}/reassess`,
      );
      toast.success(
        `Reassessed: ${result.risk.score}/100 — ${result.risk.band_label}`,
        { description: "Dismissed findings are excluded; confirmed findings are treated as established." },
      );
      router.refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Reassessment failed");
    } finally {
      setBusy(false);
    }
  }

  async function reanalyse() {
    setBusy(true);
    try {
      await apiPost(`/documents/${documentId}/analyze`, { force: true, reason: "Manual re-run" });
      toast.success("Analysis queued", {
        description: "Existing human decisions are preserved across reprocessing.",
      });
      setTimeout(() => router.refresh(), 1500);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not queue analysis");
    } finally {
      setBusy(false);
    }
  }

  async function generateReport() {
    setBusy(true);
    try {
      const report = await apiPost<{ id: string; report_ref: string }>("/reports", {
        document_id: documentId,
      });
      toast.success(`${report.report_ref} generated`, {
        description: "Open it from the Reports screen or download the PDF.",
        action: {
          label: "Download",
          onClick: () => window.open(`/api/be/reports/${report.id}/export`, "_blank"),
        },
      });
      router.refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Report generation failed");
    } finally {
      setBusy(false);
    }
  }

  const reasonTooShort = reason.trim().length < MIN_REASON;

  return (
    <>
      <div className="flex flex-wrap items-center gap-1.5">
        {can("document:verify") && verificationState !== "verified" && (
          <Button size="sm" onClick={() => setAction("mark_document_verified")}>
            <CheckCircle2 className="size-4" /> Mark verified
          </Button>
        )}
        {can("finding:request_info") && (
          <Button variant="outline" size="sm" onClick={() => setAction("request_information")}>
            <MessageSquareWarning className="size-4" /> Request information
          </Button>
        )}
        {can("investigation:escalate") && hasClaim && (
          <Button variant="outline" size="sm" onClick={() => setAction("escalate_investigation")}>
            <ShieldAlert className="size-4" /> Escalate
          </Button>
        )}
        {can("document:verify") && verificationState !== "rejected" && (
          <Button variant="outline" size="sm" onClick={() => setAction("reject_document")}>
            <XCircle className="size-4" /> Reject
          </Button>
        )}
        {can("document:analyze") && (
          <>
            <Button variant="subtle" size="sm" onClick={reassess} disabled={busy}>
              <Gavel className="size-4" /> Recompute risk
            </Button>
            <Button variant="subtle" size="sm" onClick={reanalyse} disabled={busy}>
              <RefreshCw className="size-4" /> Re-run analysis
            </Button>
          </>
        )}
        {can("report:generate") && (
          <Button variant="outline" size="sm" onClick={generateReport} disabled={busy}>
            {busy ? <Loader2 className="size-4 animate-spin" /> : <FileText className="size-4" />}
            Generate report
          </Button>
        )}
      </div>

      <Dialog open={action !== null} onOpenChange={(open) => !open && setAction(null)}>
        <DialogContent className="max-w-lg">
          {action && (
            <>
              <DialogHeader>
                <DialogTitle>{ACTION_COPY[action].title}</DialogTitle>
                <DialogDescription>{ACTION_COPY[action].description}</DialogDescription>
              </DialogHeader>

              {action === "mark_document_verified" && openHighFindings > 0 && (
                <p className="rounded-md border border-risk-review/30 bg-risk-review/8 p-2.5 text-2xs leading-relaxed">
                  {openHighFindings} high or critical finding{openHighFindings === 1 ? " is" : "s are"}{" "}
                  still awaiting adjudication on this document. Verifying it now is permitted, but
                  your reason should explain why those signals do not prevent acceptance.
                </p>
              )}

              {action === "escalate_investigation" && (
                <div className="space-y-1.5">
                  <Label htmlFor="priority">Case priority</Label>
                  <Select value={priority} onValueChange={setPriority}>
                    <SelectTrigger id="priority">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="low">Low</SelectItem>
                      <SelectItem value="medium">Medium</SelectItem>
                      <SelectItem value="high">High</SelectItem>
                      <SelectItem value="critical">Critical</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              )}

              <div className="space-y-1.5">
                <Label htmlFor="reason">
                  Reason {action === "request_information" ? "(optional)" : "(required)"}
                </Label>
                <Textarea
                  id="reason"
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  rows={4}
                  placeholder="State what you checked and what you concluded. This is kept permanently with the document."
                />
                <p className="text-2xs text-muted-foreground">
                  {reason.trim().length}/{MIN_REASON} characters minimum · recorded against your name
                  in the audit trail
                </p>
              </div>

              <DialogFooter>
                <Button variant="outline" onClick={() => setAction(null)} disabled={busy}>
                  Cancel
                </Button>
                <Button
                  onClick={submit}
                  disabled={busy || (action !== "request_information" && reasonTooShort)}
                >
                  {busy && <Loader2 className="size-4 animate-spin" />}
                  {ACTION_COPY[action].verb}
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

/** Confirm / dismiss controls attached to a single finding. */
export function FindingReviewButtons({
  documentId,
  finding,
  permissions,
}: {
  documentId: string;
  finding: Finding;
  permissions: string[];
}) {
  const router = useRouter();
  const [mode, setMode] = useState<"confirm_finding" | "dismiss_finding" | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const canConfirm = permissions.includes("finding:confirm");
  const canDismiss = permissions.includes("finding:dismiss");
  if (!canConfirm && !canDismiss) return null;

  async function submit() {
    if (!mode) return;
    setBusy(true);
    try {
      await apiPost(`/documents/${documentId}/review`, {
        action: mode,
        finding_id: finding.finding_id,
        reason,
      });
      toast.success(mode === "confirm_finding" ? "Finding confirmed" : "Finding dismissed", {
        description: "Use “Recompute risk” to fold the decision into the score.",
      });
      setMode(null);
      setReason("");
      router.refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "The decision could not be recorded");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {canConfirm && finding.status !== "confirmed" && (
        <Button variant="ghost" size="xs" onClick={() => setMode("confirm_finding")}>
          <ThumbsUp className="size-3" /> Confirm
        </Button>
      )}
      {canDismiss && finding.status !== "dismissed" && (
        <Button variant="ghost" size="xs" onClick={() => setMode("dismiss_finding")}>
          <ThumbsDown className="size-3" /> Dismiss
        </Button>
      )}

      <Dialog open={mode !== null} onOpenChange={(open) => !open && setMode(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {mode === "confirm_finding" ? "Confirm finding" : "Dismiss finding"}
            </DialogTitle>
            <DialogDescription>{finding.title}</DialogDescription>
          </DialogHeader>
          <p className="rounded-md border bg-muted/40 p-2.5 text-2xs leading-relaxed text-muted-foreground">
            {mode === "confirm_finding"
              ? "Confirming raises this signal's weight in the risk assessment and prints it as an established finding in the report."
              : "Dismissing removes this signal from the risk score. The finding itself is retained with your reason, and will survive reprocessing."}
          </p>
          <div className="space-y-1.5">
            <Label htmlFor="finding-reason">Reason (required)</Label>
            <Textarea
              id="finding-reason"
              rows={4}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="What did you check, and what did it show?"
            />
            <p className="text-2xs text-muted-foreground">
              {reason.trim().length}/{MIN_REASON} characters minimum
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setMode(null)} disabled={busy}>
              Cancel
            </Button>
            <Button onClick={submit} disabled={busy || reason.trim().length < MIN_REASON}>
              {busy && <Loader2 className="size-4 animate-spin" />}
              {mode === "confirm_finding" ? "Confirm" : "Dismiss"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
