import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { FileSearch, GitCompareArrows, Lock, ScanEye, ShieldCheck } from "lucide-react";

import { LoginForm } from "@/app/login/login-form";
import { APP_NAME, DEMO_MODE } from "@/lib/config";
import { getSessionUser } from "@/lib/session";

export const metadata: Metadata = { title: "Sign in" };

const CAPABILITIES = [
  {
    icon: ScanEye,
    title: "Forensic measurement",
    body: "PDF object structure, metadata provenance, typography, and pixel-level analysis of embedded rasters.",
  },
  {
    icon: GitCompareArrows,
    title: "Consistency & cross-document checks",
    body: "Deterministic rules over extracted fields, and field-by-field comparison across a claim bundle.",
  },
  {
    icon: ShieldCheck,
    title: "Trusted-source verification",
    body: "Policy, provider, invoice, identity, vehicle and settlement lookups — each labelled with its data source.",
  },
  {
    icon: FileSearch,
    title: "Human adjudication",
    body: "Every machine finding is confirmed or dismissed by a named reviewer, with a written reason, before a claim decision.",
  },
];

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const user = await getSessionUser();
  if (user) redirect("/dashboard");
  const { next } = await searchParams;

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      {/* Product context, not marketing. */}
      <section className="relative hidden flex-col justify-between overflow-hidden bg-sidebar p-12 text-sidebar-foreground lg:flex">
        <div className="absolute inset-0 bg-iris-mesh" aria-hidden />
        <div
          className="absolute inset-0 opacity-[0.16]"
          aria-hidden
          style={{
            backgroundImage:
              "linear-gradient(hsl(var(--sidebar-border) / 0.5) 1px, transparent 1px), linear-gradient(90deg, hsl(var(--sidebar-border) / 0.5) 1px, transparent 1px)",
            backgroundSize: "56px 56px",
            maskImage: "radial-gradient(75% 65% at 30% 25%, #000 0%, transparent 75%)",
            WebkitMaskImage: "radial-gradient(75% 65% at 30% 25%, #000 0%, transparent 75%)",
          }}
        />

        <div className="relative flex items-center gap-3">
          <span className="inline-flex size-10 items-center justify-center rounded-xl bg-white/10 text-sidebar-active ring-1 ring-inset ring-white/15">
            <ShieldCheck className="size-5" />
          </span>
          <div>
            <p className="text-sm font-semibold tracking-tight text-white">{APP_NAME}</p>
            <p className="text-2xs text-sidebar-muted">Insurance Document Intelligence</p>
          </div>
        </div>

        <div className="relative max-w-xl space-y-9">
          <div className="space-y-4">
            <h2 className="text-3xl font-semibold leading-[1.15] tracking-tight text-white">
              Evidence for a human decision — not a verdict from a machine.
            </h2>
            <p className="max-w-lg text-sm leading-relaxed text-sidebar-foreground/75">
              The platform combines forensic, OCR, rule-based, cross-document and trusted-source
              signals into one explainable record. It never concludes that a document is genuine or
              fraudulent; it ranks documents for attention and shows exactly why.
            </p>
          </div>

          <dl className="grid gap-x-8 gap-y-5 sm:grid-cols-2">
            {CAPABILITIES.map((capability) => {
              const Icon = capability.icon;
              return (
                <div key={capability.title} className="space-y-2">
                  <span className="inline-flex size-8 items-center justify-center rounded-lg bg-white/[0.07] text-sidebar-active ring-1 ring-inset ring-white/10">
                    <Icon className="size-4" />
                  </span>
                  <dt className="text-xs font-semibold text-white">{capability.title}</dt>
                  <dd className="text-2xs leading-relaxed text-sidebar-foreground/65">
                    {capability.body}
                  </dd>
                </div>
              );
            })}
          </dl>
        </div>

        <p className="relative flex max-w-xl items-start gap-2.5 text-2xs leading-relaxed text-sidebar-muted">
          <Lock className="mt-0.5 size-3.5 shrink-0" />
          <span>
            Documents processed here contain medical and identity data. Access is role-scoped, every
            action is written to an append-only audit trail, and document bodies are never written
            to application logs.
          </span>
        </p>
      </section>

      <section className="flex items-center justify-center bg-background px-5 py-12">
        <div className="w-full max-w-[26rem] space-y-8">
          <div className="flex items-center gap-2.5 lg:hidden">
            <span className="inline-flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <ShieldCheck className="size-4" />
            </span>
            <div>
              <p className="text-sm font-semibold tracking-tight">{APP_NAME}</p>
              <p className="text-2xs text-muted-foreground">Insurance Document Intelligence</p>
            </div>
          </div>

          <div className="space-y-2">
            <h1 className="text-2xl font-semibold">Sign in</h1>
            <p className="text-xs text-muted-foreground">
              Use your investigator, claims or administrator account.
            </p>
          </div>

          <LoginForm nextPath={next} demoMode={DEMO_MODE} />
        </div>
      </section>
    </div>
  );
}
