import type { Metadata } from "next";
import Link from "next/link";

import { CreateClaimDialog } from "@/components/claims/create-claim-dialog";
import { PageHeader } from "@/components/shared/page-header";
import { RiskBadge } from "@/components/shared/risk-badge";
import { ClaimStatusChip } from "@/components/shared/status-chip";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableEmpty, TableHead, TableHeader, TableRow, TableWrap,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatDate, formatMoney, humanise } from "@/lib/format";
import { can, getSessionUser } from "@/lib/session";
import type { ClaimSummary, Paged } from "@/lib/types";

export const metadata: Metadata = { title: "Claims" };

export default async function ClaimsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const params = await searchParams;
  const user = await getSessionUser();
  const claims = await api<Paged<ClaimSummary>>("/claims", {
    searchParams: {
      page: Number(params.page ?? 1),
      page_size: 25,
      status: params.status,
      risk_band: params.risk_band,
      search: params.search,
      sort: "created_at",
      order: "desc",
    },
  });

  const statuses = [
    ["", "All"],
    ["review_required", "Review required"],
    ["investigation", "Investigation"],
    ["processing", "Processing"],
    ["verified", "Verified"],
    ["resolved", "Resolved"],
  ];

  return (
    <>
      <PageHeader
        title="Claims"
        description="A claim is the unit of investigation: its documents are compared against each other
          and against the claim particulars, and its outcome is recorded by a named officer."
        actions={can(user, "claim:create") ? <CreateClaimDialog /> : null}
      />

      <div className="flex flex-wrap items-center gap-1.5">
        {statuses.map(([value, label]) => {
          const active = (params.status ?? "") === value;
          return (
            <Button key={label} variant={active ? "secondary" : "ghost"} size="sm" asChild>
              <Link href={value ? `/claims?status=${value}` : "/claims"}>{label}</Link>
            </Button>
          );
        })}
      </div>

      <section className="panel">
        <header className="panel-header">
          <p className="text-2xs text-muted-foreground">
            <span className="tabular font-semibold text-foreground">{claims.meta.total}</span> claim
            {claims.meta.total === 1 ? "" : "s"}
          </p>
        </header>
        <TableWrap>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Claim</TableHead>
                <TableHead>Customer</TableHead>
                <TableHead>Policy</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Amount</TableHead>
                <TableHead>Documents</TableHead>
                <TableHead>Open findings</TableHead>
                <TableHead>Risk</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Investigator</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {claims.items.length === 0 && (
                <TableEmpty colSpan={11}>No claims match this filter.</TableEmpty>
              )}
              {claims.items.map((claim) => (
                <TableRow key={claim.id}>
                  <TableCell className="whitespace-nowrap font-mono text-2xs">
                    <Link className="text-primary hover:underline" href={`/claims/${claim.id}`}>
                      {claim.claim_number}
                    </Link>
                  </TableCell>
                  <TableCell className="text-xs">{claim.customer_name}</TableCell>
                  <TableCell className="whitespace-nowrap font-mono text-2xs">{claim.policy_number}</TableCell>
                  <TableCell className="text-2xs">{humanise(claim.claim_type)}</TableCell>
                  <TableCell className="tabular whitespace-nowrap text-xs">
                    {formatMoney(claim.claimed_amount, claim.currency)}
                  </TableCell>
                  <TableCell>
                    <Badge variant="muted">{claim.document_count}</Badge>
                  </TableCell>
                  <TableCell>
                    {claim.open_findings > 0 ? (
                      <Badge variant="review">{claim.open_findings}</Badge>
                    ) : (
                      <span className="text-2xs text-muted-foreground">none</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <RiskBadge size="sm" band={claim.risk_band} score={claim.risk_score} />
                  </TableCell>
                  <TableCell>
                    <ClaimStatusChip status={claim.status} />
                  </TableCell>
                  <TableCell className="text-2xs">
                    {claim.assigned_investigator?.full_name ?? (
                      <span className="text-muted-foreground">Unassigned</span>
                    )}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-2xs text-muted-foreground">
                    {formatDate(claim.created_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableWrap>
      </section>
    </>
  );
}
