import type { Metadata } from "next";
import Link from "next/link";
import { Download, FileCheck2 } from "lucide-react";

import { PageHeader } from "@/components/shared/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableEmpty, TableHead, TableHeader, TableRow, TableWrap,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatBytes, formatDate, humanise, truncateHash } from "@/lib/format";
import type { Paged, ReportSummary } from "@/lib/types";

export const metadata: Metadata = { title: "Reports" };

export default async function ReportsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const params = await searchParams;
  const reports = await api<Paged<ReportSummary>>("/reports", {
    searchParams: { page: Number(params.page ?? 1), page_size: 30 },
  });

  return (
    <>
      <PageHeader
        title="Evidence reports"
        description="Each report is a point-in-time snapshot: the document hash, the pipeline and rules
          versions, every finding with its provenance, the verification answers and their data
          source, the reviewer actions and the audit-chain state at the moment of generation."
      />

      <section className="panel">
        <header className="panel-header">
          <p className="text-2xs text-muted-foreground">
            <span className="tabular font-semibold text-foreground">{reports.meta.total}</span>{" "}
            report{reports.meta.total === 1 ? "" : "s"}
          </p>
        </header>
        <TableWrap>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Reference</TableHead>
                <TableHead>Title</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Subject</TableHead>
                <TableHead>Report hash</TableHead>
                <TableHead>Document hash</TableHead>
                <TableHead>Versions</TableHead>
                <TableHead>Size</TableHead>
                <TableHead>Generated</TableHead>
                <TableHead className="text-right">PDF</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {reports.items.length === 0 && (
                <TableEmpty colSpan={10}>
                  No reports have been generated. Open a document and use “Generate report”.
                </TableEmpty>
              )}
              {reports.items.map((report) => (
                <TableRow key={report.id}>
                  <TableCell className="whitespace-nowrap font-mono text-2xs">
                    {report.report_ref}
                  </TableCell>
                  <TableCell className="max-w-[280px] text-2xs">
                    <span className="block truncate" title={report.title}>
                      {report.title}
                    </span>
                  </TableCell>
                  <TableCell className="text-2xs">{humanise(report.report_type)}</TableCell>
                  <TableCell className="text-2xs">
                    {report.document_id && (
                      <Link
                        className="text-primary hover:underline"
                        href={`/documents/${report.document_id}`}
                      >
                        Document
                      </Link>
                    )}
                    {report.document_id && report.claim_id ? " · " : ""}
                    {report.claim_id && (
                      <Link className="text-primary hover:underline" href={`/claims/${report.claim_id}`}>
                        Claim
                      </Link>
                    )}
                  </TableCell>
                  <TableCell className="font-mono text-2xs text-muted-foreground">
                    {truncateHash(report.sha256)}
                  </TableCell>
                  <TableCell className="font-mono text-2xs text-muted-foreground">
                    {truncateHash(report.document_sha256)}
                  </TableCell>
                  <TableCell className="font-mono text-2xs text-muted-foreground">
                    {report.pipeline_version} / {report.rules_version}
                  </TableCell>
                  <TableCell className="tabular text-2xs">{formatBytes(report.file_size)}</TableCell>
                  <TableCell className="whitespace-nowrap text-2xs text-muted-foreground">
                    {formatDate(report.created_at, true)}
                    <span className="block">{report.generated_by?.full_name}</span>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="xs" asChild>
                      <a
                        href={`/api/be/reports/${report.id}/export?disposition=inline`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <Download className="size-3" /> Open
                      </a>
                    </Button>
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
