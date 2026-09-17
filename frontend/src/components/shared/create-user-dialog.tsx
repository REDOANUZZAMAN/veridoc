"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2, UserPlus } from "lucide-react";
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
import { apiPost } from "@/lib/client";

export function CreateUserDialog({
  roles,
}: {
  roles: Array<{ name: string; label: string; description: string }>;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    email: "", full_name: "", role_name: "reviewer", password: "", job_title: "", team: "",
  });

  const update = (key: keyof typeof form) => (value: string) =>
    setForm((current) => ({ ...current, [key]: value }));

  const strong =
    form.password.length >= 10 &&
    /[A-Z]/.test(form.password) &&
    /\d/.test(form.password) &&
    /[^A-Za-z0-9]/.test(form.password);

  async function submit() {
    setBusy(true);
    try {
      await apiPost("/users", {
        ...form,
        job_title: form.job_title || null,
        team: form.team || null,
      });
      toast.success(`${form.email} created`, {
        description: "The account must change its password at first sign-in.",
      });
      setOpen(false);
      setForm({ email: "", full_name: "", role_name: "reviewer", password: "", job_title: "", team: "" });
      router.refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "The account could not be created");
    } finally {
      setBusy(false);
    }
  }

  const selected = roles.find((role) => role.name === form.role_name);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <UserPlus className="size-4" /> New user
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Create a user</DialogTitle>
          <DialogDescription>
            The role decides what the account may do; authorisation is enforced on every endpoint,
            not just in the interface.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="user-email">Work email *</Label>
            <Input
              id="user-email"
              type="email"
              value={form.email}
              onChange={(event) => update("email")(event.target.value)}
              placeholder="name@insurer.example"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="user-name">Full name *</Label>
            <Input
              id="user-name"
              value={form.full_name}
              onChange={(event) => update("full_name")(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="user-role">Role *</Label>
            <Select value={form.role_name} onValueChange={update("role_name")}>
              <SelectTrigger id="user-role">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {roles.map((role) => (
                  <SelectItem key={role.name} value={role.name}>
                    {role.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="user-title">Job title</Label>
            <Input
              id="user-title"
              value={form.job_title}
              onChange={(event) => update("job_title")(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="user-team">Team</Label>
            <Input
              id="user-team"
              value={form.team}
              onChange={(event) => update("team")(event.target.value)}
            />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="user-password">Initial password *</Label>
            <Input
              id="user-password"
              type="password"
              value={form.password}
              onChange={(event) => update("password")(event.target.value)}
            />
            <p className="text-2xs text-muted-foreground">
              At least 10 characters with an uppercase letter, a digit and a symbol. The account is
              forced to change it at first sign-in.
            </p>
          </div>
        </div>

        {selected && (
          <p className="rounded-md border bg-muted/40 p-2.5 text-2xs leading-relaxed text-muted-foreground">
            <span className="font-semibold text-foreground">{selected.label}: </span>
            {selected.description}
          </p>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>
            Cancel
          </Button>
          <Button
            onClick={submit}
            disabled={busy || !form.email || form.full_name.length < 2 || !strong}
          >
            {busy && <Loader2 className="size-4 animate-spin" />}
            Create user
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
