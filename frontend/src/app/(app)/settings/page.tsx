import type { Metadata } from "next";
import { Database, Lock, ScanEye, Scale } from "lucide-react";

import { ThresholdEditor } from "@/components/shared/rule-controls";
import { PageHeader } from "@/components/shared/page-header";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow, TableWrap,
} from "@/components/ui/table";
import { api, apiSafe } from "@/lib/api";
import { humanise } from "@/lib/format";
import { can, getSessionUser } from "@/lib/session";

export const metadata: Metadata = { title: "Settings" };

interface Setting {
  key: string;
  label: string;
  value: any;
  description: string;
  updated_at: string;
}

const ICONS: Record<string, typeof Scale> = {
  risk_thresholds: Scale,
  retention: Database,
  review_policy: ScanEye,
  privacy_policy: Lock,
  analysis_policy: ScanEye,
};

export default async function SettingsPage() {
  const user = await getSessionUser();
  const [settings, capabilities] = await Promise.all([
    api<Setting[]>("/settings"),
    apiSafe<Record<string, any>>("/system/capabilities"),
  ]);

  const editable = can(user, "settings:write");
  const thresholds = settings.find((setting) => setting.key === "risk_thresholds");

  return (
    <>
      <PageHeader
        title="System settings"
        description="Operating policy for the platform: where the triage bands sit, how long evidence and
          derived artifacts are kept, and what the platform requires of a human before a claim can
          be cleared."
        actions={
          <Badge variant={editable ? "default" : "muted"}>
            {editable ? "You can edit" : "Read-only for your role"}
          </Badge>
        }
      />

      {thresholds && (
        <section className="panel">
          <header className="panel-header">
            <div>
              <h2 className="text-xs font-semibold">Risk band thresholds</h2>
              <p className="mt-0.5 text-2xs text-muted-foreground">{thresholds.description}</p>
            </div>
          </header>
          <div className="space-y-3 p-4">
            {editable ? (
              <ThresholdEditor
                review={Number(thresholds.value.review_recommended)}
                high={Number(thresholds.value.high_concern)}
              />
            ) : (
              <p className="text-2xs">
                Review Recommended at{" "}
                <span className="tabular font-semibold">
                  {thresholds.value.review_recommended}
                </span>
                , High Concern at{" "}
                <span className="tabular font-semibold">{thresholds.value.high_concern}</span>.
              </p>
            )}
            <p className="text-2xs leading-relaxed text-muted-foreground">
              Changing a threshold does not rewrite existing assessments — a document keeps the band
              it was given until it is reassessed, so a historical decision always reflects the
              policy in force at the time it was made.
            </p>
          </div>
        </section>
      )}

      <div className="grid gap-3 lg:grid-cols-2">
        {settings
          .filter((setting) => setting.key !== "risk_thresholds")
          .map((setting) => {
            const Icon = ICONS[setting.key] ?? Database;
            return (
              <section key={setting.key} className="panel">
                <header className="panel-header">
                  <div className="min-w-0">
                    <h2 className="flex items-center gap-2 text-xs font-semibold">
                      <Icon className="size-3.5 text-muted-foreground" />
                      {setting.label}
                    </h2>
                    <p className="mt-0.5 text-2xs leading-relaxed text-muted-foreground">
                      {setting.description}
                    </p>
                  </div>
                </header>
                <TableWrap>
                  <Table>
                    <TableBody>
                      {Object.entries(setting.value ?? {}).map(([key, value]) => (
                        <TableRow key={key}>
                          <TableCell className="w-1/2 text-2xs text-muted-foreground">
                            {humanise(key)}
                          </TableCell>
                          <TableCell className="tabular font-mono text-2xs">
                            {typeof value === "boolean" ? (
                              <Badge variant={value ? "low" : "muted"}>{String(value)}</Badge>
                            ) : (
                              String(value)
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableWrap>
              </section>
            );
          })}
      </div>

      {capabilities && (
        <section className="panel">
          <header className="panel-header">
            <h2 className="text-xs font-semibold">Runtime configuration</h2>
            <span className="text-2xs text-muted-foreground">
              Read from the environment at start-up
            </span>
          </header>
          <div className="grid gap-4 p-4 md:grid-cols-3">
            <div className="space-y-1.5">
              <p className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
                Upload limits
              </p>
              <ul className="space-y-0.5 text-2xs text-muted-foreground">
                <li>Maximum size: {capabilities.upload.max_size_mb} MB</li>
                <li>Maximum pages: {capabilities.upload.max_pages}</li>
                <li>Types: {capabilities.upload.allowed_extensions.join(", ")}</li>
              </ul>
            </div>
            <div className="space-y-1.5">
              <p className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
                Active providers
              </p>
              <ul className="space-y-0.5 font-mono text-2xs text-muted-foreground">
                <li>ocr: {capabilities.providers.ocr.active}</li>
                <li>aigc: {capabilities.providers.aigc.active}</li>
                <li>verification: {capabilities.providers.verification.active}</li>
                <li>storage: {capabilities.providers.storage.active}</li>
                <li>malware: {capabilities.providers.malware.active}</li>
                <li>queue: {capabilities.queue.mode}</li>
              </ul>
            </div>
            <div className="space-y-1.5">
              <p className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
                Versions
              </p>
              <ul className="space-y-0.5 font-mono text-2xs text-muted-foreground">
                <li>pipeline: {capabilities.versions.pipeline}</li>
                <li>rules: {capabilities.versions.rules}</li>
                <li>risk weights: {capabilities.versions.risk_weights}</li>
              </ul>
            </div>
          </div>
        </section>
      )}
    </>
  );
}
