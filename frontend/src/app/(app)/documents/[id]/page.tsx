import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ChevronRight } from "lucide-react";

import { Workstation } from "@/components/documents/workstation";
import { PageHeader } from "@/components/shared/page-header";
import { RiskBadge } from "@/components/shared/risk-badge";
import { Badge } from "@/components/ui/badge";
import { ApiError, api, apiSafe } from "@/lib/api";
import { getSessionUser } from "@/lib/session";
import type { AuditEntry, DocumentDetail, Paged } from "@/lib/types";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const document = await apiSafe<DocumentDetail>(`/documents/${id}`);
  return { title: document ? `${document.document_ref} · Investigation` : "Document" };
}

export default async function DocumentInvestigationPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const user = await getSessionUser();

  let document: DocumentDetail;
  try {
    document = await api<DocumentDetail>(`/documents/${id}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  // The audit panel is best-effort: a claims officer may read a document without
  // holding audit:read, and that must not break the page.
  const audit = await apiSafe<Paged<AuditEntry>>("/audit-logs", {
    searchParams: { resource_id: document.id, page_size: 60 },
  });

  return (
    <>
      <PageHeader
        breadcrumb={
          <span className="flex items-center gap-1">
            <Link href="/documents" className="hover:text-foreground hover:underline">
              Documents
            </Link>
            <ChevronRight className="size-3" />
            {document.claim_id ? (
              <>
                <Link
                  href={`/claims/${document.claim_id}`}
                  className="hover:text-foreground hover:underline"
                >
                  {document.claim_number}
                </Link>
                <ChevronRight className="size-3" />
              </>
            ) : null}
            <span className="font-mono">{document.document_ref}</span>
          </span>
        }
        title={
          <span className="flex flex-wrap items-center gap-2">
            {document.classification_label ?? "Unclassified document"}
            <Badge variant="outline" className="font-mono">
              {document.document_ref}
            </Badge>
          </span>
        }
        description={document.original_filename}
        actions={
          <RiskBadge band={document.risk_band} score={document.risk_score} size="default" />
        }
      />

      <Workstation
        document={document}
        auditEntries={audit?.items ?? []}
        permissions={user?.permissions ?? []}
      />
    </>
  );
}
