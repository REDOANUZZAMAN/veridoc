"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, useTransition } from "react";
import { AlertCircle, ArrowRight, Eye, EyeOff, Loader2 } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/**
 * Role reference for the demo environment. Emails only — no password is ever
 * shown on or pre-filled into this page, so the credential still has to be
 * typed by whoever is signing in.
 */
const DEMO_ACCOUNTS = [
  { email: "investigator@veridoc.example", role: "Fraud Investigator", note: "Reviews findings, escalates, runs verification" },
  { email: "claims@veridoc.example", role: "Claims Officer", note: "Creates claims, uploads, records the decision" },
  { email: "reviewer@veridoc.example", role: "Reviewer", note: "Second-line review of machine findings" },
  { email: "admin@veridoc.example", role: "Administrator", note: "Rules, providers, thresholds, users, audit" },
];

export function LoginForm({ nextPath, demoMode }: { nextPath?: string; demoMode: boolean }) {
  const router = useRouter();
  const passwordRef = useRef<HTMLInputElement>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [reveal, setReveal] = useState(false);
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
    <div className="space-y-6">
      <form onSubmit={onSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="email">Work email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="username"
            required
            autoFocus
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="name@insurer.example"
            className="h-11"
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="password">Password</Label>
          <div className="relative">
            <Input
              id="password"
              ref={passwordRef}
              type={reveal ? "text" : "password"}
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Enter your password"
              className="h-11 pr-11"
            />
            <button
              type="button"
              onClick={() => setReveal((shown) => !shown)}
              aria-label={reveal ? "Hide password" : "Show password"}
              className="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-r-lg text-muted-foreground transition-colors hover:text-foreground"
            >
              {reveal ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>
        </div>

        {error && (
          <Alert variant="danger">
            <AlertCircle />
            <AlertDescription className="text-foreground">{error}</AlertDescription>
          </Alert>
        )}

        <Button type="submit" size="lg" className="w-full" disabled={busy}>
          {busy ? <Loader2 className="size-4 animate-spin" /> : null}
          {busy ? "Signing in…" : "Sign in"}
          {!busy && <ArrowRight className="size-4" />}
        </Button>
      </form>

      {demoMode && (
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <span className="eyebrow shrink-0">Demo roles</span>
            <span className="h-px flex-1 bg-border" />
          </div>
          <ul className="grid gap-1.5">
            {DEMO_ACCOUNTS.map((account) => (
              <li key={account.email}>
                <button
                  type="button"
                  title={account.note}
                  onClick={() => {
                    setEmail(account.email);
                    passwordRef.current?.focus();
                  }}
                  className="flex w-full items-baseline justify-between gap-3 rounded-lg border border-transparent bg-surface px-3 py-2 text-left transition-colors hover:border-primary/30 hover:bg-accent/60"
                >
                  <span className="shrink-0 text-2xs font-semibold">{account.role}</span>
                  <span className="truncate font-mono text-2xs text-muted-foreground">
                    {account.email}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          <p className="text-2xs leading-relaxed text-muted-foreground">
            Selecting a role fills the email field only. Roles differ in what they may do: a
            Reviewer cannot escalate or decide, a Claims Officer cannot adjudicate findings, and
            only an Administrator can retune rules.
          </p>
        </div>
      )}
    </div>
  );
}
