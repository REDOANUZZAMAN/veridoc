"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2, MessageSquarePlus } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { apiPatch, apiPost } from "@/lib/client";

export function AddInvestigationNote({ investigationId }: { investigationId: string }) {
  const router = useRouter();
  const [body, setBody] = useState("");
  const [noteType, setNoteType] = useState("observation");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    try {
      await apiPost(`/investigations/${investigationId}/notes`, {
        body,
        note_type: noteType,
        is_internal: true,
      });
      toast.success("Note added");
      setBody("");
      router.refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "The note could not be saved");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2 p-4">
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-[160px] space-y-1.5">
          <Label htmlFor="note-type">Note type</Label>
          <Select value={noteType} onValueChange={setNoteType}>
            <SelectTrigger id="note-type">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="observation">Observation</SelectItem>
              <SelectItem value="contact">Contact with a party</SelectItem>
              <SelectItem value="evidence_request">Evidence request</SelectItem>
              <SelectItem value="decision_rationale">Decision rationale</SelectItem>
              <SelectItem value="referral">Referral</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="note-body">Note</Label>
        <Textarea
          id="note-body"
          rows={4}
          value={body}
          onChange={(event) => setBody(event.target.value)}
          placeholder="What did you do, who did you contact, and what did you learn?"
        />
      </div>
      <div className="flex justify-end">
        <Button size="sm" onClick={submit} disabled={busy || body.trim().length < 3}>
          {busy ? <Loader2 className="size-4 animate-spin" /> : <MessageSquarePlus className="size-4" />}
          Add note
        </Button>
      </div>
    </div>
  );
}

export function InvestigationStatusControl({
  investigationId,
  status,
  canClose,
}: {
  investigationId: string;
  status: string;
  canClose: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [resolution, setResolution] = useState("");
  const [reason, setReason] = useState("");

  async function change(next: string) {
    if (next === "closed" && reason.trim().length < 10) {
      toast.error("Closing a case needs a resolution reason of at least 10 characters");
      return;
    }
    setBusy(true);
    try {
      await apiPatch(`/investigations/${investigationId}`, {
        status: next,
        ...(next === "closed"
          ? { resolution: resolution || "resolved", resolution_reason: reason }
          : {}),
      });
      toast.success("Investigation updated");
      router.refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Update failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3 p-4">
      <div className="flex flex-wrap items-center gap-2">
        {["open", "in_progress", "pending_information", "escalated"].map((option) => (
          <Button
            key={option}
            size="sm"
            variant={status === option ? "secondary" : "outline"}
            disabled={busy || status === option}
            onClick={() => change(option)}
          >
            {option.replace(/_/g, " ")}
          </Button>
        ))}
      </div>

      {canClose && status !== "closed" && (
        <div className="space-y-2 rounded-md border border-dashed p-3">
          <p className="text-2xs font-semibold">Close this case</p>
          <div className="flex flex-wrap gap-2">
            <Select value={resolution} onValueChange={setResolution}>
              <SelectTrigger className="w-[190px]">
                <SelectValue placeholder="Resolution" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="no_further_action">No further action</SelectItem>
                <SelectItem value="substantiated">Substantiated</SelectItem>
                <SelectItem value="unsubstantiated">Unsubstantiated</SelectItem>
                <SelectItem value="refer">Referred onward</SelectItem>
                <SelectItem value="withdrawn">Withdrawn</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Textarea
            rows={3}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Resolution reason — what was established, and what happens next?"
          />
          <div className="flex justify-end">
            <Button
              size="sm"
              variant="outline"
              disabled={busy || reason.trim().length < 10 || !resolution}
              onClick={() => change("closed")}
            >
              Close case
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
