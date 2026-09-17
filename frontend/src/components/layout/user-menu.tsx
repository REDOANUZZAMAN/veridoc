"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { KeyRound, LogOut, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiPost } from "@/lib/client";
import type { SessionUser } from "@/lib/types";

export function UserMenu({ user }: { user: SessionUser }) {
  const router = useRouter();
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);

  async function signOut() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
  }

  async function changePassword() {
    setBusy(true);
    try {
      await apiPost("/auth/change-password", { current_password: current, new_password: next });
      toast.success("Password updated");
      setPasswordOpen(false);
      setCurrent("");
      setNext("");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not change the password");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" className="h-9 gap-2 pl-1.5 pr-2.5">
            <Avatar className="size-6">
              <AvatarFallback>{user.initials ?? user.full_name.slice(0, 2)}</AvatarFallback>
            </Avatar>
            <span className="hidden text-xs font-medium sm:inline">{user.full_name}</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent className="w-64" align="end">
          <DropdownMenuLabel>Signed in</DropdownMenuLabel>
          <div className="space-y-1.5 px-2 pb-2">
            <p className="text-xs font-medium">{user.full_name}</p>
            <p className="text-2xs text-muted-foreground">{user.email}</p>
            <div className="flex flex-wrap items-center gap-1 pt-0.5">
              <Badge variant="default">
                <ShieldCheck className="size-3" />
                {user.role_label ?? user.role_name}
              </Badge>
              <Badge variant="muted">{user.permissions.length} permissions</Badge>
            </div>
            {user.job_title && (
              <p className="text-2xs text-muted-foreground">
                {user.job_title}
                {user.team ? ` · ${user.team}` : ""}
              </p>
            )}
          </div>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => setPasswordOpen(true)}>
            <KeyRound /> Change password
          </DropdownMenuItem>
          <DropdownMenuItem onClick={signOut}>
            <LogOut /> Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={passwordOpen} onOpenChange={setPasswordOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Change password</DialogTitle>
            <DialogDescription>
              Minimum ten characters with an uppercase letter, a digit and a symbol.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="current-password">Current password</Label>
              <Input
                id="current-password"
                type="password"
                value={current}
                onChange={(event) => setCurrent(event.target.value)}
                autoComplete="current-password"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="new-password">New password</Label>
              <Input
                id="new-password"
                type="password"
                value={next}
                onChange={(event) => setNext(event.target.value)}
                autoComplete="new-password"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPasswordOpen(false)}>
              Cancel
            </Button>
            <Button onClick={changePassword} disabled={busy || !current || next.length < 10}>
              {busy ? "Saving…" : "Update password"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
