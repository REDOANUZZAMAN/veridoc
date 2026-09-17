import type { Metadata } from "next";
import Link from "next/link";

import { PageHeader } from "@/components/shared/page-header";
import { RiskBadge } from "@/components/shared/risk-badge";
import { InvestigationStatusChip, PriorityChip } from "@/components/shared/status-chip";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableEmpty, TableHead, TableHeader, TableRow, TableWrap,
} from "@/components/ui/table";
import { api, apiSafe } from "@/lib/api";
import { formatDate, relativeTime } from "@/lib/format";
import type { Investigation, Paged } from "@/lib/types";

export const metadata: Metadata = { title: "Investigations" };

export default async function InvestigationsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const params = await searchParams;
  const [investigations, workload] = await Promise.all([
    api<Paged<Investigation>>("/investigations", {
      searchParams: {
        page: Number(params.page ?? 1),
        page_size: 30,
        status: params.status,
        priority: params.priority,
        mine: params.mine,
      },
    }),
    apiSafe<{ items: Array<{ full_name: string; email: string; assigned_investigations: number }> }>(
      "/users/workload",
    ),
  ]);

  const filters: Array<[string, string]> = [
    ["", "All"],
    ["open", "Open"],
    ["in_progress", "In progress"],
    ["pending_information", "Pending information"],
    ["escalated", "Escalated"],
    ["closed", "Closed"],
  ];

  return (
    <>
      <PageHeader
        title="Investigations"
        description="Cases are opened automatically when a claim reaches High Concern, and manually when an
          investigator escalates. A case is only closed with a recorded resolution."
      />

      <div className="flex flex-wrap items-center gap-1.5">
        {filters.map(([value, label]) => (
          <Button
            key={label}
            variant={(params.status ?? "") === value ? "secondary" : "ghost"}
            size="sm"
            asChild
          >
            <Link href={value ? `/investigations?status=${value}` : "/investigations"}>{label}</Link>
          </Button>
        ))}
        <Button variant={params.mine ? "secondary" : "ghost"} size="sm" asChild>
          <Link href="/investigations?mine=true">Assigned to me</Link>
        </Button>
      </div>

      <div className="grid gap-3 lg:grid-cols-4">
        <section className="panel lg:col-span-3">
          <header className="panel-header">
            <p className="text-2xs text-muted-foreground">
              <span className="tabular font-semibold text-foreground">
                {investigations.meta.total}
              </span>{" "}
              case{investigations.meta.total === 1 ? "" : "s"}
            </p>
          </header>
          <TableWrap>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Case</TableHead>
                  <TableHead>Claim</TableHead>
                  <TableHead>Title</TableHead>
                  <TableHead>Risk</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Priority</TableHead>
                  <TableHead>Assigned</TableHead>
                  <TableHead>Notes</TableHead>
                  <TableHead>Opened</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {investigations.items.length === 0 && (
                  <TableEmpty colSpan={10}>No cases match this filter.</TableEmpty>
                )}
                {investigations.items.map((investigation) => (
                  <TableRow key={investigation.id}>
                    <TableCell className="font-mono text-2xs">
                      <Link
                        className="text-primary hover:underline"
                        href={`/investigations/${investigation.id}`}
                      >
                        {investigation.case_number}
                      </Link>
                    </TableCell>
                    <TableCell className="text-2xs">
                      {investigation.claim_id ? (
                        <Link
                          className="text-primary hover:underline"
                          href={`/claims/${investigation.claim_id}`}
                        >
                          {investigation.claim_number}
                        </Link>
                      ) : (
                        "—"
                      )}
                      <span className="block text-muted-foreground">
                        {investigation.customer_name}
                      </span>
                    </TableCell>
                    <TableCell className="max-w-[280px] text-2xs">{investigation.title}</TableCell>
                    <TableCell>
                      <RiskBadge
                        size="sm"
                        band={investigation.risk_band ?? null}
                        score={investigation.risk_score ?? investigation.risk_score_at_open}
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
                    <TableCell>
                      <Badge variant="muted">{investigation.note_count}</Badge>
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-2xs text-muted-foreground">
                      {relativeTime(investigation.opened_at ?? investigation.created_at)}
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

        <section className="panel">
          <header className="panel-header">
            <h2 className="text-xs font-semibold">Caseload</h2>
          </header>
          <ul className="divide-y">
            {(workload?.items ?? []).map((row) => (
              <li key={row.email} className="flex items-center justify-between gap-2 px-4 py-2.5">
                <div className="min-w-0">
                  <p className="truncate text-2xs font-medium">{row.full_name}</p>
                  <p className="truncate text-2xs text-muted-foreground">{row.email}</p>
                </div>
                <Badge variant={row.assigned_investigations > 2 ? "review" : "muted"}>
                  {row.assigned_investigations}
                </Badge>
              </li>
            ))}
            {!(workload?.items ?? []).length && (
              <li className="px-4 py-6 text-center text-2xs text-muted-foreground">
                No workload data.
              </li>
            )}
          </ul>
        </section>
      </div>
    </>
  );
}
