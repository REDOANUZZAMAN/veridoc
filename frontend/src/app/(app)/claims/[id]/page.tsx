import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ChevronRight, FileStack, GitCompareArrows, Landmark, ScrollText } from "lucide-react";

import { AssignInvestigator } from "@/components/claims/assign-investigator";
import { ClaimDecisionDialog } from "@/components/claims/claim-decision";
import { UploadDialog } from "@/components/documents/upload-dialog";
import { FindingCard } from "@/components/documents/finding-card";
import { DemoBadge } from "@/components/shared/demo-notice";
import { EmptyState, KeyValue, PageHeader } from "@/components/shared/page-header";
import { RiskBadge } from "@/components/shared/risk-badge";
import { SeverityBadge } from "@/components/shared/severity-badge";
import {
  ClaimStatusChip, InvestigationStatusChip, OutcomeChip, PriorityChip, ProcessingStatusChip,
  VerificationStateChip,
} from "@/components/shared/status-chip";
import { UncertaintyNote } from "@/components/shared/uncertainty-note";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table, TableBody, TableCell, TableEmpty, TableHead, TableHeader, TableRow, TableWrap,
} from "@/components/ui/table";
import { ApiError, api, apiSafe } from "@/lib/api";
import { formatDate, formatMoney, humanise, percent } from "@/lib/format";
import { can, getSessionUser } from "@/lib/session";
import type { ClaimDetail, ReportSummary, UserRef } from "@/lib/types";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const claim = await apiSafe<ClaimDetail>(`/claims/${id}`);
  return { title: claim ? `${claim.claim_number} · Claim` : "Claim" };
}

export default async function ClaimDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const user = await getSessionUser();

  let claim: ClaimDetail;
  try {
    claim = await api<ClaimDetail>(`/claims/${id}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  const [investigators, reports] = await Promise.all([
    apiSafe<UserRef[]>("/users/investigators"),
    apiSafe<{ items: ReportSummary[] }>("/reports", { searchParams: { claim_id: claim.id } }),
  ]);

  const openHigh = claim.findings_summary.top.filter(
    (finding) => finding.status === "open" && ["high", "critical"].includes(finding.severity),
  ).length;
  const mismatches = (claim.cross_document.comparisons ?? []).filter(
    (row) => !row.agrees && !row.skipped,
  );

  return (
    <>
      <PageHeader
        breadcrumb={
          <span className="flex items-center gap-1">
            <Link href="/claims" className="hover:text-foreground hover:underline">
              Claims
            </Link>
            <ChevronRight className="size-3" />
            <span className="font-mono">{claim.claim_number}</span>
          </span>
        }
        title={
          <span className="flex flex-wrap items-center gap-2">
            {claim.customer_name}
            <Badge variant="outline" className="font-mono">
              {claim.claim_number}
            </Badge>
            <ClaimStatusChip status={claim.status} />
          </span>
        }
        description={claim.summary ?? undefined}
        actions={
          <>
            <RiskBadge band={claim.risk_band} score={claim.risk_score} />
            {can(user, "investigation:assign") && (
              <AssignInvestigator
                claimId={claim.id}
                current={claim.assigned_investigator}
                investigators={investigators ?? []}
              />
            )}
            {can(user, "document:upload") && (
              <UploadDialog
                claims={[{ id: claim.id, claim_number: claim.claim_number, customer_name: claim.customer_name }]}
                defaultClaimId={claim.id}
              />
            )}
            {can(user, "claim:decide") && claim.status !== "resolved" && (
              <ClaimDecisionDialog
                claimId={claim.id}
                claimNumber={claim.claim_number}
                openHighFindings={openHigh}
              />
            )}
          </>
        }
      />

      {claim.decision && (
        <section className="rounded-lg border border-primary/30 bg-primary/5 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="default">Decision: {humanise(claim.decision)}</Badge>
            <span className="text-2xs text-muted-foreground">
              recorded {formatDate(claim.decided_at, true)}
            </span>
          </div>
          <p className="mt-2 text-2xs leading-relaxed">{claim.decision_reason}</p>
        </section>
      )}

      <div className="grid gap-3 lg:grid-cols-4">
        <section className="panel lg:col-span-3">
          <header className="panel-header">
            <h2 className="text-xs font-semibold">Claim particulars</h2>
            <span className="text-2xs text-muted-foreground">
              These values are what documents are checked against
            </span>
          </header>
          <div className="p-4">
            <KeyValue
              columns={3}
              items={[
                { label: "Customer", value: claim.customer_name },
                { label: "Date of birth", value: formatDate(claim.customer_dob) },
                { label: "Policy number", value: claim.policy_number, mono: true },
                { label: "Insurer", value: claim.insurer },
                { label: "Claim type", value: humanise(claim.claim_type) },
                { label: "Incident date", value: formatDate(claim.incident_date) },
                {
                  label: "Amount claimed",
                  value: formatMoney(claim.claimed_amount, claim.currency),
                },
                { label: "Created by", value: claim.created_by?.full_name ?? "—" },
                {
                  label: "Assigned investigator",
                  value: claim.assigned_investigator?.full_name ?? "Unassigned",
                },
                { label: "Customer email", value: claim.customer_email ?? "—" },
                { label: "Opened", value: formatDate(claim.created_at, true) },
                { label: "Last updated", value: formatDate(claim.updated_at, true) },
              ]}
            />
          </div>
        </section>

        <section className="panel">
          <header className="panel-header">
            <h2 className="text-xs font-semibold">Finding summary</h2>
          </header>
          <div className="space-y-2 p-4">
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(claim.findings_summary.by_severity ?? {})
                .sort(
                  ([a], [b]) =>
                    ["critical", "high", "medium", "low", "info"].indexOf(a) -
                    ["critical", "high", "medium", "low", "info"].indexOf(b),
                )
                .map(([severity, count]) => (
                  <span key={severity} className="flex items-center gap-1">
                    <SeverityBadge severity={severity as any} withIcon={false} />
                    <span className="tabular text-2xs text-muted-foreground">{count}</span>
                  </span>
                ))}
              {!Object.keys(claim.findings_summary.by_severity ?? {}).length && (
                <span className="text-2xs text-muted-foreground">No findings recorded.</span>
              )}
            </div>
            <dl className="space-y-1 pt-1 text-2xs">
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Awaiting review</dt>
                <dd className="tabular font-medium">{claim.findings_summary.open}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Confirmed</dt>
                <dd className="tabular font-medium">{claim.findings_summary.confirmed}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Dismissed</dt>
                <dd className="tabular font-medium">{claim.findings_summary.dismissed}</dd>
              </div>
              <div className="flex justify-between border-t pt-1">
                <dt className="text-muted-foreground">Cross-document mismatches</dt>
                <dd className="tabular font-medium">{mismatches.length}</dd>
              </div>
            </dl>
          </div>
        </section>
      </div>

      <Tabs defaultValue="documents">
        <TabsList>
          <TabsTrigger value="documents">
            <FileStack className="size-3.5" /> Documents
            <span className="tabular ml-0.5 rounded bg-muted px-1 text-2xs">{claim.documents.length}</span>
          </TabsTrigger>
          <TabsTrigger value="crossdoc">
            <GitCompareArrows className="size-3.5" /> Cross-document
            {mismatches.length > 0 && (
              <span className="tabular ml-0.5 rounded bg-muted px-1 text-2xs">{mismatches.length}</span>
            )}
          </TabsTrigger>
          <TabsTrigger value="findings">Findings</TabsTrigger>
          <TabsTrigger value="verification">
            <Landmark className="size-3.5" /> Verification
          </TabsTrigger>
          <TabsTrigger value="investigations">Investigations</TabsTrigger>
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
          <TabsTrigger value="reports">
            <ScrollText className="size-3.5" /> Reports
          </TabsTrigger>
        </TabsList>

        <TabsContent value="documents">
          <section className="panel">
            <TableWrap>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Reference</TableHead>
                    <TableHead>Document</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Risk</TableHead>
                    <TableHead>Findings</TableHead>
                    <TableHead>Pipeline</TableHead>
                    <TableHead>Human verdict</TableHead>
                    <TableHead className="text-right">Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {claim.documents.length === 0 && (
                    <TableEmpty colSpan={8}>
                      No documents have been attached to this claim yet.
                    </TableEmpty>
                  )}
                  {claim.documents.map((document) => (
                    <TableRow key={document.id}>
                      <TableCell className="font-mono text-2xs">
                        <Link className="text-primary hover:underline" href={`/documents/${document.id}`}>
                          {document.document_ref}
                        </Link>
                      </TableCell>
                      <TableCell className="max-w-[260px] text-xs">
                        <span className="block truncate">{document.original_filename}</span>
                        <span className="block text-2xs text-muted-foreground">
                          {document.page_count} page{document.page_count === 1 ? "" : "s"} ·{" "}
                          {document.file_extension.toUpperCase()}
                        </span>
                      </TableCell>
                      <TableCell className="text-2xs">
                        {document.classification_label ?? "—"}
                        <span className="block text-muted-foreground">
                          {percent(document.classification_confidence)}
                        </span>
                      </TableCell>
                      <TableCell>
                        <RiskBadge size="sm" band={document.risk_band} score={document.risk_score} />
                      </TableCell>
                      <TableCell>
                        <Badge variant="muted">{document.finding_counts.total ?? 0}</Badge>
                      </TableCell>
                      <TableCell>
                        <ProcessingStatusChip status={document.processing_status} />
                      </TableCell>
                      <TableCell>
                        <VerificationStateChip state={document.verification_state} />
                      </TableCell>
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
        </TabsContent>

        <TabsContent value="crossdoc">
          <section className="panel">
            <header className="panel-header">
              <div>
                <h3 className="text-xs font-semibold">Field agreement across the bundle</h3>
                <p className="mt-0.5 text-2xs text-muted-foreground">
                  {claim.cross_document.agreements ?? 0} agreements ·{" "}
                  {claim.cross_document.mismatches ?? 0} mismatches across{" "}
                  {claim.cross_document.documents_compared ?? 0} documents. Fields are only compared
                  where the comparison is meaningful — two separate invoices are not expected to
                  carry the same total.
                </p>
              </div>
            </header>
            <TableWrap className="max-h-[520px]">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Field</TableHead>
                    <TableHead>Source A</TableHead>
                    <TableHead>Source B</TableHead>
                    <TableHead>Result</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(claim.cross_document.comparisons ?? []).map((row, index) => (
                    <TableRow key={index} className={!row.agrees ? "bg-risk-high/5" : undefined}>
                      <TableCell className="text-2xs">
                        {row.label}
                        <span className="block text-muted-foreground">{row.mode}</span>
                      </TableCell>
                      <TableCell className="max-w-[220px] text-2xs">
                        <span className="block font-mono text-muted-foreground">{row.document_a}</span>
                        <span className="block break-words">{row.value_a || "—"}</span>
                      </TableCell>
                      <TableCell className="max-w-[220px] text-2xs">
                        <span className="block font-mono text-muted-foreground">{row.document_b}</span>
                        <span className="block break-words">{row.value_b || "—"}</span>
                      </TableCell>
                      <TableCell className="text-2xs">
                        {row.skipped ? (
                          <Badge variant="muted">Not compared</Badge>
                        ) : row.agrees ? (
                          <Badge variant="low">Agrees</Badge>
                        ) : (
                          <Badge variant="high">Mismatch</Badge>
                        )}
                        <span className="mt-0.5 block text-muted-foreground">{row.detail}</span>
                      </TableCell>
                    </TableRow>
                  ))}
                  {!(claim.cross_document.comparisons ?? []).length && (
                    <TableEmpty colSpan={4}>
                      At least two documents with extracted fields are needed to compare a bundle.
                    </TableEmpty>
                  )}
                </TableBody>
              </Table>
            </TableWrap>
          </section>
        </TabsContent>

        <TabsContent value="findings" className="space-y-2">
          {claim.findings_summary.top.length === 0 && (
            <EmptyState title="No findings across this claim" description="Nothing has been raised by the
              analysis stages that completed." />
          )}
          {claim.findings_summary.top.map((finding) => (
            <FindingCard key={finding.finding_id} finding={finding} />
          ))}
          {claim.findings_summary.total > claim.findings_summary.top.length && (
            <p className="px-1 text-2xs text-muted-foreground">
              Showing the {claim.findings_summary.top.length} most severe of{" "}
              {claim.findings_summary.total}. Open a document to see all of its findings.
            </p>
          )}
          <UncertaintyNote />
        </TabsContent>

        <TabsContent value="verification">
          <section className="panel">
            <TableWrap>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Check</TableHead>
                    <TableHead>Provider</TableHead>
                    <TableHead>Outcome</TableHead>
                    <TableHead>Summary</TableHead>
                    <TableHead>When</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {claim.verification.length === 0 && (
                    <TableEmpty colSpan={5}>
                      No verification has been requested for this claim.
                    </TableEmpty>
                  )}
                  {claim.verification.map((request) => (
                    <TableRow key={request.id}>
                      <TableCell className="text-2xs">{humanise(request.request_type)}</TableCell>
                      <TableCell className="text-2xs">
                        {request.provider_label}
                        {request.is_demo_provider && (
                          <span className="ml-1 inline-block">
                            <DemoBadge label="demo" />
                          </span>
                        )}
                      </TableCell>
                      <TableCell>
                        {request.result ? <OutcomeChip outcome={request.result.outcome} /> : "—"}
                      </TableCell>
                      <TableCell className="max-w-[420px] text-2xs text-muted-foreground">
                        {request.result?.summary}
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-2xs text-muted-foreground">
                        {formatDate(request.requested_at, true)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableWrap>
          </section>
        </TabsContent>

        <TabsContent value="investigations">
          <section className="panel">
            <TableWrap>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Case</TableHead>
                    <TableHead>Title</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Priority</TableHead>
                    <TableHead>Assigned</TableHead>
                    <TableHead>Notes</TableHead>
                    <TableHead>Opened</TableHead>
                    <TableHead className="text-right">Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {claim.investigations.length === 0 && (
                    <TableEmpty colSpan={8}>No investigation has been opened.</TableEmpty>
                  )}
                  {claim.investigations.map((investigation) => (
                    <TableRow key={investigation.id}>
                      <TableCell className="font-mono text-2xs">{investigation.case_number}</TableCell>
                      <TableCell className="max-w-[300px] text-2xs">{investigation.title}</TableCell>
                      <TableCell>
                        <InvestigationStatusChip status={investigation.status} />
                      </TableCell>
                      <TableCell>
                        <PriorityChip priority={investigation.priority} />
                      </TableCell>
                      <TableCell className="text-2xs">
                        {investigation.assigned_to?.full_name ?? "—"}
                      </TableCell>
                      <TableCell className="tabular text-2xs">{investigation.note_count}</TableCell>
                      <TableCell className="whitespace-nowrap text-2xs text-muted-foreground">
                        {formatDate(investigation.opened_at ?? investigation.created_at)}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button variant="ghost" size="xs" asChild>
                          <Link href={`/investigations/${investigation.id}`}>Open</Link>
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableWrap>
          </section>
        </TabsContent>

        <TabsContent value="timeline">
          <section className="panel">
            <ol className="divide-y">
              {claim.timeline.map((entry, index) => (
                <li key={index} className="flex gap-3 px-4 py-2.5">
                  <span className="mt-0.5 shrink-0 text-2xs tabular text-muted-foreground">
                    {formatDate(entry.at, true)}
                  </span>
                  <div className="min-w-0 space-y-0.5">
                    <p className="text-xs">{entry.summary}</p>
                    <p className="text-2xs text-muted-foreground">
                      {humanise(entry.type)}
                      {entry.actor ? ` · ${entry.actor.full_name}` : ""}
                    </p>
                  </div>
                </li>
              ))}
              {!claim.timeline.length && (
                <li className="px-4 py-8 text-center text-2xs text-muted-foreground">
                  Nothing has happened on this claim yet.
                </li>
              )}
            </ol>
          </section>
        </TabsContent>

        <TabsContent value="reports">
          <section className="panel">
            <TableWrap>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Report</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Generated by</TableHead>
                    <TableHead>Versions</TableHead>
                    <TableHead>When</TableHead>
                    <TableHead className="text-right">PDF</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {!(reports?.items ?? []).length && (
                    <TableEmpty colSpan={6}>
                      No report has been generated for this claim.
                    </TableEmpty>
                  )}
                  {(reports?.items ?? []).map((report) => (
                    <TableRow key={report.id}>
                      <TableCell className="font-mono text-2xs">{report.report_ref}</TableCell>
                      <TableCell className="text-2xs">{humanise(report.report_type)}</TableCell>
                      <TableCell className="text-2xs">{report.generated_by?.full_name ?? "—"}</TableCell>
                      <TableCell className="font-mono text-2xs text-muted-foreground">
                        {report.pipeline_version} / {report.rules_version}
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-2xs text-muted-foreground">
                        {formatDate(report.created_at, true)}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button variant="ghost" size="xs" asChild>
                          <a href={`/api/be/reports/${report.id}/export`} target="_blank" rel="noreferrer">
                            Open
                          </a>
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableWrap>
          </section>
        </TabsContent>
      </Tabs>
    </>
  );
}
