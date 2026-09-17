import type { Metadata } from "next";
import Link from "next/link";
import { Landmark, PlugZap } from "lucide-react";

import { DemoBadge, DemoNotice } from "@/components/shared/demo-notice";
import { PageHeader } from "@/components/shared/page-header";
import { OutcomeChip } from "@/components/shared/status-chip";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableEmpty, TableHead, TableHeader, TableRow, TableWrap,
} from "@/components/ui/table";
import { api, apiSafe } from "@/lib/api";
import { formatDate, humanise } from "@/lib/format";
import type { Paged, VerificationRequest } from "@/lib/types";

export const metadata: Metadata = { title: "Verification" };

interface ProvidersResponse {
  providers: Array<{
    key: string;
    label: string;
    mode: string;
    request_types: string[];
    description: string;
    available: boolean;
    detail: string;
    is_demo: boolean;
  }>;
  routing: Record<string, string[]>;
  note: string;
}

export default async function VerificationPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const params = await searchParams;
  const [requests, providers] = await Promise.all([
    api<Paged<Record<string, any>>>("/verification/requests", {
      searchParams: {
        page: Number(params.page ?? 1),
        page_size: 30,
        outcome: params.outcome,
        request_type: params.request_type,
      },
    }),
    apiSafe<ProvidersResponse>("/verification/providers"),
  ]);

  const outcomes = [
    ["", "All"],
    ["match", "Match"],
    ["partial_match", "Partial"],
    ["mismatch", "Mismatch"],
    ["not_found", "Not found"],
    ["unavailable", "Unavailable"],
  ];

  return (
    <>
      <PageHeader
        title="Trusted-source verification"
        description="Verification is the only signal in the platform that can corroborate a document rather
          than flag an anomaly — so every answer is labelled with the source that gave it."
        actions={
          <Button variant="outline" size="sm" asChild>
            <Link href="/integrations">
              <PlugZap className="size-4" /> Configure providers
            </Link>
          </Button>
        }
      />

      {providers?.providers.some((provider) => provider.is_demo && provider.available) && (
        <DemoNotice title="Demo providers are active">{providers.note}</DemoNotice>
      )}

      <section className="panel">
        <header className="panel-header">
          <h2 className="text-xs font-semibold">Configured providers</h2>
          <span className="text-2xs text-muted-foreground">
            One provider answers each request type
          </span>
        </header>
        <TableWrap>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Provider</TableHead>
                <TableHead>Mode</TableHead>
                <TableHead>Request types</TableHead>
                <TableHead>What it checks</TableHead>
                <TableHead>Availability</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(providers?.providers ?? []).map((provider) => (
                <TableRow key={provider.key}>
                  <TableCell className="text-2xs">
                    {provider.label}
                    <span className="block font-mono text-muted-foreground">{provider.key}</span>
                  </TableCell>
                  <TableCell>
                    {provider.is_demo ? <DemoBadge /> : <Badge variant="low">Production</Badge>}
                  </TableCell>
                  <TableCell className="text-2xs text-muted-foreground">
                    {provider.request_types.map((type) => humanise(type)).join(", ")}
                  </TableCell>
                  <TableCell className="max-w-[420px] text-2xs text-muted-foreground">
                    {provider.description}
                  </TableCell>
                  <TableCell className="text-2xs">
                    {provider.available ? (
                      <Badge variant="low">Ready</Badge>
                    ) : (
                      <Badge variant="muted">Not configured</Badge>
                    )}
                    <span className="mt-0.5 block text-muted-foreground">{provider.detail}</span>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableWrap>
      </section>

      <div className="flex flex-wrap items-center gap-1.5">
        {outcomes.map(([value, label]) => (
          <Button
            key={label}
            variant={(params.outcome ?? "") === value ? "secondary" : "ghost"}
            size="sm"
            asChild
          >
            <Link href={value ? `/verification?outcome=${value}` : "/verification"}>{label}</Link>
          </Button>
        ))}
      </div>

      <section className="panel">
        <header className="panel-header">
          <h2 className="text-xs font-semibold">Verification history</h2>
          <p className="text-2xs text-muted-foreground">
            <span className="tabular font-semibold text-foreground">{requests.meta.total}</span>{" "}
            request{requests.meta.total === 1 ? "" : "s"}
          </p>
        </header>
        <TableWrap>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>When</TableHead>
                <TableHead>Check</TableHead>
                <TableHead>Document</TableHead>
                <TableHead>Claim</TableHead>
                <TableHead>Provider</TableHead>
                <TableHead>Outcome</TableHead>
                <TableHead>Failed checks</TableHead>
                <TableHead>Latency</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {requests.items.length === 0 && (
                <TableEmpty colSpan={8}>No verification requests recorded.</TableEmpty>
              )}
              {requests.items.map((request) => {
                const failed = (request.result?.checks ?? []).filter(
                  (check: any) => check.passed === false,
                );
                return (
                  <TableRow key={request.id}>
                    <TableCell className="whitespace-nowrap text-2xs text-muted-foreground">
                      {formatDate(request.requested_at, true)}
                    </TableCell>
                    <TableCell className="text-2xs">{humanise(request.request_type)}</TableCell>
                    <TableCell className="font-mono text-2xs">
                      {request.document_id ? (
                        <Link
                          className="text-primary hover:underline"
                          href={`/documents/${request.document_id}`}
                        >
                          {request.document_ref}
                        </Link>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell className="font-mono text-2xs">
                      {request.claim_id ? (
                        <Link className="text-primary hover:underline" href={`/claims/${request.claim_id}`}>
                          {request.claim_number}
                        </Link>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell className="text-2xs">
                      {request.provider_label}
                      {request.is_demo_provider && (
                        <span className="ml-1 inline-block align-middle">
                          <DemoBadge label="demo" />
                        </span>
                      )}
                    </TableCell>
                    <TableCell>
                      {request.result ? <OutcomeChip outcome={request.result.outcome} /> : "—"}
                    </TableCell>
                    <TableCell className="max-w-[260px] text-2xs text-muted-foreground">
                      {failed.length ? failed.map((check: any) => check.label).join(", ") : "—"}
                    </TableCell>
                    <TableCell className="tabular text-2xs text-muted-foreground">
                      {request.result?.latency_ms ?? "—"} ms
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableWrap>
      </section>
    </>
  );
}
