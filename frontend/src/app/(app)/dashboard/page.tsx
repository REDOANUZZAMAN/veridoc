import type { Metadata } from "next";
import Link from "next/link";
import {
  AlertTriangle, CheckCircle2, ClipboardList, FileStack, FileWarning, Hourglass,
  Layers, ShieldAlert, Wallet,
} from "lucide-react";

import {
  CategoryBarChart, DailyVolumeChart, FindingsByKindChart, RiskDistributionChart,
  VerificationOutcomeChart,
} from "@/components/dashboard/charts";
import { ChartCard } from "@/components/dashboard/chart-card";
import { EmptyState, PageHeader } from "@/components/shared/page-header";
import { PipelineTimeline } from "@/components/shared/pipeline-timeline";
import { RiskBadge } from "@/components/shared/risk-badge";
import { StatCard } from "@/components/shared/stat-card";
import { InvestigationStatusChip, PriorityChip } from "@/components/shared/status-chip";
import { UncertaintyNote } from "@/components/shared/uncertainty-note";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableEmpty, TableHead, TableHeader, TableRow, TableWrap,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import { PROCESSING_STATUS_LABEL, formatMoney, humanise, relativeTime } from "@/lib/format";
import type { DashboardData } from "@/lib/types";

export const metadata: Metadata = { title: "Dashboard" };

export default async function DashboardPage() {
  const data = await api<DashboardData>("/dashboard", { searchParams: { days: 21 } });
  const cards = data.cards;

  const findingRows = Object.entries(data.findings_by_kind).map(([kind, value]) => ({
    kind,
    total: value.total,
    open: value.open,
  }));

  return (
    <>
      <PageHeader
        title="Operations dashboard"
        description="Queue health, risk distribution and the cases that need a person next. Risk bands rank
          documents for attention; they are not conclusions about authenticity."
        actions={
          <>
            <Button variant="outline" size="sm" asChild>
              <Link href="/documents">Open document queue</Link>
            </Button>
            <Button size="sm" asChild>
              <Link href="/claims">Claims</Link>
            </Button>
          </>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <StatCard
          label="Documents processed"
          value={cards.documents_processed ?? 0}
          hint={`${cards.documents_total ?? 0} ingested in total`}
          icon={<FileStack className="size-4" />}
          href="/documents"
        />
        <StatCard
          label="Pending review"
          value={cards.pending_review ?? 0}
          hint="Raised a signal and has no human verdict yet"
          tone="review"
          icon={<Hourglass className="size-4" />}
          href="/documents?status=analyzed"
        />
        <StatCard
          label="High concern"
          value={cards.high_concern ?? 0}
          hint="Corroborating signals across categories"
          tone="high"
          icon={<ShieldAlert className="size-4" />}
          href="/documents?risk_band=high_concern"
        />
        <StatCard
          label="Verified"
          value={cards.verified ?? 0}
          hint="Marked verified by a named reviewer"
          tone="low"
          icon={<CheckCircle2 className="size-4" />}
        />
        <StatCard
          label="Processing errors"
          value={cards.processing_errors ?? 0}
          hint="Originals preserved; can be reprocessed"
          tone={cards.processing_errors ? "high" : "default"}
          icon={<FileWarning className="size-4" />}
        />
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Open investigations"
          value={cards.open_investigations ?? 0}
          icon={<ClipboardList className="size-4" />}
          href="/investigations"
        />
        <StatCard
          label="In flight"
          value={cards.in_flight ?? 0}
          hint="Queued or being analysed now"
          icon={<Layers className="size-4" />}
        />
        <StatCard
          label="Flagged exposure"
          value={formatMoney(cards.flagged_exposure ?? 0)}
          hint="Unresolved claims at review or high concern"
          tone="review"
          icon={<Wallet className="size-4" />}
        />
        <StatCard
          label="Documents awaiting a verdict"
          value={(cards.documents_total ?? 0) - (cards.verified ?? 0)}
          hint="Machine findings alone never close a document"
          icon={<AlertTriangle className="size-4" />}
        />
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        <ChartCard
          title="Risk distribution"
          description="Assessed documents by triage band"
          tableColumns={["Band", "Documents"]}
          tableRows={data.risk_distribution.map((row) => [row.label, row.count])}
        >
          <RiskDistributionChart data={data.risk_distribution} />
        </ChartCard>

        <ChartCard
          className="lg:col-span-2"
          title="Daily intake"
          description="Documents ingested per day, split by the band they were assigned"
          tableColumns={["Date", "Documents", "Low", "Review", "High"]}
          tableRows={data.daily_volume.map((row) => [
            row.date, row.documents, row.low_concern, row.review_recommended, row.high_concern,
          ])}
        >
          <DailyVolumeChart data={data.daily_volume} />
        </ChartCard>
      </div>

      <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-4">
        <ChartCard
          title="Documents by status"
          description="Where each upload sits in the pipeline"
          tableColumns={["Status", "Documents"]}
          tableRows={data.documents_by_status.map((row) => [
            PROCESSING_STATUS_LABEL[row.status] ?? humanise(row.status), row.count,
          ])}
        >
          <CategoryBarChart
            height={190}
            labelWidth={108}
            data={data.documents_by_status.map((row) => ({
              label: PROCESSING_STATUS_LABEL[row.status] ?? humanise(row.status),
              count: row.count,
            }))}
          />
        </ChartCard>

        <ChartCard
          title="Document types"
          description="As classified by the lexical-structural classifier"
          tableColumns={["Type", "Documents"]}
          tableRows={data.document_types.map((row) => [row.label, row.count])}
        >
          <CategoryBarChart
            height={190}
            data={data.document_types.slice(0, 7).map((row) => ({
              label: row.label,
              count: row.count,
            }))}
          />
        </ChartCard>

        <ChartCard
          title="Findings by detector family"
          description="Split by whether a reviewer has adjudicated them"
          tableColumns={["Family", "Total", "Awaiting review"]}
          tableRows={findingRows.map((row) => [humanise(row.kind), row.total, row.open])}
        >
          <FindingsByKindChart data={findingRows} />
        </ChartCard>

        <ChartCard
          title="Verification outcomes"
          description={data.verification_note}
          tableColumns={["Outcome", "Checks"]}
          tableRows={data.verification_outcomes.map((row) => [humanise(row.outcome), row.count])}
        >
          <VerificationOutcomeChart data={data.verification_outcomes} />
        </ChartCard>
      </div>

      <section className="panel">
        <header className="panel-header">
          <div>
            <h2 className="text-xs font-semibold">Recent investigations</h2>
            <p className="mt-0.5 text-2xs text-muted-foreground">
              Cases opened automatically by the risk engine or manually by an investigator
            </p>
          </div>
          <Button variant="outline" size="sm" asChild>
            <Link href="/investigations">All investigations</Link>
          </Button>
        </header>
        <TableWrap>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Case</TableHead>
                <TableHead>Claim</TableHead>
                <TableHead>Document</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Risk</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Priority</TableHead>
                <TableHead>Assigned</TableHead>
                <TableHead>Opened</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.recent_investigations.length === 0 && (
                <TableEmpty colSpan={10}>No investigations have been opened.</TableEmpty>
              )}
              {data.recent_investigations.map((investigation) => (
                <TableRow key={investigation.id}>
                  <TableCell className="font-mono text-2xs">{investigation.case_number}</TableCell>
                  <TableCell>
                    {investigation.claim_id ? (
                      <Link
                        className="font-medium text-primary hover:underline"
                        href={`/claims/${investigation.claim_id}`}
                      >
                        {investigation.claim_number}
                      </Link>
                    ) : (
                      "—"
                    )}
                    <span className="block text-2xs text-muted-foreground">
                      {investigation.customer_name ?? ""}
                    </span>
                  </TableCell>
                  <TableCell className="font-mono text-2xs">
                    {investigation.document_id ? (
                      <Link
                        className="text-primary hover:underline"
                        href={`/documents/${investigation.document_id}`}
                      >
                        {investigation.document_ref}
                      </Link>
                    ) : (
                      "—"
                    )}
                  </TableCell>
                  <TableCell className="text-2xs">{investigation.document_type ?? "—"}</TableCell>
                  <TableCell>
                    <RiskBadge
                      size="sm"
                      band={investigation.risk_band ?? null}
                      score={investigation.risk_score ?? null}
                    />
                  </TableCell>
                  <TableCell>
                    <InvestigationStatusChip status={investigation.status} />
                  </TableCell>
                  <TableCell>
                    <PriorityChip priority={investigation.priority} />
                  </TableCell>
                  <TableCell className="text-2xs">
                    {investigation.assigned_to?.full_name ?? (
                      <span className="text-muted-foreground">Unassigned</span>
                    )}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-2xs text-muted-foreground">
                    {relativeTime(investigation.created_at)}
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

      <div className="grid gap-3 lg:grid-cols-3">
        <section className="panel lg:col-span-2">
          <header className="panel-header">
            <h2 className="text-xs font-semibold">Pipeline throughput</h2>
            <span className="text-2xs text-muted-foreground">
              Analysis runs by final state
            </span>
          </header>
          <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3">
            {Object.entries(data.pipeline_runs).map(([status, value]) => (
              <div key={status} className="rounded-md border bg-muted/30 p-3">
                <p className="text-2xs uppercase tracking-wider text-muted-foreground">
                  {PROCESSING_STATUS_LABEL[status] ?? humanise(status)}
                </p>
                <p className="tabular text-lg font-semibold">{value.count}</p>
                <p className="text-2xs text-muted-foreground">
                  mean {(value.avg_duration_ms / 1000).toFixed(1)}s per run
                </p>
              </div>
            ))}
            {Object.keys(data.pipeline_runs).length === 0 && (
              <EmptyState title="No analysis runs yet" description="Upload a document to start." />
            )}
          </div>
        </section>

        <section className="panel">
          <header className="panel-header">
            <h2 className="text-xs font-semibold">Claims by status</h2>
          </header>
          <ul className="divide-y">
            {data.claims_by_status.map((row) => (
              <li key={row.status} className="flex items-center justify-between px-4 py-2.5">
                <span className="text-xs">{humanise(row.status)}</span>
                <Badge variant="muted">{row.count}</Badge>
              </li>
            ))}
            {data.claims_by_status.length === 0 && (
              <li className="px-4 py-6 text-center text-2xs text-muted-foreground">
                No claims recorded.
              </li>
            )}
          </ul>
        </section>
      </div>

      <UncertaintyNote />
    </>
  );
}
