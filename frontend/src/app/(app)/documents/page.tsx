import type { Metadata } from "next";
import Link from "next/link";
import { FileStack } from "lucide-react";

import { DocumentFilters } from "@/components/documents/document-filters";
import { UploadDialog } from "@/components/documents/upload-dialog";
import { EmptyState, PageHeader } from "@/components/shared/page-header";
import { RiskBadge } from "@/components/shared/risk-badge";
import { ProcessingStatusChip, VerificationStateChip } from "@/components/shared/status-chip";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableEmpty, TableHead, TableHeader, TableRow, TableWrap,
} from "@/components/ui/table";
import { api, apiSafe } from "@/lib/api";
import { formatBytes, percent, relativeTime } from "@/lib/format";
import { can, getSessionUser } from "@/lib/session";
import type { ClaimSummary, DocumentSummary, Paged } from "@/lib/types";

export const metadata: Metadata = { title: "Documents" };

const DOCUMENT_TYPES = [
  ["medical_invoice", "Medical Invoice"], ["hospital_bill", "Hospital Bill"],
  ["prescription", "Prescription"], ["identity_document", "Identity Document"],
  ["insurance_certificate", "Insurance Certificate"], ["claim_form", "Claim Form"],
  ["vehicle_document", "Vehicle Document"], ["repair_estimate", "Repair Estimate"],
  ["receipt", "Receipt"], ["police_report", "Police Report"],
  ["bank_payment_document", "Bank / Payment Document"], ["other", "Other"],
].map(([value, label]) => ({ value, label }));

export default async function DocumentsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const params = await searchParams;
  const page = Number(params.page ?? 1);
  const user = await getSessionUser();

  const [documents, claims] = await Promise.all([
    api<Paged<DocumentSummary>>("/documents", {
      searchParams: {
        page,
        page_size: 25,
        status: params.status,
        risk_band: params.risk_band,
        document_type: params.document_type,
        verification_state: params.verification_state,
        search: params.search,
        claim_id: params.claim_id,
        sort: params.sort ?? "uploaded_at",
        order: params.order ?? "desc",
      },
    }),
    apiSafe<Paged<ClaimSummary>>("/claims", { searchParams: { page_size: 100 } }),
  ]);

  const query = new URLSearchParams(
    Object.entries(params).filter(([, value]) => value) as [string, string][],
  );

  return (
    <>
      <PageHeader
        title="Documents"
        description="Every ingested document, its pipeline state and the triage band the risk engine
          assigned. Open one to see the evidence behind the band."
        actions={
          can(user, "document:upload") ? (
            <UploadDialog
              claims={(claims?.items ?? []).map((claim) => ({
                id: claim.id,
                claim_number: claim.claim_number,
                customer_name: claim.customer_name,
              }))}
            />
          ) : null
        }
      />

      <DocumentFilters documentTypes={DOCUMENT_TYPES} />

      <section className="panel">
        <header className="panel-header">
          <p className="text-2xs text-muted-foreground">
            <span className="tabular font-semibold text-foreground">{documents.meta.total}</span>{" "}
            document{documents.meta.total === 1 ? "" : "s"}
            {documents.meta.pages > 1 &&
              ` · page ${documents.meta.page} of ${documents.meta.pages}`}
          </p>
        </header>

        <TableWrap>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Reference</TableHead>
                <TableHead>Document</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Claim</TableHead>
                <TableHead>Risk</TableHead>
                <TableHead>Findings</TableHead>
                <TableHead>Pipeline</TableHead>
                <TableHead>Human verdict</TableHead>
                <TableHead>Uploaded</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {documents.items.length === 0 && (
                <TableEmpty colSpan={10}>
                  No documents match these filters.
                </TableEmpty>
              )}
              {documents.items.map((document) => {
                const severities = document.finding_counts.by_severity ?? {};
                const high = (severities.critical ?? 0) + (severities.high ?? 0);
                return (
                  <TableRow key={document.id}>
                    <TableCell className="whitespace-nowrap font-mono text-2xs">
                      <Link className="text-primary hover:underline" href={`/documents/${document.id}`}>
                        {document.document_ref}
                      </Link>
                    </TableCell>
                    <TableCell className="max-w-[240px]">
                      <span className="block truncate text-xs" title={document.original_filename}>
                        {document.original_filename}
                      </span>
                      <span className="block text-2xs text-muted-foreground">
                        {document.file_extension.toUpperCase()} · {formatBytes(document.file_size)} ·{" "}
                        {document.page_count} page{document.page_count === 1 ? "" : "s"}
                      </span>
                    </TableCell>
                    <TableCell className="min-w-[7.5rem] text-xs">
                      {document.classification_label ?? "—"}
                      {document.classification_confidence != null && (
                        <span className="block text-2xs text-muted-foreground">
                          {percent(document.classification_confidence)} confidence
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-2xs">
                      {document.claim_id ? (
                        <Link className="text-primary hover:underline" href={`/claims/${document.claim_id}`}>
                          {document.claim_number}
                        </Link>
                      ) : (
                        <span className="text-muted-foreground">Unattached</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <RiskBadge size="sm" band={document.risk_band} score={document.risk_score} />
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Badge variant="muted">{document.finding_counts.total ?? 0}</Badge>
                        {high > 0 && <Badge variant="high">{high} high+</Badge>}
                      </div>
                    </TableCell>
                    <TableCell>
                      <ProcessingStatusChip status={document.processing_status} />
                    </TableCell>
                    <TableCell>
                      <VerificationStateChip state={document.verification_state} />
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-2xs text-muted-foreground">
                      {relativeTime(document.uploaded_at)}
                      <span className="block">{document.uploaded_by?.full_name ?? "—"}</span>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="xs" asChild>
                        <Link href={`/documents/${document.id}`}>Investigate</Link>
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableWrap>

        {documents.meta.pages > 1 && (
          <footer className="flex items-center justify-between border-t px-4 py-2.5">
            <Button variant="outline" size="sm" disabled={!documents.meta.has_previous} asChild>
              <Link
                href={`/documents?${new URLSearchParams({
                  ...Object.fromEntries(query),
                  page: String(documents.meta.page - 1),
                })}`}
              >
                Previous
              </Link>
            </Button>
            <span className="tabular text-2xs text-muted-foreground">
              {documents.meta.page} / {documents.meta.pages}
            </span>
            <Button variant="outline" size="sm" disabled={!documents.meta.has_next} asChild>
              <Link
                href={`/documents?${new URLSearchParams({
                  ...Object.fromEntries(query),
                  page: String(documents.meta.page + 1),
                })}`}
              >
                Next
              </Link>
            </Button>
          </footer>
        )}
      </section>
    </>
  );
}
