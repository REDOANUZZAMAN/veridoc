"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  Activity, AlertTriangle, Fingerprint, GitCompareArrows, Landmark, ListChecks, ScanEye,
  ScrollText, ShieldAlert, SquareStack,
} from "lucide-react";

import { FindingCard } from "@/components/documents/finding-card";
import {
  AigcPanel, AuditPanel, ConsistencyPanel, CrossDocumentPanel, ExtractedDataPanel,
  ForensicsPanel, TamperingPanel, VerificationPanel,
} from "@/components/documents/panels";
import { FindingReviewButtons, ReviewActionBar } from "@/components/documents/review-actions";
import { DocumentViewer, regionsFromFindings, type ViewerRegion } from "@/components/documents/viewer";
import { KeyValue } from "@/components/shared/page-header";
import { PipelineTimeline } from "@/components/shared/pipeline-timeline";
import { RiskBadge, RiskScoreMeter } from "@/components/shared/risk-badge";
import { SeverityBadge } from "@/components/shared/severity-badge";
import { ProcessingStatusChip, VerificationStateChip } from "@/components/shared/status-chip";
import { ProvenanceLegend, UncertaintyNote } from "@/components/shared/uncertainty-note";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TooltipProvider } from "@/components/ui/tooltip";
import { formatBytes, formatDate, humanise, percent } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { AuditEntry, DocumentDetail, ExtractedField } from "@/lib/types";

const SEVERITY_RANK: Record<string, number> = {
  critical: 0, high: 1, medium: 2, low: 3, info: 4,
};

/**
 * The investigation workstation.
 *
 * Split screen by design: the document on the left never leaves view, and every
 * finding on the right can put a box around the pixels it is talking about. An
 * investigator should never have to hold a claim in their head while switching
 * screens to check what a signal refers to.
 */
export function Workstation({
  document,
  auditEntries,
  permissions,
}: {
  document: DocumentDetail;
  auditEntries: AuditEntry[];
  permissions: string[];
}) {
  const [activeFindingId, setActiveFindingId] = useState<string | null>(null);
  const [activeField, setActiveField] = useState<ExtractedField | null>(null);

  const findings = useMemo(
    () =>
      [...document.findings].sort(
        (a, b) =>
          (SEVERITY_RANK[a.severity] ?? 9) - (SEVERITY_RANK[b.severity] ?? 9) ||
          b.confidence - a.confidence,
      ),
    [document.findings],
  );

  const regions: ViewerRegion[] = useMemo(() => {
    const base = regionsFromFindings(findings);
    if (activeField?.bbox && activeField.page) {
      base.push({
        id: `field:${activeField.field_key}`,
        page: activeField.page,
        region: activeField.bbox,
        label: `${activeField.field_label}: ${activeField.value ?? ""}`,
        severity: "info",
        kind: "field",
      });
    }
    return base;
  }, [findings, activeField]);

  const counts = document.finding_counts ?? {};
  const bySeverity = counts.by_severity ?? {};
  const byKind = counts.by_kind ?? {};
  const openHigh = findings.filter(
    (finding) => finding.status === "open" && ["high", "critical"].includes(finding.severity),
  ).length;

  const risk = document.risk_assessment;
  const degraded = (risk?.coverage?.degraded_stages as string[] | undefined) ?? [];
  const positiveFindings = findings.filter((finding) => finding.severity === "info");

  const tabs = [
    { value: "overview", label: "Overview", icon: ListChecks },
    { value: "extracted", label: "Extracted data", icon: SquareStack, count: document.extracted_fields.length },
    { value: "forensics", label: "Forensics", icon: Fingerprint, count: byKind.forensic },
    { value: "aigc", label: "AIGC analysis", icon: ScanEye, count: byKind.aigc },
    { value: "tampering", label: "Tampering", icon: ShieldAlert, count: byKind.tampering },
    { value: "consistency", label: "Consistency", icon: ListChecks, count: byKind.consistency },
    { value: "crossdoc", label: "Cross-document", icon: GitCompareArrows, count: byKind.cross_document },
    { value: "verification", label: "Verification", icon: Landmark, count: document.verification.length },
    { value: "audit", label: "Audit trail", icon: Activity, count: auditEntries.length },
  ];

  return (
    <TooltipProvider>
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <ReviewActionBar
            documentId={document.id}
            permissions={permissions}
            verificationState={document.verification_state}
            hasClaim={Boolean(document.claim_id)}
            openHighFindings={openHigh}
          />
        </div>

        <div className="grid min-h-0 gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] 2xl:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
          {/* LEFT: the document itself */}
          <div className="min-w-0 xl:sticky xl:top-[4.25rem] xl:self-start">
            <DocumentViewer
              documentId={document.id}
              documentRef={document.document_ref}
              filename={document.original_filename}
              pages={document.pages}
              regions={regions}
              activeId={activeFindingId ?? (activeField ? `field:${activeField.field_key}` : null)}
              onSelect={(id) => {
                setActiveFindingId(id);
                if (id) setActiveField(null);
              }}
              canDownload={permissions.includes("document:download")}
            />
          </div>

          {/* RIGHT: the investigation */}
          <div className="min-w-0">
            <Tabs defaultValue="overview">
              <TabsList className="w-full justify-start">
                {tabs.map((tab) => {
                  const Icon = tab.icon;
                  return (
                    <TabsTrigger key={tab.value} value={tab.value}>
                      <Icon className="size-3.5" />
                      {tab.label}
                      {tab.count ? (
                        <span className="tabular ml-0.5 rounded bg-muted px-1 text-2xs text-muted-foreground">
                          {tab.count}
                        </span>
                      ) : null}
                    </TabsTrigger>
                  );
                })}
              </TabsList>

              {/* ----------------------------------------------------- overview */}
              <TabsContent value="overview" className="space-y-3">
                <section
                  className={cn(
                    "rounded-lg border p-4",
                    risk?.band === "high_concern" && "border-risk-high/40 bg-risk-high/5",
                    risk?.band === "review_recommended" && "border-risk-review/40 bg-risk-review/5",
                    risk?.band === "low_concern" && "border-risk-low/40 bg-risk-low/5",
                    !risk && "bg-muted/40",
                  )}
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="space-y-1">
                      <p className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
                        Overall assessment
                      </p>
                      <RiskBadge band={risk?.band ?? null} score={risk?.score ?? null} size="lg" />
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <ProcessingStatusChip status={document.processing_status} />
                      <VerificationStateChip state={document.verification_state} />
                    </div>
                  </div>

                  {risk && (
                    <div className="mt-4 space-y-3">
                      <RiskScoreMeter score={risk.score} band={risk.band} />
                      <p className="text-2xs leading-relaxed">{risk.explanation}</p>
                      <p className="text-2xs italic leading-relaxed text-muted-foreground">
                        {risk.interpretation_note}
                      </p>
                    </div>
                  )}

                  {!risk && (
                    <p className="mt-3 text-2xs text-muted-foreground">
                      No risk assessment has been recorded yet.{" "}
                      {document.processing_message ?? ""}
                    </p>
                  )}
                </section>

                {degraded.length > 0 && (
                  <div className="flex gap-2 rounded-md border border-risk-review/30 bg-risk-review/8 p-3">
                    <AlertTriangle className="mt-0.5 size-4 shrink-0 text-risk-review" />
                    <div className="space-y-0.5">
                      <p className="text-2xs font-semibold">Partial coverage</p>
                      <p className="text-2xs leading-relaxed text-muted-foreground">
                        {degraded.length} stage{degraded.length === 1 ? "" : "s"} did not complete:{" "}
                        {degraded.join(", ")}. Findings from those areas are absent by omission, not
                        by exclusion — re-run the analysis once the provider is available.
                      </p>
                    </div>
                  </div>
                )}

                {risk?.top_reasons?.length ? (
                  <section className="panel">
                    <header className="panel-header">
                      <h3 className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
                        Why this score
                      </h3>
                      <span className="text-2xs text-muted-foreground">
                        weights {risk.weights_version}
                      </span>
                    </header>
                    <ul className="divide-y">
                      {risk.top_reasons.map((reason) => (
                        <li key={`${reason.code}-${reason.finding_id ?? ""}`} className="px-4 py-2.5">
                          <div className="flex flex-wrap items-center gap-2">
                            <SeverityBadge severity={reason.severity} withIcon={false} />
                            <span className="min-w-0 flex-1 truncate text-xs">{reason.label}</span>
                            <span className="tabular text-2xs text-muted-foreground">
                              +{reason.contribution.toFixed(1)}
                            </span>
                            {reason.finding_id && (
                              <Button
                                variant="ghost"
                                size="xs"
                                onClick={() => setActiveFindingId(reason.finding_id!)}
                              >
                                Show
                              </Button>
                            )}
                          </div>
                          <p className="mt-0.5 text-2xs text-muted-foreground">
                            {reason.category} · confidence {percent(reason.confidence)} ·{" "}
                            {humanise(reason.source)}
                          </p>
                        </li>
                      ))}
                    </ul>
                    <footer className="border-t px-4 py-2">
                      <p className="font-mono text-2xs text-muted-foreground">
                        {(risk as any).formula ??
                          "contribution = weight x confidence x severity_multiplier"}
                      </p>
                    </footer>
                  </section>
                ) : null}

                <section className="panel">
                  <header className="panel-header">
                    <div>
                      <h3 className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
                        All findings
                      </h3>
                      <p className="mt-0.5 text-2xs text-muted-foreground">
                        {counts.total ?? 0} total · {counts.open ?? 0} awaiting review ·{" "}
                        {counts.confirmed ?? 0} confirmed · {counts.dismissed ?? 0} dismissed
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {["critical", "high", "medium", "low", "info"].map((severity) =>
                        bySeverity[severity] ? (
                          <SeverityBadge
                            key={severity}
                            severity={severity as any}
                            withIcon={false}
                          />
                        ) : null,
                      )}
                    </div>
                  </header>
                  <div className="space-y-2 p-3">
                    {findings.length === 0 && (
                      <p className="py-6 text-center text-2xs text-muted-foreground">
                        No findings were raised by the stages that completed.
                      </p>
                    )}
                    {findings.map((finding) => (
                      <FindingCard
                        key={finding.finding_id}
                        finding={finding}
                        active={activeFindingId === finding.finding_id}
                        onSelect={(id) => {
                          setActiveFindingId(id);
                          setActiveField(null);
                        }}
                        actions={
                          <FindingReviewButtons
                            documentId={document.id}
                            finding={finding}
                            permissions={permissions}
                          />
                        }
                      />
                    ))}
                  </div>
                  <footer className="border-t px-4 py-2">
                    <ProvenanceLegend />
                  </footer>
                </section>

                <section className="panel">
                  <header className="panel-header">
                    <h3 className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Processing pipeline
                    </h3>
                    {document.latest_run && (
                      <span className="text-2xs text-muted-foreground">
                        pipeline {document.latest_run.pipeline_version} · rules{" "}
                        {document.latest_run.rules_version} ·{" "}
                        {((document.latest_run.duration_ms ?? 0) / 1000).toFixed(1)}s ·{" "}
                        {document.latest_run.queue_mode}
                      </span>
                    )}
                  </header>
                  <PipelineTimeline stages={document.latest_run?.stages ?? []} />
                </section>

                <section className="panel">
                  <header className="panel-header">
                    <h3 className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Document facts
                    </h3>
                  </header>
                  <div className="p-4">
                    <KeyValue
                      columns={2}
                      items={[
                        { label: "Reference", value: document.document_ref, mono: true },
                        { label: "Original filename", value: document.original_filename },
                        {
                          label: "Detected type",
                          value: `${document.classification_label ?? "—"} · ${percent(
                            document.classification_confidence,
                          )} confidence`,
                        },
                        {
                          label: "File",
                          value: `${document.mime_type} · ${formatBytes(document.file_size)} · ${
                            document.page_count
                          } page(s)`,
                        },
                        { label: "SHA-256 at ingest", value: document.sha256, mono: true },
                        { label: "Intake source", value: humanise(document.source) },
                        {
                          label: "Uploaded",
                          value: `${formatDate(document.uploaded_at, true)} by ${
                            document.uploaded_by?.full_name ?? "unknown"
                          }`,
                        },
                        {
                          label: "Security scan",
                          value: `${humanise(document.malware_status)} · ${
                            document.malware_detail?.scanner ?? "—"
                          }`,
                          hint: document.malware_detail?.message,
                        },
                        {
                          label: "Claim",
                          value: document.claim_id ? (
                            <Link className="text-primary hover:underline" href={`/claims/${document.claim_id}`}>
                              {document.claim_number}
                            </Link>
                          ) : (
                            "Unattached"
                          ),
                        },
                        {
                          label: "Retention",
                          value: document.retention_expires_at
                            ? formatDate(document.retention_expires_at)
                            : "Not scheduled",
                        },
                      ]}
                    />
                    {document.processing_message && (
                      <p className="mt-3 rounded border bg-muted/40 px-2.5 py-2 text-2xs leading-relaxed text-muted-foreground">
                        {document.processing_message}
                      </p>
                    )}
                  </div>
                </section>

                {positiveFindings.length > 0 && (
                  <section className="panel">
                    <header className="panel-header">
                      <h3 className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
                        Checks that produced no concern
                      </h3>
                    </header>
                    <div className="space-y-2 p-3">
                      {positiveFindings.map((finding) => (
                        <FindingCard key={finding.finding_id} finding={finding} compact />
                      ))}
                    </div>
                  </section>
                )}

                <UncertaintyNote />
              </TabsContent>

              <TabsContent value="extracted">
                <ExtractedDataPanel
                  document={document}
                  activeFieldKey={activeField?.field_key ?? null}
                  onHighlightField={(field) => {
                    setActiveField(field);
                    setActiveFindingId(null);
                  }}
                />
              </TabsContent>

              <TabsContent value="forensics">
                <ForensicsPanel
                  document={document}
                  documentId={document.id}
                  permissions={permissions}
                  activeId={activeFindingId}
                  onSelect={setActiveFindingId}
                />
              </TabsContent>

              <TabsContent value="aigc">
                <AigcPanel
                  document={document}
                  documentId={document.id}
                  permissions={permissions}
                  activeId={activeFindingId}
                  onSelect={setActiveFindingId}
                />
              </TabsContent>

              <TabsContent value="tampering">
                <TamperingPanel
                  document={document}
                  documentId={document.id}
                  permissions={permissions}
                  activeId={activeFindingId}
                  onSelect={setActiveFindingId}
                />
              </TabsContent>

              <TabsContent value="consistency">
                <ConsistencyPanel
                  document={document}
                  documentId={document.id}
                  permissions={permissions}
                  activeId={activeFindingId}
                  onSelect={setActiveFindingId}
                />
              </TabsContent>

              <TabsContent value="crossdoc">
                <CrossDocumentPanel
                  document={document}
                  documentId={document.id}
                  permissions={permissions}
                  activeId={activeFindingId}
                  onSelect={setActiveFindingId}
                />
              </TabsContent>

              <TabsContent value="verification">
                <VerificationPanel
                  document={document}
                  canRun={permissions.includes("verification:run")}
                />
              </TabsContent>

              <TabsContent value="audit">
                <AuditPanel document={document} auditEntries={auditEntries} />
              </TabsContent>
            </Tabs>
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}
