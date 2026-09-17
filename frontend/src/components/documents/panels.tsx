"use client";

import { useState } from "react";
import Link from "next/link";
import {
  AlertTriangle, Blocks, Braces, CheckCircle2, CircleSlash, Database, FileWarning,
  Fingerprint, Landmark, MinusCircle, Play, ScanEye, Search, Sparkles, XCircle,
} from "lucide-react";
import { toast } from "sonner";

import { FindingCard } from "@/components/documents/finding-card";
import { FindingReviewButtons } from "@/components/documents/review-actions";
import { DemoBadge, DemoNotice } from "@/components/shared/demo-notice";
import { EmptyState, KeyValue } from "@/components/shared/page-header";
import { SeverityBadge } from "@/components/shared/severity-badge";
import { OutcomeChip } from "@/components/shared/status-chip";
import { UncertaintyNote } from "@/components/shared/uncertainty-note";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table, TableBody, TableCell, TableEmpty, TableHead, TableHeader, TableRow, TableWrap,
} from "@/components/ui/table";
import { apiPost } from "@/lib/client";
import { formatDate, humanise, percent } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { DocumentDetail, ExtractedField, Finding } from "@/lib/types";

function FindingList({
  findings,
  documentId,
  permissions,
  activeId,
  onSelect,
  emptyTitle,
  emptyDescription,
  emptyIcon,
}: {
  findings: Finding[];
  documentId: string;
  permissions: string[];
  activeId: string | null;
  onSelect: (id: string | null) => void;
  emptyTitle: string;
  emptyDescription: string;
  emptyIcon?: React.ReactNode;
}) {
  if (!findings.length) {
    return <EmptyState icon={emptyIcon} title={emptyTitle} description={emptyDescription} />;
  }
  return (
    <div className="space-y-2">
      {findings.map((finding) => (
        <FindingCard
          key={finding.finding_id}
          finding={finding}
          active={activeId === finding.finding_id}
          onSelect={onSelect}
          actions={
            <FindingReviewButtons
              documentId={documentId}
              finding={finding}
              permissions={permissions}
            />
          }
        />
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ extracted */
export function ExtractedDataPanel({
  document,
  onHighlightField,
  activeFieldKey,
}: {
  document: DocumentDetail;
  onHighlightField: (field: ExtractedField | null) => void;
  activeFieldKey: string | null;
}) {
  const [query, setQuery] = useState("");
  const declared = document.schema_fields ?? [];
  const found = new Map(document.extracted_fields.map((field) => [field.field_key, field]));
  const missing = declared.filter(
    (spec) => spec.required && !found.get(spec.key)?.value,
  );

  const groups = new Map<string, ExtractedField[]>();
  for (const field of document.extracted_fields) {
    if (query && !`${field.field_label} ${field.value ?? ""}`.toLowerCase().includes(query.toLowerCase())) {
      continue;
    }
    const group = field.group ?? "general";
    groups.set(group, [...(groups.get(group) ?? []), field]);
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="outline">{document.schema_label ?? "Generic"} schema</Badge>
          <Badge variant="muted">{document.extracted_fields.length} fields</Badge>
          <Badge variant="muted">{document.line_items.length} line items</Badge>
          {missing.length > 0 && <Badge variant="review">{missing.length} required missing</Badge>}
        </div>
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Filter fields"
            className="h-8 w-52 pl-8 text-xs"
          />
        </div>
      </div>

      {missing.length > 0 && (
        <div className="rounded-md border border-risk-review/30 bg-risk-review/8 p-2.5">
          <p className="text-2xs font-semibold">Required fields not located</p>
          <p className="mt-0.5 text-2xs leading-relaxed text-muted-foreground">
            {missing.map((field) => field.label).join(", ")}. A missing identifier also blocks the
            verification route that depends on it.
          </p>
        </div>
      )}

      {Array.from(groups.entries()).map(([group, fields]) => (
        <section key={group} className="panel">
          <header className="panel-header">
            <h3 className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
              {humanise(group)}
            </h3>
          </header>
          <TableWrap>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Field</TableHead>
                  <TableHead>Value</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Confidence</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead className="text-right">Locate</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {fields.map((field) => (
                  <TableRow
                    key={field.field_key}
                    className={cn(activeFieldKey === field.field_key && "bg-primary/8")}
                  >
                    <TableCell className="text-xs">
                      {field.field_label}
                      {field.required && <span className="ml-1 text-risk-review">*</span>}
                    </TableCell>
                    <TableCell className="max-w-[260px] font-mono text-2xs">
                      <span className="block truncate" title={field.value ?? field.value_raw ?? ""}>
                        {field.value ?? field.value_raw ?? "—"}
                      </span>
                      {field.value && field.value_raw && field.value !== field.value_raw && (
                        <span className="block truncate text-muted-foreground" title={field.value_raw}>
                          raw: {field.value_raw}
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-2xs text-muted-foreground">{field.value_type}</TableCell>
                    <TableCell className="tabular text-2xs">{percent(field.confidence)}</TableCell>
                    <TableCell className="text-2xs text-muted-foreground">
                      {humanise(field.source)}
                    </TableCell>
                    <TableCell className="text-right">
                      {field.bbox && field.page ? (
                        <Button
                          variant="ghost"
                          size="xs"
                          onClick={() =>
                            onHighlightField(activeFieldKey === field.field_key ? null : field)
                          }
                        >
                          p{field.page}
                        </Button>
                      ) : (
                        <span className="text-2xs text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableWrap>
        </section>
      ))}

      {document.line_items.length > 0 && (
        <section className="panel">
          <header className="panel-header">
            <h3 className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
              Line items
            </h3>
            <span className="text-2xs text-muted-foreground">
              Summed and reconciled by the consistency engine
            </span>
          </header>
          <TableWrap>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>#</TableHead>
                  <TableHead>Extracted row</TableHead>
                  <TableHead>Normalised</TableHead>
                  <TableHead className="text-right">Locate</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {document.line_items.map((item, index) => (
                  <TableRow key={item.field_key}>
                    <TableCell className="tabular text-2xs text-muted-foreground">{index + 1}</TableCell>
                    <TableCell className="font-mono text-2xs">{item.raw}</TableCell>
                    <TableCell className="text-2xs">{item.value}</TableCell>
                    <TableCell className="text-right text-2xs text-muted-foreground">
                      p{item.page ?? "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableWrap>
        </section>
      )}

      <section className="panel">
        <header className="panel-header">
          <h3 className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
            Recognition detail
          </h3>
        </header>
        <div className="space-y-3 p-4">
          {document.ocr.map((page) => (
            <div key={page.page_number} className="space-y-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline">Page {page.page_number}</Badge>
                <Badge variant="muted">
                  {page.provider} {page.provider_version}
                </Badge>
                <span className="text-2xs text-muted-foreground">
                  {page.word_count} words · mean confidence {percent(page.mean_confidence ?? 0)} ·{" "}
                  {page.duration_ms} ms
                </span>
              </div>
              {page.error && <p className="text-2xs text-risk-review">{page.error}</p>}
              <details className="rounded border bg-muted/30">
                <summary className="cursor-pointer px-2.5 py-1.5 text-2xs text-muted-foreground">
                  Raw recognised text
                </summary>
                <pre className="max-h-56 overflow-auto whitespace-pre-wrap px-2.5 pb-2.5 font-mono text-2xs leading-relaxed scrollbar-thin">
                  {page.raw_text || "(no text recognised)"}
                </pre>
              </details>
            </div>
          ))}
          {document.ocr.length === 0 && (
            <p className="text-2xs text-muted-foreground">No OCR result is stored for this document.</p>
          )}
        </div>
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ forensics */
export function ForensicsPanel({
  document,
  documentId,
  permissions,
  activeId,
  onSelect,
}: {
  document: DocumentDetail;
  documentId: string;
  permissions: string[];
  activeId: string | null;
  onSelect: (id: string | null) => void;
}) {
  const findings = document.findings.filter((finding) => finding.kind === "forensic");
  const anomalous = document.metadata_entries.filter((entry) => entry.is_anomalous);
  const groups = new Map<string, typeof document.metadata_entries>();
  for (const entry of document.metadata_entries) {
    groups.set(entry.group, [...(groups.get(entry.group) ?? []), entry]);
  }
  const stage = document.latest_run?.stages?.find((item) => item.key === "forensics");
  const rasterNote = stage?.detail?.raster;

  return (
    <div className="space-y-3">
      <FindingList
        findings={findings}
        documentId={documentId}
        permissions={permissions}
        activeId={activeId}
        onSelect={onSelect}
        emptyIcon={<Fingerprint className="size-7" />}
        emptyTitle="No forensic signals were raised"
        emptyDescription="Structure, metadata, typography and any embedded rasters were examined without
          producing a signal. That is not a certificate of authenticity — see the coverage note on
          the Overview tab for what did and did not run."
      />

      {rasterNote?.status === "not_applicable" && (
        <div className="rounded-md border border-dashed bg-muted/40 p-3">
          <p className="flex items-center gap-1.5 text-2xs font-semibold">
            <CircleSlash className="size-3.5" /> Pixel-history metrics not applicable
          </p>
          <p className="mt-1 text-2xs leading-relaxed text-muted-foreground">{rasterNote.reason}</p>
        </div>
      )}

      <section className="panel">
        <header className="panel-header">
          <h3 className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
            Document metadata
          </h3>
          <div className="flex items-center gap-1.5">
            <Badge variant="muted">{document.metadata_entries.length} fields</Badge>
            {anomalous.length > 0 && <Badge variant="review">{anomalous.length} flagged</Badge>}
          </div>
        </header>
        {Array.from(groups.entries()).map(([group, entries]) => (
          <div key={group}>
            <p className="border-b bg-muted/40 px-4 py-1.5 text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
              {humanise(group)}
            </p>
            <TableWrap>
              <Table>
                <TableBody>
                  {entries.map((entry, index) => (
                    <TableRow key={`${entry.key}-${index}`} className={entry.is_anomalous ? "bg-risk-review/8" : undefined}>
                      <TableCell className="w-[38%] text-2xs text-muted-foreground">{entry.key}</TableCell>
                      <TableCell className="break-all font-mono text-2xs">{entry.value ?? "—"}</TableCell>
                      <TableCell className="w-[26%] text-2xs">
                        {entry.is_anomalous && (
                          <span className="flex items-start gap-1 text-risk-review">
                            <AlertTriangle className="mt-0.5 size-3 shrink-0" />
                            {entry.note}
                          </span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableWrap>
          </div>
        ))}
        {document.metadata_entries.length === 0 && (
          <p className="px-4 py-6 text-2xs text-muted-foreground">
            No metadata was recoverable from this document.
          </p>
        )}
      </section>

      {stage?.detail && (
        <section className="panel">
          <header className="panel-header">
            <h3 className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
              Raw measurements
            </h3>
            <span className="text-2xs text-muted-foreground">
              Everything the forensic stage computed, including metrics that did not fire
            </span>
          </header>
          <pre className="max-h-72 overflow-auto p-3 font-mono text-2xs leading-relaxed text-muted-foreground scrollbar-thin">
            {JSON.stringify(stage.detail, null, 2)}
          </pre>
        </section>
      )}
    </div>
  );
}

/* ----------------------------------------------------------------------- AIGC */
export function AigcPanel({
  document,
  documentId,
  permissions,
  activeId,
  onSelect,
}: {
  document: DocumentDetail;
  documentId: string;
  permissions: string[];
  activeId: string | null;
  onSelect: (id: string | null) => void;
}) {
  const findings = document.findings.filter((finding) => finding.kind === "aigc");
  const stage = document.latest_run?.stages?.find((item) => item.key === "aigc");
  const pages: any[] = stage?.detail?.pages ?? [];
  const provider = findings[0];
  const isDemo = pages[0]?.provider?.is_demo ?? provider?.is_demo_provider ?? true;
  const disclaimer = stage?.detail?.disclaimer ?? pages[0]?.disclaimer;

  if (stage?.status === "unavailable") {
    return (
      <div className="space-y-3">
        <DemoNotice title="Synthetic-media analysis unavailable">
          {stage.message ||
            "The configured detector could not be reached. The document is preserved and the stage can be re-run; the absence of a result is not evidence either way."}
        </DemoNotice>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {isDemo && (
        <DemoNotice title="Heuristic demo detector — not a trained classifier">
          {disclaimer ??
            "This result comes from the bundled deterministic heuristic provider. It is explainable and reproducible but is not calibrated against a labelled corpus. Configure a production detector under Integrations before relying on this signal."}
        </DemoNotice>
      )}

      {pages.map((page) => (
        <section key={page.page} className="panel">
          <header className="panel-header">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-xs font-semibold">Page {page.page}</h3>
              <Badge variant={page.band === "no_significant_indicators" ? "low" : "review"}>
                <Sparkles className="size-3" />
                {page.band_label}
              </Badge>
              {page.provider?.is_demo && <DemoBadge />}
            </div>
            <span className="tabular text-2xs text-muted-foreground">
              likelihood {page.likelihood?.toFixed?.(3) ?? page.likelihood}
            </span>
          </header>

          <div className="space-y-3 p-4">
            <p className="text-2xs leading-relaxed text-muted-foreground">{page.summary}</p>

            <KeyValue
              columns={3}
              items={[
                { label: "Provider", value: page.provider?.label },
                {
                  label: "Model / version",
                  value: `${page.provider?.model_name} @ ${page.provider?.model_version}`,
                  mono: true,
                },
                {
                  label: "Source",
                  value: page.evidence?.source_is_lossless_render
                    ? "Lossless page render (damped)"
                    : (page.evidence?.source_mime ?? "original upload"),
                },
              ]}
            />

            <div className="space-y-1.5">
              <p className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
                Indicator contributions
              </p>
              <TableWrap>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Indicator</TableHead>
                      <TableHead>Measured</TableHead>
                      <TableHead>Normalised</TableHead>
                      <TableHead>Weight</TableHead>
                      <TableHead>Contribution</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(page.indicators ?? []).map((indicator: any) => (
                      <TableRow key={indicator.key}>
                        <TableCell className="text-2xs">
                          {indicator.label}
                          <span className="block text-2xs text-muted-foreground">{indicator.note}</span>
                        </TableCell>
                        <TableCell className="tabular text-2xs">{indicator.measured}</TableCell>
                        <TableCell className="tabular text-2xs">{indicator.normalized}</TableCell>
                        <TableCell className="tabular text-2xs text-muted-foreground">
                          {indicator.weight}
                        </TableCell>
                        <TableCell className="tabular text-2xs font-medium">
                          {indicator.contribution}
                        </TableCell>
                      </TableRow>
                    ))}
                    {!(page.indicators ?? []).length && (
                      <TableEmpty colSpan={5}>No indicators were computed for this page.</TableEmpty>
                    )}
                  </TableBody>
                </Table>
              </TableWrap>
            </div>

            <UncertaintyNote>{page.uncertainty_note}</UncertaintyNote>
          </div>
        </section>
      ))}

      <FindingList
        findings={findings}
        documentId={documentId}
        permissions={permissions}
        activeId={activeId}
        onSelect={onSelect}
        emptyIcon={<ScanEye className="size-7" />}
        emptyTitle="No synthetic-media finding recorded"
        emptyDescription="The analysis stage did not produce a finding for this document."
      />
    </div>
  );
}

/* ------------------------------------------------------------------ tampering */
export function TamperingPanel({
  document,
  documentId,
  permissions,
  activeId,
  onSelect,
}: {
  document: DocumentDetail;
  documentId: string;
  permissions: string[];
  activeId: string | null;
  onSelect: (id: string | null) => void;
}) {
  const findings = document.findings.filter((finding) => finding.kind === "tampering");
  const stage = document.latest_run?.stages?.find((item) => item.key === "tampering");
  const candidates = stage?.detail?.candidate_regions ?? 0;

  return (
    <div className="space-y-3">
      <div className="rounded-md border bg-muted/40 p-3">
        <p className="text-2xs leading-relaxed text-muted-foreground">
          A tampering signal is raised only where <strong>independent detectors agree on the same
          area</strong> of the page — error-level response, noise floor, compression history,
          duplicated regions, typography, and, for digital PDFs, the exact font each character was
          drawn with. Confidence is combined across those detectors, each damped by how much it can
          be trusted alone. The region is then named by intersecting it with the extracted fields,
          which is how a signal becomes “the total amount” rather than “an area of the page”.
        </p>
        <p className="mt-2 text-2xs text-muted-foreground">
          {candidates} candidate region{candidates === 1 ? "" : "s"} were considered on this
          document; {findings.length} reached the multi-detector threshold.
        </p>
      </div>

      <FindingList
        findings={findings}
        documentId={documentId}
        permissions={permissions}
        activeId={activeId}
        onSelect={onSelect}
        emptyIcon={<Blocks className="size-7" />}
        emptyTitle="No region reached the tampering threshold"
        emptyDescription="Individual forensic measurements may still appear under Forensics; none of them
          coincided with another detector on the same area of the page."
      />

      {findings.length > 0 && (
        <UncertaintyNote>
          Overlapping anomalies in one place are the pattern a localised edit leaves, but each
          contributing measurement has benign explanations — a pasted logo, a stamp, a photograph, a
          re-scanned page. Confirm the value with the issuer before treating this as established.
        </UncertaintyNote>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- consistency */
export function ConsistencyPanel({
  document,
  documentId,
  permissions,
  activeId,
  onSelect,
}: {
  document: DocumentDetail;
  documentId: string;
  permissions: string[];
  activeId: string | null;
  onSelect: (id: string | null) => void;
}) {
  const findings = document.findings.filter((finding) => finding.kind === "consistency");
  const stage = document.latest_run?.stages?.find((item) => item.key === "consistency");
  const checks: any[] = stage?.detail?.checks ?? [];
  const [showAll, setShowAll] = useState(false);

  const visible = showAll
    ? checks
    : checks.filter((check) => check.status === "failed" || check.status === "passed");

  const counts = {
    passed: checks.filter((check) => check.status === "passed").length,
    failed: checks.filter((check) => check.status === "failed").length,
    not_applicable: checks.filter((check) => check.status === "not_applicable").length,
    disabled: checks.filter((check) => check.status === "disabled").length,
    error: checks.filter((check) => check.status === "error").length,
  };

  const ICON: Record<string, React.ReactNode> = {
    passed: <CheckCircle2 className="size-3.5 text-risk-low" />,
    failed: <XCircle className="size-3.5 text-risk-high" />,
    not_applicable: <MinusCircle className="size-3.5 text-muted-foreground" />,
    disabled: <CircleSlash className="size-3.5 text-muted-foreground" />,
    error: <AlertTriangle className="size-3.5 text-risk-review" />,
  };

  return (
    <div className="space-y-3">
      <FindingList
        findings={findings}
        documentId={documentId}
        permissions={permissions}
        activeId={activeId}
        onSelect={onSelect}
        emptyIcon={<CheckCircle2 className="size-7" />}
        emptyTitle="Every applicable consistency rule passed"
        emptyDescription="Totals reconcile, dates are ordered plausibly, identifiers are well formed and
          required fields are present."
      />

      <section className="panel">
        <header className="panel-header">
          <div className="min-w-0">
            <h3 className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
              Rule evaluation
            </h3>
            <p className="mt-0.5 text-2xs text-muted-foreground">
              {counts.passed} passed · {counts.failed} failed · {counts.not_applicable} not
              applicable
              {counts.disabled ? ` · ${counts.disabled} disabled` : ""}
              {counts.error ? ` · ${counts.error} errored` : ""} · rules{" "}
              {stage?.detail?.rules_version}
            </p>
          </div>
          <Button variant="ghost" size="xs" onClick={() => setShowAll((current) => !current)}>
            {showAll ? "Hide inapplicable" : "Show all rules"}
          </Button>
        </header>
        <TableWrap className="max-h-[420px]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Status</TableHead>
                <TableHead>Rule</TableHead>
                <TableHead>Detail</TableHead>
                <TableHead>Severity</TableHead>
                <TableHead>Weight</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {visible.map((check) => (
                <TableRow
                  key={check.code}
                  className={check.status === "failed" ? "bg-risk-high/5" : undefined}
                >
                  <TableCell>
                    <span className="flex items-center gap-1.5 text-2xs">
                      {ICON[check.status]}
                      {humanise(check.status)}
                    </span>
                  </TableCell>
                  <TableCell className="text-2xs">
                    {check.name}
                    <span className="block font-mono text-2xs text-muted-foreground">
                      {check.code}
                    </span>
                  </TableCell>
                  <TableCell className="text-2xs text-muted-foreground">{check.detail}</TableCell>
                  <TableCell className="text-2xs">{humanise(check.severity)}</TableCell>
                  <TableCell className="tabular text-2xs text-muted-foreground">
                    {check.weight}
                  </TableCell>
                </TableRow>
              ))}
              {!visible.length && (
                <TableEmpty colSpan={5}>
                  The consistency stage did not record any rule evaluations.
                </TableEmpty>
              )}
            </TableBody>
          </Table>
        </TableWrap>
      </section>
    </div>
  );
}

/* -------------------------------------------------------------- cross-document */
export function CrossDocumentPanel({
  document,
  documentId,
  permissions,
  activeId,
  onSelect,
  comparisons,
}: {
  document: DocumentDetail;
  documentId: string;
  permissions: string[];
  activeId: string | null;
  onSelect: (id: string | null) => void;
  comparisons?: Array<any>;
}) {
  const findings = document.findings.filter((finding) => finding.kind === "cross_document");
  const stage = document.latest_run?.stages?.find((item) => item.key === "cross_document");
  const rows: any[] = comparisons ?? stage?.detail?.comparisons ?? [];
  const [showSkipped, setShowSkipped] = useState(false);
  const visible = showSkipped ? rows : rows.filter((row) => !row.skipped);

  if (!document.claim_id) {
    return (
      <EmptyState
        icon={<Database className="size-7" />}
        title="Not attached to a claim"
        description="Cross-document comparison needs at least two documents in the same claim. Attach this
          document to a claim to compare patient, policy, provider, date and amount fields across the
          bundle."
      />
    );
  }

  return (
    <div className="space-y-3">
      <FindingList
        findings={findings}
        documentId={documentId}
        permissions={permissions}
        activeId={activeId}
        onSelect={onSelect}
        emptyIcon={<CheckCircle2 className="size-7" />}
        emptyTitle="The claim bundle agrees with itself"
        emptyDescription="Comparable fields matched across the documents in this claim and against the claim
          record."
      />

      <section className="panel">
        <header className="panel-header">
          <div>
            <h3 className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
              Field comparison
            </h3>
            <p className="mt-0.5 text-2xs text-muted-foreground">
              {stage?.detail?.agreements ?? 0} agreements · {stage?.detail?.mismatches ?? 0} mismatches
              across {stage?.detail?.documents_compared ?? 0} documents
            </p>
          </div>
          <Button variant="ghost" size="xs" onClick={() => setShowSkipped((current) => !current)}>
            {showSkipped ? "Hide not-compared" : "Show not-compared"}
          </Button>
        </header>
        <TableWrap className="max-h-[420px]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Field</TableHead>
                <TableHead>Document A</TableHead>
                <TableHead>Document B</TableHead>
                <TableHead>Result</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {visible.map((row, index) => (
                <TableRow key={index} className={!row.agrees ? "bg-risk-high/5" : undefined}>
                  <TableCell className="text-2xs">
                    {row.label}
                    <span className="block text-2xs text-muted-foreground">{row.mode} compare</span>
                  </TableCell>
                  <TableCell className="max-w-[200px] text-2xs">
                    <span className="block font-mono text-muted-foreground">{row.document_a}</span>
                    <span className="block break-words">{row.value_a || "—"}</span>
                  </TableCell>
                  <TableCell className="max-w-[200px] text-2xs">
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
                    <span className="mt-0.5 block text-2xs text-muted-foreground">{row.detail}</span>
                  </TableCell>
                </TableRow>
              ))}
              {!visible.length && (
                <TableEmpty colSpan={4}>
                  No comparable fields were found across this claim's documents.
                </TableEmpty>
              )}
            </TableBody>
          </Table>
        </TableWrap>
      </section>
    </div>
  );
}

/* ------------------------------------------------------------- verification */
export function VerificationPanel({
  document,
  canRun,
}: {
  document: DocumentDetail;
  canRun: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const requests = document.verification;
  const stage = document.latest_run?.stages?.find((item) => item.key === "verification");
  const skipped: any[] = stage?.detail?.skipped ?? [];

  async function run() {
    setBusy(true);
    try {
      const result = await apiPost<{ results: any[] }>(
        `/verification/documents/${document.id}/run`,
        {},
      );
      const executed = result.results.filter((item) => !item.skipped);
      toast.success(`${executed.length} check(s) completed`, {
        description: "Use “Recompute risk” on the Overview tab to fold the outcome into the score.",
      });
      window.location.reload();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Verification could not be run");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="max-w-2xl text-2xs leading-relaxed text-muted-foreground">
          Verification is the only signal here that can <em>corroborate</em> a document rather than
          flag an anomaly, which is why the source of every answer is stated explicitly.
        </p>
        {canRun && (
          <Button size="sm" variant="outline" onClick={run} disabled={busy}>
            <Play className="size-3.5" /> {busy ? "Running…" : "Run checks now"}
          </Button>
        )}
      </div>

      {requests.some((request) => request.result?.is_demo_data) && (
        <DemoNotice title="Answers came from the bundled demo registry">
          No external insurer, hospital, government or banking system was contacted. These results
          demonstrate the integration and must not be treated as real-world confirmations. Configure
          a production endpoint under Integrations to make these checks authoritative.
        </DemoNotice>
      )}

      {requests.map((request) => (
        <section key={request.id} className="panel">
          <header className="panel-header">
            <div className="min-w-0">
              <h3 className="flex flex-wrap items-center gap-2 text-xs font-semibold">
                <Landmark className="size-3.5 text-muted-foreground" />
                {humanise(request.request_type)}
                {request.result && <OutcomeChip outcome={request.result.outcome} />}
                {request.is_demo_provider && <DemoBadge />}
              </h3>
              <p className="mt-0.5 truncate text-2xs text-muted-foreground">
                {request.provider_label} · {humanise(request.trigger)} ·{" "}
                {formatDate(request.requested_at, true)}
                {request.result ? ` · ${request.result.latency_ms} ms` : ""}
              </p>
            </div>
            {request.result?.reference_id && (
              <Badge variant="outline" className="font-mono">
                {request.result.reference_id}
              </Badge>
            )}
          </header>

          <div className="space-y-3 p-4">
            {request.result?.summary && (
              <p className="text-2xs leading-relaxed">{request.result.summary}</p>
            )}
            {request.result?.error && (
              <p className="rounded border border-risk-review/30 bg-risk-review/8 px-2 py-1.5 text-2xs">
                {request.result.error}
              </p>
            )}

            <TableWrap>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Check</TableHead>
                    <TableHead>Source record</TableHead>
                    <TableHead>This document</TableHead>
                    <TableHead>Result</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(request.result?.checks ?? []).map((check) => (
                    <TableRow
                      key={check.key}
                      className={check.passed === false ? "bg-risk-high/5" : undefined}
                    >
                      <TableCell className="text-2xs">{check.label}</TableCell>
                      <TableCell className="font-mono text-2xs">{check.expected ?? "—"}</TableCell>
                      <TableCell className="font-mono text-2xs">{check.actual ?? "—"}</TableCell>
                      <TableCell className="text-2xs">
                        {check.passed === true && <Badge variant="low">Agrees</Badge>}
                        {check.passed === false && <Badge variant="high">Disagrees</Badge>}
                        {check.passed === null && <Badge variant="muted">Not evaluated</Badge>}
                        {check.note && (
                          <span className="mt-0.5 block text-2xs text-muted-foreground">
                            {check.note}
                          </span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                  {!(request.result?.checks ?? []).length && (
                    <TableEmpty colSpan={4}>No checks were returned.</TableEmpty>
                  )}
                </TableBody>
              </Table>
            </TableWrap>

            <details className="rounded border bg-muted/30">
              <summary className="cursor-pointer px-2.5 py-1.5 text-2xs text-muted-foreground">
                Request payload sent to the provider
              </summary>
              <pre className="overflow-auto px-2.5 pb-2.5 font-mono text-2xs scrollbar-thin">
                {JSON.stringify(request.request_payload, null, 2)}
              </pre>
            </details>

            {request.result?.data_source_disclaimer && (
              <p className="text-2xs italic leading-relaxed text-muted-foreground">
                {request.result.data_source_disclaimer}
              </p>
            )}
          </div>
        </section>
      ))}

      {skipped.length > 0 && (
        <section className="panel">
          <header className="panel-header">
            <h3 className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
              Checks not attempted
            </h3>
          </header>
          <ul className="divide-y">
            {skipped.map((item, index) => (
              <li key={index} className="flex items-center justify-between gap-3 px-4 py-2">
                <span className="text-2xs">{humanise(item.request_type)}</span>
                <span className="text-2xs text-muted-foreground">{item.reason}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {!requests.length && (
        <EmptyState
          icon={<Landmark className="size-7" />}
          title="No verification has been requested"
          description="Either no route applies to this document type, or the references needed for a lookup
            were not extracted."
        />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------- audit */
export function AuditPanel({
  document,
  auditEntries,
}: {
  document: DocumentDetail;
  auditEntries: Array<any>;
}) {
  return (
    <div className="space-y-3">
      <section className="panel">
        <header className="panel-header">
          <h3 className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
            Human review actions
          </h3>
          <Badge variant="muted">{document.review_actions.length}</Badge>
        </header>
        {document.review_actions.length ? (
          <ul className="divide-y">
            {document.review_actions.map((action) => (
              <li key={action.id} className="space-y-1 px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline">{humanise(action.action)}</Badge>
                  <span className="text-2xs font-medium">{action.actor?.full_name ?? "system"}</span>
                  <span className="text-2xs text-muted-foreground">
                    {humanise(action.actor_role ?? "")} · {formatDate(action.created_at, true)}
                  </span>
                  {action.previous_status && action.new_status && (
                    <span className="font-mono text-2xs text-muted-foreground">
                      {action.previous_status} → {action.new_status}
                    </span>
                  )}
                </div>
                {action.reason && (
                  <p className="text-2xs leading-relaxed text-muted-foreground">“{action.reason}”</p>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="px-4 py-6 text-2xs text-muted-foreground">
            No human review action has been recorded. Machine findings on this document remain
            unadjudicated.
          </p>
        )}
      </section>

      <section className="panel">
        <header className="panel-header">
          <div>
            <h3 className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
              Audit trail
            </h3>
            <p className="mt-0.5 text-2xs text-muted-foreground">
              Append-only, hash-chained. Each entry commits to the one before it.
            </p>
          </div>
          <Button variant="ghost" size="xs" asChild>
            <Link href={`/audit-logs?resource_id=${document.id}`}>Open in audit log</Link>
          </Button>
        </header>
        <TableWrap className="max-h-[420px]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Seq</TableHead>
                <TableHead>When</TableHead>
                <TableHead>Actor</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Summary</TableHead>
                <TableHead>Entry hash</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {auditEntries.map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell className="tabular text-2xs text-muted-foreground">{entry.seq}</TableCell>
                  <TableCell className="whitespace-nowrap text-2xs">
                    {formatDate(entry.created_at, true)}
                  </TableCell>
                  <TableCell className="text-2xs">{entry.actor_email ?? "system"}</TableCell>
                  <TableCell className="font-mono text-2xs">{entry.action}</TableCell>
                  <TableCell className="max-w-[280px] text-2xs text-muted-foreground">
                    <span className="block truncate" title={entry.summary ?? ""}>
                      {entry.summary}
                    </span>
                  </TableCell>
                  <TableCell className="font-mono text-2xs text-muted-foreground">
                    {entry.entry_hash?.slice(0, 10)}…
                  </TableCell>
                </TableRow>
              ))}
              {!auditEntries.length && (
                <TableEmpty colSpan={6}>No audit entries for this document.</TableEmpty>
              )}
            </TableBody>
          </Table>
        </TableWrap>
      </section>
    </div>
  );
}
