import type { Metadata } from "next";
import { KeyRound, PlugZap } from "lucide-react";

import { ProviderActivateSwitch } from "@/components/shared/rule-controls";
import { DemoBadge } from "@/components/shared/demo-notice";
import { PageHeader } from "@/components/shared/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow, TableWrap,
} from "@/components/ui/table";
import { api, apiSafe } from "@/lib/api";
import { humanise } from "@/lib/format";
import { can, getSessionUser } from "@/lib/session";
import type { ProviderConfig } from "@/lib/types";

export const metadata: Metadata = { title: "Integrations" };

const KIND_COPY: Record<string, { title: string; body: string }> = {
  ocr: {
    title: "OCR / text extraction",
    body: "Reads values off the page. The hybrid provider uses a PDF's embedded text layer where it exists — exact characters and exact coordinates — and falls back to pixel OCR for scans and photographs.",
  },
  aigc: {
    title: "Synthetic-media detection",
    body: "Estimates whether page imagery shows signs of being generated or AI-edited. The bundled provider is a deterministic heuristic, not a trained classifier; swap in a vendor endpoint to make this signal authoritative.",
  },
  verification: {
    title: "Trusted-source verification",
    body: "Confirms references against an authoritative record. Demo providers answer from a bundled sample registry; a production endpoint makes the same checks real.",
  },
  storage: {
    title: "Object storage",
    body: "Originals and derived artifacts are kept in separate buckets so retention can purge derivatives without touching evidence.",
  },
  malware: {
    title: "Security scanning",
    body: "Checks uploads for active content before analysis. A suspicious verdict quarantines the document without deleting it.",
  },
};

export default async function IntegrationsPage() {
  const user = await getSessionUser();
  const [providers, runtime] = await Promise.all([
    api<ProviderConfig[]>("/providers"),
    apiSafe<Record<string, any>>("/providers/runtime"),
  ]);

  const editable = can(user, "provider:write");
  const byKind = new Map<string, ProviderConfig[]>();
  for (const provider of providers) {
    byKind.set(provider.kind, [...(byKind.get(provider.kind) ?? []), provider]);
  }

  return (
    <>
      <PageHeader
        title="Integrations"
        description="Every external capability sits behind an interface with at least one demo or local
          implementation, so the platform is complete without credentials — and a production
          provider can be dropped in without touching the pipeline."
        actions={
          <Badge variant={editable ? "default" : "muted"}>
            {editable ? "You can switch providers" : "Read-only for your role"}
          </Badge>
        }
      />

      <Alert variant="info">
        <KeyRound />
        <div>
          <AlertTitle>Credentials live in the environment, never in the database</AlertTitle>
          <AlertDescription>
            {runtime?.credentials_note ??
              "This screen shows which environment variables a provider expects — never their values."}
          </AlertDescription>
        </div>
      </Alert>

      {["ocr", "aigc", "verification", "storage", "malware"].map((kind) => {
        const items = byKind.get(kind) ?? [];
        if (!items.length) return null;
        const copy = KIND_COPY[kind];
        return (
          <section key={kind} className="panel">
            <header className="panel-header">
              <div className="min-w-0">
                <h2 className="flex items-center gap-2 text-xs font-semibold">
                  <PlugZap className="size-3.5 text-muted-foreground" />
                  {copy?.title ?? humanise(kind)}
                </h2>
                <p className="mt-0.5 max-w-3xl text-2xs leading-relaxed text-muted-foreground">
                  {copy?.body}
                </p>
              </div>
              <Badge variant="muted">{items.length} available</Badge>
            </header>
            <TableWrap>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[80px]">Active</TableHead>
                    <TableHead>Provider</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead>Model</TableHead>
                    <TableHead>Required environment</TableHead>
                    <TableHead>Data source</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((provider) => {
                    const needsCredentials = provider.credential_env_keys.length > 0;
                    return (
                      <TableRow key={provider.id} className={provider.is_active ? "bg-primary/5" : undefined}>
                        <TableCell>
                          {editable ? (
                            <ProviderActivateSwitch
                              kind={provider.kind}
                              providerKey={provider.key}
                              isActive={provider.is_active}
                            />
                          ) : (
                            <Badge variant={provider.is_active ? "low" : "muted"}>
                              {provider.is_active ? "active" : "off"}
                            </Badge>
                          )}
                        </TableCell>
                        <TableCell className="max-w-[220px] text-2xs">
                          <span className="block font-medium">{provider.label}</span>
                          <span className="block font-mono text-muted-foreground">{provider.key}</span>
                        </TableCell>
                        <TableCell className="max-w-[420px] text-2xs text-muted-foreground">
                          {provider.description}
                        </TableCell>
                        <TableCell className="text-2xs">
                          {provider.model_name ? (
                            <span className="font-mono">
                              {provider.model_name}
                              {provider.model_version ? ` @ ${provider.model_version}` : ""}
                            </span>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </TableCell>
                        <TableCell className="text-2xs">
                          {needsCredentials ? (
                            <ul className="space-y-0.5 font-mono text-muted-foreground">
                              {provider.credential_env_keys.map((key) => (
                                <li key={key}>{key}</li>
                              ))}
                            </ul>
                          ) : (
                            <span className="text-muted-foreground">none</span>
                          )}
                        </TableCell>
                        <TableCell>
                          {provider.is_demo ? (
                            <DemoBadge label="Demo / local" />
                          ) : (
                            <Badge variant="low">Production capable</Badge>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableWrap>
            {runtime?.[kind]?.providers && (
              <footer className="border-t px-4 py-2.5">
                <p className="text-2xs text-muted-foreground">
                  Live availability:{" "}
                  {(runtime[kind].providers as any[])
                    .map(
                      (entry) =>
                        `${entry.key ?? entry.label}: ${entry.available ? "ready" : "unavailable"}`,
                    )
                    .join(" · ")}
                </p>
              </footer>
            )}
          </section>
        );
      })}
    </>
  );
}
