"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { UserPlus } from "lucide-react";
import { toast } from "sonner";

import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { apiPatch } from "@/lib/client";
import type { UserRef } from "@/lib/types";

const UNASSIGNED = "__unassigned__";

export function AssignInvestigator({
  claimId,
  current,
  investigators,
}: {
  claimId: string;
  current: UserRef | null;
  investigators: UserRef[];
}) {
  const router = useRouter();
  const [value, setValue] = useState(current?.id ?? UNASSIGNED);
  const [busy, setBusy] = useState(false);

  async function change(next: string) {
    setValue(next);
    setBusy(true);
    try {
      await apiPatch(`/claims/${claimId}`, {
        assigned_investigator_id: next === UNASSIGNED ? null : next,
      });
      toast.success("Assignment updated");
      router.refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not reassign");
      setValue(current?.id ?? UNASSIGNED);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Select value={value} onValueChange={change} disabled={busy}>
      <SelectTrigger className="h-8 w-[190px]">
        <UserPlus className="size-3.5 text-muted-foreground" />
        <SelectValue placeholder="Unassigned" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={UNASSIGNED}>Unassigned</SelectItem>
        {investigators.map((investigator) => (
          <SelectItem key={investigator.id} value={investigator.id}>
            {investigator.full_name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
