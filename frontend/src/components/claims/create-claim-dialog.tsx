"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2, Plus } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { apiPost } from "@/lib/client";

export function CreateClaimDialog() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    customer_name: "",
    policy_number: "",
    claim_type: "health",
    customer_dob: "",
    customer_email: "",
    incident_date: "",
    claimed_amount: "",
    currency: "USD",
    summary: "",
  });

  const update = (key: keyof typeof form) => (value: string) =>
    setForm((current) => ({ ...current, [key]: value }));

  async function submit() {
    setBusy(true);
    try {
      const claim = await apiPost<{ id: string; claim_number: string }>("/claims", {
        ...form,
        customer_dob: form.customer_dob || null,
        customer_email: form.customer_email || null,
        incident_date: form.incident_date || null,
        claimed_amount: form.claimed_amount || null,
        summary: form.summary || null,
      });
      toast.success(`${claim.claim_number} created`, {
        description: "Upload the supporting documents to start analysis.",
      });
      setOpen(false);
      router.push(`/claims/${claim.id}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "The claim could not be created");
    } finally {
      setBusy(false);
    }
  }

  const valid = form.customer_name.trim().length > 1 && form.policy_number.trim().length > 2;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus className="size-4" /> New claim
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Create claim</DialogTitle>
          <DialogDescription>
            The claim record is what supporting documents are compared against — the policy number,
            the named customer and the amount claimed all feed cross-document checks and
            trusted-source verification.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="customer_name">Customer name *</Label>
            <Input
              id="customer_name"
              value={form.customer_name}
              onChange={(event) => update("customer_name")(event.target.value)}
              placeholder="Amelia R. Okonkwo"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="policy_number">Policy number *</Label>
            <Input
              id="policy_number"
              value={form.policy_number}
              onChange={(event) => update("policy_number")(event.target.value)}
              placeholder="POL-938472"
              className="font-mono"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="claim_type">Claim type</Label>
            <Select value={form.claim_type} onValueChange={update("claim_type")}>
              <SelectTrigger id="claim_type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="health">Health</SelectItem>
                <SelectItem value="motor">Motor</SelectItem>
                <SelectItem value="travel">Travel</SelectItem>
                <SelectItem value="property">Property</SelectItem>
                <SelectItem value="liability">Liability</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="customer_dob">Customer date of birth</Label>
            <Input
              id="customer_dob"
              type="date"
              value={form.customer_dob}
              onChange={(event) => update("customer_dob")(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="incident_date">Incident date</Label>
            <Input
              id="incident_date"
              type="date"
              value={form.incident_date}
              onChange={(event) => update("incident_date")(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="claimed_amount">Amount claimed</Label>
            <div className="flex gap-2">
              <Input
                id="claimed_amount"
                inputMode="decimal"
                value={form.claimed_amount}
                onChange={(event) => update("claimed_amount")(event.target.value)}
                placeholder="4820.00"
                className="tabular"
              />
              <Select value={form.currency} onValueChange={update("currency")}>
                <SelectTrigger className="w-24">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {["USD", "EUR", "GBP", "SGD", "AUD", "INR", "BDT"].map((code) => (
                    <SelectItem key={code} value={code}>
                      {code}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="customer_email">Customer email</Label>
            <Input
              id="customer_email"
              type="email"
              value={form.customer_email}
              onChange={(event) => update("customer_email")(event.target.value)}
            />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="summary">Summary</Label>
            <Textarea
              id="summary"
              rows={3}
              value={form.summary}
              onChange={(event) => update("summary")(event.target.value)}
              placeholder="What is being claimed, and for what event?"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={busy || !valid}>
            {busy && <Loader2 className="size-4 animate-spin" />}
            Create claim
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
