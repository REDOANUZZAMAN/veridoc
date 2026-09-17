import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ChevronRight } from "lucide-react";

import {
  AddInvestigationNote, InvestigationStatusControl,
} from "@/components/claims/investigation-notes";
import { FindingCard } from "@/components/documents/finding-card";
import { EmptyState, KeyValue, PageHeader } from "@/components/shared/page-header";
import { RiskBadge } from "@/components/shared/risk-badge";
import { InvestigationStatusChip, PriorityChip } from "@/components/shared/status-chip";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableEmpty, TableHead, TableHeader, TableRow, TableWrap,
} from "@/components/ui/table";
import { ApiError, api } from "@/lib/api";
import { formatDate, formatMoney, humanise } from "@/lib/format";
import { can, getSessionUser } from "@/lib/session";
import type { Investigation } from "@/lib/types";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  return { title: `Investigation ${id.slice(0, 8)}` };
}

export default async function InvestigationPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const user = await getSessionUser();

  let investigation: Investigation;
  try {
    investigation = await api<Investigation>(`/investigations/${id}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  const claim = investigation.claim ?? null;

  return (
    <>
      <PageHeader
        breadcrumb={
          <span className="flex items-center gap-1">
            <Link href="/investigations" className="hover:text-foreground hover:underline">
              Investigations
            </Link>
            <ChevronRight className="size-3" />
            <span className="font-mono">{investigation.case_number}</span>
          </span>
        }
        title={
          <span className="flex flex-wrap items-center gap-2">
            {investigation.title}
            <InvestigationStatusChip status={investigation.status} />
            <PriorityChip priority={investigation.priority} />
          </span>
        }
        description={investigation.summary ?? undefined}
        actions={
          claim ? (
            <>
              <RiskBadge band={claim.risk_band} score={claim.risk_score} />
              <Button variant="outline" size="sm" asChild>
                <Link href={`/claims/${claim.id}`}>Open claim</Link>
              </Button>
            </>
          ) : null
        }
      />

      <div className="grid gap-3 lg:grid-cols-3">
        <section className="panel lg:col-span-2">
          <header className="panel-header">
            <h2 className="text-xs font-semibold">Case detail</h2>
          </header>
          <div className="p-4">
            <KeyValue
              columns={2}
              items={[
                { label: "Case number", value: investigation.case_number, mono: true },
                { label: "Opened", value: formatDate(investigation.opened_at, true) },
                { label: "Opened by", value: investigation.opened_by?.full_name ?? "system" },
                {
                  label: "Assigned to",
                  value: investigation.assigned_to?.full_name ?? "Unassigned",
                },
                {
                  label: "Risk at open",
                  value: investigation.risk_score_at_open
                    ? `${investigation.risk_score_at_open}/100`
                    : "—",
                },
                {
                  label: "Trigger",
                  value: humanise(String(investigation.context?.opened_by ?? "manual")),
                },
                ...(claim
                  ? [
                      { label: "Claim", value: claim.claim_number, mono: true },
                      { label: "Customer", value: claim.customer_name },
                      { label: "Policy", value: claim.policy_number, mono: true },
                      {
                        label: "Amount claimed",
                        value: formatMoney(claim.claimed_amount, claim.currency),
                      },
                    ]
                  : []),
                ...(investigation.closed_at
                  ? [
                      { label: "Closed", value: formatDate(investigation.closed_at, true) },
                      {
                        label: "Resolution",
                        value: humanise(investigation.resolution ?? ""),
                      },
                    ]
                  : []),
              ]}
            />
            {investigation.resolution_reason && (
              <p className="mt-3 rounded border-l-2 border-primary/50 bg-muted/40 px-3 py-2 text-2xs leading-relaxed">
                {investigation.resolution_reason}
              </p>
            )}
          </div>
        </section>

        <section className="panel">
          <header className="panel-header">
            <h2 className="text-xs font-semibold">Case status</h2>
          </header>
          {can(user, "investigation:note") ? (
            <InvestigationStatusControl
              investigationId={investigation.id}
              status={investigation.status}
              canClose={can(user, "investigation:close")}
            />
          ) : (
            <p className="px-4 py-6 text-2xs text-muted-foreground">
              Your role can view this case but not change its state.
            </p>
          )}
        </section>
      </div>

      {(investigation.documents ?? []).length > 0 && (
        <section className="panel">
          <header className="panel-header">
            <h2 className="text-xs font-semibold">Documents on the claim</h2>
          </header>
          <TableWrap>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Reference</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Risk</TableHead>
                  <TableHead>Human verdict</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(investigation.documents ?? []).map((document: any) => (
                  <TableRow key={document.id}>
                    <TableCell className="font-mono text-2xs">{document.document_ref}</TableCell>
                    <TableCell className="text-2xs">{humanise(document.classification_type)}</TableCell>
                    <TableCell>
                      <RiskBadge size="sm" band={document.risk_band} score={document.risk_score} />
                    </TableCell>
                    <TableCell className="text-2xs">{humanise(document.verification_state)}</TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="xs" asChild>
                        <Link href={`/documents/${document.id}`}>Investigate</Link>
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableWrap>
        </section>
      )}

      <div className="grid gap-3 lg:grid-cols-2">
        <section className="panel">
          <header className="panel-header">
            <h2 className="text-xs font-semibold">Investigation notes</h2>
            <Badge variant="muted">{investigation.notes?.length ?? 0}</Badge>
          </header>
          <ol className="divide-y">
            {(investigation.notes ?? []).map((note) => (
              <li key={note.id} className="space-y-1 px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline">{humanise(note.note_type)}</Badge>
                  <span className="text-2xs font-medium">{note.author?.full_name ?? "system"}</span>
                  <span className="text-2xs text-muted-foreground">
                    {formatDate(note.created_at, true)}
                  </span>
                </div>
                <p className="whitespace-pre-wrap text-2xs leading-relaxed">{note.body}</p>
              </li>
            ))}
            {!(investigation.notes ?? []).length && (
              <li className="px-4 py-8 text-center text-2xs text-muted-foreground">
                No notes yet.
              </li>
            )}
          </ol>
          {can(user, "investigation:note") && (
            <div className="border-t">
              <AddInvestigationNote investigationId={investigation.id} />
            </div>
          )}
        </section>

        <section className="panel">
          <header className="panel-header">
            <h2 className="text-xs font-semibold">Findings across the claim</h2>
            <Badge variant="muted">{investigation.findings?.length ?? 0}</Badge>
          </header>
          <div className="max-h-[560px] space-y-2 overflow-y-auto p-3 scrollbar-thin">
            {(investigation.findings ?? []).map((finding) => (
              <FindingCard key={finding.finding_id} finding={finding} compact />
            ))}
            {!(investigation.findings ?? []).length && (
              <EmptyState title="No findings" description="Nothing has been raised on this claim." />
            )}
          </div>
        </section>
      </div>
    </>
  );
}
