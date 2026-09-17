import type { Metadata } from "next";
import Link from "next/link";
import { CheckCircle2, ShieldAlert } from "lucide-react";

import { PageHeader } from "@/components/shared/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableEmpty, TableHead, TableHeader, TableRow, TableWrap,
} from "@/components/ui/table";
import { api, apiSafe } from "@/lib/api";
import { formatDate, humanise, truncateHash } from "@/lib/format";
import type { AuditEntry, Paged } from "@/lib/types";

export const metadata: Metadata = { title: "Audit logs" };

export default async function AuditLogsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const params = await searchParams;
  const [entries, chain, actions] = await Promise.all([
    api<Paged<AuditEntry>>("/audit-logs", {
      searchParams: {
        page: Number(params.page ?? 1),
        page_size: 60,
        action: params.action,
        resource_type: params.resource_type,
        resource_id: params.resource_id,
        search: params.search,
      },
    }),
    apiSafe<{
      intact: boolean;
      entries_checked: number;
      entries_total: number;
      head_hash: string;
      broken_at: Record<string, unknown> | null;
      algorithm: string;
      note: string;
    }>("/audit-logs/chain/verify"),
    apiSafe<{ actions: string[] }>("/audit-logs/actions"),
  ]);

  const query = new URLSearchParams(
    Object.entries(params).filter(([, value]) => value) as [string, string][],
  );

  return (
    <>
      <PageHeader
        title="Audit trail"
        description="Append-only and hash-chained: each entry commits to the previous one, so removing or
          editing history invalidates every hash after it. Special-category fields are redacted
          before an entry is written — this log records who did what, not the contents of a medical
          document."
        actions={
          params.resource_id ? (
            <Button variant="outline" size="sm" asChild>
              <Link href="/audit-logs">Clear resource filter</Link>
            </Button>
          ) : null
        }
      />

      {chain && (
        <Alert variant={chain.intact ? "success" : "danger"}>
          {chain.intact ? <CheckCircle2 /> : <ShieldAlert />}
          <div>
            <AlertTitle>
              {chain.intact
                ? `Chain intact across ${chain.entries_checked} of ${chain.entries_total} entries`
                : "Chain integrity check FAILED"}
            </AlertTitle>
            <AlertDescription>
              {chain.note} Algorithm: <span className="font-mono">{chain.algorithm}</span>. Head
              hash <span className="font-mono">{truncateHash(chain.head_hash, 16)}</span>.
              {chain.broken_at && (
                <span className="mt-1 block font-mono">
                  First divergence at sequence {String((chain.broken_at as any).seq)}.
                </span>
              )}
            </AlertDescription>
          </div>
        </Alert>
      )}

      <div className="flex flex-wrap items-center gap-1.5">
        <Button variant={!params.action ? "secondary" : "ghost"} size="sm" asChild>
          <Link href="/audit-logs">All actions</Link>
        </Button>
        {[
          "document.uploaded",
          "analysis.completed",
          "review.action",
          "finding.modified",
          "claim.decision",
          "verification.completed",
          "report.generated",
          "user.login",
        ].map((action) => (
          <Button
            key={action}
            variant={params.action === action ? "secondary" : "ghost"}
            size="sm"
            asChild
          >
            <Link href={`/audit-logs?action=${action}`}>{action}</Link>
          </Button>
        ))}
      </div>

      <section className="panel">
        <header className="panel-header">
          <p className="text-2xs text-muted-foreground">
            <span className="tabular font-semibold text-foreground">{entries.meta.total}</span>{" "}
            entr{entries.meta.total === 1 ? "y" : "ies"}
            {params.resource_id && (
              <span className="ml-1 font-mono">· resource {params.resource_id.slice(0, 8)}…</span>
            )}
          </p>
          <span className="text-2xs text-muted-foreground">
            {actions?.actions.length ?? 0} action types recorded by the platform
          </span>
        </header>
        <TableWrap>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Seq</TableHead>
                <TableHead>When</TableHead>
                <TableHead>Actor</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Resource</TableHead>
                <TableHead>Summary</TableHead>
                <TableHead>Change</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Hash</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.items.length === 0 && (
                <TableEmpty colSpan={9}>No audit entries match this filter.</TableEmpty>
              )}
              {entries.items.map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell className="tabular text-2xs text-muted-foreground">{entry.seq}</TableCell>
                  <TableCell className="whitespace-nowrap text-2xs">
                    {formatDate(entry.created_at, true)}
                  </TableCell>
                  <TableCell className="text-2xs">
                    {entry.actor_email ?? <span className="text-muted-foreground">system</span>}
                    {entry.actor_role && (
                      <span className="block text-muted-foreground">{humanise(entry.actor_role)}</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className="font-mono">
                      {entry.action}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-2xs">
                    {entry.resource_type}
                    {entry.resource_id && (
                      <span className="block font-mono text-muted-foreground">
                        {entry.resource_id.slice(0, 8)}…
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="max-w-[320px] text-2xs text-muted-foreground">
                    {entry.summary}
                  </TableCell>
                  <TableCell className="max-w-[260px] text-2xs">
                    {entry.before_state || entry.after_state ? (
                      <details>
                        <summary className="cursor-pointer text-muted-foreground">diff</summary>
                        <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap font-mono text-2xs scrollbar-thin">
                          {JSON.stringify(
                            { before: entry.before_state, after: entry.after_state },
                            null,
                            1,
                          )}
                        </pre>
                      </details>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-2xs text-muted-foreground">
                    {entry.ip_address ?? "—"}
                    {entry.request_id && (
                      <span className="block font-mono">{entry.request_id.slice(0, 8)}</span>
                    )}
                  </TableCell>
                  <TableCell className="font-mono text-2xs text-muted-foreground">
                    {entry.entry_hash.slice(0, 8)}
                    <span className="block opacity-60">
                      ← {entry.prev_hash ? entry.prev_hash.slice(0, 8) : "genesis"}
                    </span>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableWrap>
        {entries.meta.pages > 1 && (
          <footer className="flex items-center justify-between border-t px-4 py-2.5">
            <Button variant="outline" size="sm" disabled={!entries.meta.has_previous} asChild>
              <Link
                href={`/audit-logs?${new URLSearchParams({
                  ...Object.fromEntries(query),
                  page: String(entries.meta.page - 1),
                })}`}
              >
                Previous
              </Link>
            </Button>
            <span className="tabular text-2xs text-muted-foreground">
              {entries.meta.page} / {entries.meta.pages}
            </span>
            <Button variant="outline" size="sm" disabled={!entries.meta.has_next} asChild>
              <Link
                href={`/audit-logs?${new URLSearchParams({
                  ...Object.fromEntries(query),
                  page: String(entries.meta.page + 1),
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
