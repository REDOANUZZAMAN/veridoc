"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { AlertCircle, ArrowRight, Loader2 } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const DEMO_ACCOUNTS = [
  { email: "investigator@veridoc.example", role: "Fraud Investigator", note: "Reviews findings, escalates, runs verification" },
  { email: "claims@veridoc.example", role: "Claims Officer", note: "Creates claims, uploads, records the decision" },
  { email: "reviewer@veridoc.example", role: "Reviewer", note: "Second-line review of machine findings" },
  { email: "admin@veridoc.example", role: "Administrator", note: "Rules, providers, thresholds, users, audit" },
];

export function LoginForm({ nextPath, demoMode }: { nextPath?: string; demoMode: boolean }) {
  const router = useRouter();
  const [email, setEmail] = useState("investigator@veridoc.example");
  const [password, setPassword] = useState(demoMode ? "Demo!2026" : "");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        setError(body?.error?.message ?? "Sign-in failed. Please try again.");
        setSubmitting(false);
        return;
      }
      startTransition(() => {
        router.replace(nextPath && nextPath.startsWith("/") ? nextPath : "/dashboard");
        router.refresh();
      });
    } catch {
      setError("Could not reach the service. Check that the API is running.");
      setSubmitting(false);
    }
  }

  const busy = submitting || pending;

  return (
    <div className="space-y-5">
      <form onSubmit={onSubmit} className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="email">Work email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="name@insurer.example"
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>

        {error && (
          <Alert variant="danger">
            <AlertCircle />
            <AlertDescription className="text-foreground">{error}</AlertDescription>
          </Alert>
        )}

        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? <Loader2 className="size-4 animate-spin" /> : <ArrowRight className="size-4" />}
          {busy ? "Signing in…" : "Sign in"}
        </Button>
      </form>

      {demoMode && (
        <div className="space-y-2 rounded-md border border-dashed bg-muted/40 p-3">
          <p className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
            Demo accounts · password Demo!2026
          </p>
          <ul className="space-y-1">
            {DEMO_ACCOUNTS.map((account) => (
              <li key={account.email}>
                <button
                  type="button"
                  onClick={() => {
                    setEmail(account.email);
                    setPassword("Demo!2026");
                  }}
                  className="w-full rounded px-1.5 py-1 text-left transition-colors hover:bg-accent"
                >
                  <span className="block text-2xs font-medium">{account.role}</span>
                  <span className="block font-mono text-2xs text-muted-foreground">
                    {account.email}
                  </span>
                  <span className="block text-2xs text-muted-foreground/80">{account.note}</span>
                </button>
              </li>
            ))}
          </ul>
          <p className="text-2xs leading-relaxed text-muted-foreground">
            Roles differ in what they may do: a Reviewer cannot escalate or decide, a Claims Officer
            cannot adjudicate findings, and only an Administrator can retune rules.
          </p>
        </div>
      )}
    </div>
  );
}
