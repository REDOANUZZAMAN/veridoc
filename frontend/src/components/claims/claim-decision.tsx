"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { AlertTriangle, Gavel, Loader2 } from "lucide-react";
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

const DECISIONS = [
  { value: "approve", label: "Approve", note: "Settle the claim as submitted." },
  { value: "decline", label: "Decline", note: "Refuse the claim, with the reason recorded." },
  { value: "refer", label: "Refer", note: "Pass to another team for specialist assessment." },
  { value: "withdraw", label: "Withdraw", note: "The claimant has withdrawn the claim." },
];

/**
 * The final human decision.
 *
 * Deliberately a distinct, deliberate action with a mandatory written reason:
 * nothing the analysis pipeline produces can put a claim into this state on its
 * own, and the server refuses an approval while high-severity findings remain
 * unadjudicated.
 */
export function ClaimDecisionDialog({
  claimId,
  claimNumber,
  openHighFindings,
}: {
  claimId: string;
  claimNumber: string;
  openHighFindings: number;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [decision, setDecision] = useState("approve");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    try {
      await apiPost(`/claims/${claimId}/decision`, {
        decision,
        reason,
        close_investigations: true,
      });
      toast.success(`Decision recorded for ${claimNumber}`);
      setOpen(false);
      router.refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "The decision could not be recorded", {
        description:
          error instanceof Error && error.message.includes("unreviewed")
            ? "Confirm or dismiss the outstanding high-severity findings first."
            : undefined,
      });
    } finally {
      setBusy(false);
    }
  }

  const selected = DECISIONS.find((item) => item.value === decision);

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        <Gavel className="size-4" /> Record decision
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Record the claim decision</DialogTitle>
            <DialogDescription>
              {claimNumber} · this is the authoritative outcome of the claim and is attributed to
              you in the audit trail.
            </DialogDescription>
          </DialogHeader>

          {openHighFindings > 0 && (
            <div className="flex gap-2 rounded-md border border-risk-review/30 bg-risk-review/8 p-2.5">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-risk-review" />
              <p className="text-2xs leading-relaxed">
                {openHighFindings} high or critical finding{openHighFindings === 1 ? "" : "s"} across
                this claim {openHighFindings === 1 ? "has" : "have"} not been adjudicated. Approval
                will be refused until each one is confirmed or dismissed with a reason — machine
                findings must not become a decision by default.
              </p>
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="decision">Decision</Label>
            <Select value={decision} onValueChange={setDecision}>
              <SelectTrigger id="decision">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DECISIONS.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-2xs text-muted-foreground">{selected?.note}</p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="decision-reason">Reason (required)</Label>
            <Textarea
              id="decision-reason"
              rows={5}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Summarise the evidence relied on and how the outstanding findings were resolved."
            />
            <p className="text-2xs text-muted-foreground">{reason.trim().length}/12 minimum</p>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button onClick={submit} disabled={busy || reason.trim().length < 12}>
              {busy && <Loader2 className="size-4 animate-spin" />}
              Record {selected?.label.toLowerCase()}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
