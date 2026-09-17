"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { RotateCcw, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

const ANY = "__any__";

/** Filter bar. One row above the table, as filters should be. */
export function DocumentFilters({
  documentTypes,
}: {
  documentTypes: Array<{ value: string; label: string }>;
}) {
  const router = useRouter();
  const params = useSearchParams();
  const [search, setSearch] = useState(params.get("search") ?? "");

  const push = useCallback(
    (updates: Record<string, string | undefined>) => {
      const next = new URLSearchParams(params.toString());
      for (const [key, value] of Object.entries(updates)) {
        if (!value || value === ANY) next.delete(key);
        else next.set(key, value);
      }
      next.delete("page");
      router.push(`/documents?${next.toString()}`);
    },
    [params, router],
  );

  useEffect(() => {
    setSearch(params.get("search") ?? "");
  }, [params]);

  const active =
    params.get("status") ||
    params.get("risk_band") ||
    params.get("document_type") ||
    params.get("verification_state") ||
    params.get("search");

  return (
    <div className="flex flex-wrap items-center gap-2">
      <form
        className="relative"
        onSubmit={(event) => {
          event.preventDefault();
          push({ search });
        }}
      >
        <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Reference, filename or SHA-256"
          className="h-9 w-64 pl-8 text-xs"
        />
      </form>

      <Select
        value={params.get("risk_band") ?? ANY}
        onValueChange={(value) => push({ risk_band: value })}
      >
        <SelectTrigger className="h-9 w-[168px]">
          <SelectValue placeholder="Any risk band" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>Any risk band</SelectItem>
          <SelectItem value="high_concern">High Concern</SelectItem>
          <SelectItem value="review_recommended">Review Recommended</SelectItem>
          <SelectItem value="low_concern">Low Concern</SelectItem>
        </SelectContent>
      </Select>

      <Select value={params.get("status") ?? ANY} onValueChange={(value) => push({ status: value })}>
        <SelectTrigger className="h-9 w-[150px]">
          <SelectValue placeholder="Any status" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>Any status</SelectItem>
          <SelectItem value="analyzed">Analysed</SelectItem>
          <SelectItem value="partial">Partial coverage</SelectItem>
          <SelectItem value="processing">Processing</SelectItem>
          <SelectItem value="queued">Queued</SelectItem>
          <SelectItem value="failed">Failed</SelectItem>
          <SelectItem value="quarantined">Quarantined</SelectItem>
        </SelectContent>
      </Select>

      <Select
        value={params.get("document_type") ?? ANY}
        onValueChange={(value) => push({ document_type: value })}
      >
        <SelectTrigger className="h-9 w-[170px]">
          <SelectValue placeholder="Any document type" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>Any document type</SelectItem>
          {documentTypes.map((type) => (
            <SelectItem key={type.value} value={type.value}>
              {type.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={params.get("verification_state") ?? ANY}
        onValueChange={(value) => push({ verification_state: value })}
      >
        <SelectTrigger className="h-9 w-[168px]">
          <SelectValue placeholder="Any verdict" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>Any human verdict</SelectItem>
          <SelectItem value="unverified">Unverified</SelectItem>
          <SelectItem value="verified">Verified</SelectItem>
          <SelectItem value="information_requested">Information requested</SelectItem>
          <SelectItem value="rejected">Rejected</SelectItem>
        </SelectContent>
      </Select>

      {active && (
        <Button variant="ghost" size="sm" onClick={() => router.push("/documents")}>
          <RotateCcw className="size-3.5" /> Clear
        </Button>
      )}
    </div>
  );
}
