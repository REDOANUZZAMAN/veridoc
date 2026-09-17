import type { Metadata } from "next";
import { SlidersHorizontal } from "lucide-react";

import {
  RuleSeveritySelect, RuleToggle, RuleWeightInput,
} from "@/components/shared/rule-controls";
import { PageHeader } from "@/components/shared/page-header";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableEmpty, TableHead, TableHeader, TableRow, TableWrap,
} from "@/components/ui/table";
import { api, apiSafe } from "@/lib/api";
import { humanise } from "@/lib/format";
import { can, getSessionUser } from "@/lib/session";
import type { DetectionRule } from "@/lib/types";

export const metadata: Metadata = { title: "Detection rules" };

interface DocumentTypeCatalogue {
  document_types: Array<{
    document_type: string;
    label: string;
    field_count: number;
    required_fields: string[];
    line_items: boolean;
    verification_routes: string[];
    classifier_signature: { strong_terms: string[] } | null;
  }>;
  note: string;
}

interface Catalogue {
  consistency_rules: Array<{ code: string; name: string; description: string; params: Record<string, unknown> }>;
  risk_weight_defaults: Array<{ category: string; label: string; default_weight: number; cap: number }>;
  category_caps: Record<string, number>;
  default_thresholds: { review_recommended: number; high_concern: number };
  note: string;
}

export default async function RulesPage() {
  const user = await getSessionUser();
  const [rules, catalogue, documentTypes] = await Promise.all([
    api<DetectionRule[]>("/rules"),
    apiSafe<Catalogue>("/rules/catalogue"),
    apiSafe<DocumentTypeCatalogue>("/document-types"),
  ]);

  const editable = can(user, "rule:write");
  const byCategory = new Map<string, DetectionRule[]>();
  for (const rule of rules) {
    byCategory.set(rule.category, [...(byCategory.get(rule.category) ?? []), rule]);
  }

  return (
    <>
      <PageHeader
        title="Detection rules & risk weights"
        description="Both the consistency engine and the risk engine read severity and weight from this
          table at run time, so thresholds are configuration rather than code. Changes apply to the
          next analysis run; existing assessments are not rewritten."
        actions={
          <Badge variant={editable ? "default" : "muted"}>
            {editable ? "You can edit" : "Read-only for your role"}
          </Badge>
        }
      />

      <div className="grid gap-3 lg:grid-cols-3">
        <section className="panel lg:col-span-2">
          <header className="panel-header">
            <h2 className="text-xs font-semibold">Category ceilings</h2>
            <span className="text-2xs text-muted-foreground">
              Why one weak category cannot outvote a decisive one
            </span>
          </header>
          <TableWrap>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Category</TableHead>
                  <TableHead>Default weight per finding</TableHead>
                  <TableHead>Category ceiling</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(catalogue?.risk_weight_defaults ?? []).map((row) => (
                  <TableRow key={row.category}>
                    <TableCell className="text-xs">{row.label}</TableCell>
                    <TableCell className="tabular text-2xs">{row.default_weight}</TableCell>
                    <TableCell className="tabular text-2xs">{row.cap}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableWrap>
          <footer className="border-t px-4 py-2.5">
            <p className="text-2xs leading-relaxed text-muted-foreground">{catalogue?.note}</p>
          </footer>
        </section>

        <section className="panel">
          <header className="panel-header">
            <h2 className="text-xs font-semibold">Band thresholds</h2>
          </header>
          <div className="space-y-2 p-4 text-2xs">
            <p className="text-muted-foreground">
              A document moves from Low Concern to Review Recommended at{" "}
              <span className="tabular font-semibold text-foreground">
                {catalogue?.default_thresholds.review_recommended}
              </span>{" "}
              and to High Concern at{" "}
              <span className="tabular font-semibold text-foreground">
                {catalogue?.default_thresholds.high_concern}
              </span>
              .
            </p>
            <p className="text-muted-foreground">
              Thresholds are tuned under <span className="font-medium text-foreground">Settings</span>.
              Raising High Concern reduces the number of investigations opened automatically.
            </p>
          </div>
        </section>
      </div>

      {documentTypes && (
        <section className="panel">
          <header className="panel-header">
            <div className="min-w-0">
              <h2 className="text-xs font-semibold">Document types & extraction schemas</h2>
              <p className="mt-0.5 max-w-3xl text-2xs leading-relaxed text-muted-foreground">
                {documentTypes.note}
              </p>
            </div>
            <Badge variant="muted">{documentTypes.document_types.length} types</Badge>
          </header>
          <TableWrap>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Document type</TableHead>
                  <TableHead>Declared fields</TableHead>
                  <TableHead>Required for this type</TableHead>
                  <TableHead>Line items</TableHead>
                  <TableHead>Verification routes</TableHead>
                  <TableHead>Strongest classifier terms</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {documentTypes.document_types.map((type) => (
                  <TableRow key={type.document_type}>
                    <TableCell className="text-2xs">
                      <span className="block font-medium">{type.label}</span>
                      <span className="block font-mono text-muted-foreground">
                        {type.document_type}
                      </span>
                    </TableCell>
                    <TableCell className="tabular text-2xs">{type.field_count}</TableCell>
                    <TableCell className="max-w-[260px] text-2xs text-muted-foreground">
                      {type.required_fields.length
                        ? type.required_fields.map((field) => humanise(field)).join(", ")
                        : "none"}
                    </TableCell>
                    <TableCell className="text-2xs">
                      {type.line_items ? <Badge variant="low">parsed</Badge> : "—"}
                    </TableCell>
                    <TableCell className="max-w-[220px] text-2xs text-muted-foreground">
                      {type.verification_routes.length
                        ? type.verification_routes.map((route) => humanise(route)).join(", ")
                        : "none configured"}
                    </TableCell>
                    <TableCell className="max-w-[300px] text-2xs text-muted-foreground">
                      {(type.classifier_signature?.strong_terms ?? []).slice(0, 5).join(" · ") || "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableWrap>
        </section>
      )}

      {Array.from(byCategory.entries())
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([category, categoryRules]) => (
          <section key={category} className="panel">
            <header className="panel-header">
              <h2 className="flex items-center gap-2 text-xs font-semibold">
                <SlidersHorizontal className="size-3.5 text-muted-foreground" />
                {humanise(category)}
              </h2>
              <Badge variant="muted">{categoryRules.length}</Badge>
            </header>
            <TableWrap>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[70px]">Enabled</TableHead>
                    <TableHead>Rule</TableHead>
                    <TableHead>What it checks</TableHead>
                    <TableHead className="w-[120px]">Severity</TableHead>
                    <TableHead className="w-[90px]">Weight</TableHead>
                    <TableHead className="w-[110px]">Applies to</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {categoryRules.map((rule) => (
                    <TableRow key={rule.code} className={rule.enabled ? undefined : "opacity-60"}>
                      <TableCell>
                        {editable ? (
                          <RuleToggle code={rule.code} enabled={rule.enabled} />
                        ) : (
                          <Badge variant={rule.enabled ? "low" : "muted"}>
                            {rule.enabled ? "on" : "off"}
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="max-w-[230px] text-2xs">
                        <span className="block font-medium">{rule.name}</span>
                        <span className="block font-mono text-muted-foreground">{rule.code}</span>
                      </TableCell>
                      <TableCell className="max-w-[440px] text-2xs text-muted-foreground">
                        {rule.description}
                        {Object.keys(rule.params ?? {}).length > 0 && (
                          <span className="mt-0.5 block font-mono text-2xs">
                            {JSON.stringify(rule.params)}
                          </span>
                        )}
                      </TableCell>
                      <TableCell>
                        {editable ? (
                          <RuleSeveritySelect code={rule.code} severity={rule.default_severity} />
                        ) : (
                          <span className="text-2xs">{rule.default_severity}</span>
                        )}
                      </TableCell>
                      <TableCell>
                        {editable ? (
                          <RuleWeightInput code={rule.code} weight={rule.weight} />
                        ) : (
                          <span className="tabular text-2xs">{rule.weight}</span>
                        )}
                      </TableCell>
                      <TableCell className="text-2xs text-muted-foreground">
                        {rule.applies_to?.length
                          ? rule.applies_to.map((type) => humanise(type)).join(", ")
                          : "All document types"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableWrap>
          </section>
        ))}
    </>
  );
}
