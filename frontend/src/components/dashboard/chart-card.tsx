"use client";

import { useEffect, useState } from "react";
import { BarChart3, TableIcon } from "lucide-react";
import { useTheme } from "next-themes";

import { DARK_THEME, LIGHT_THEME, type ChartTheme } from "@/components/dashboard/palette";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow, TableWrap } from "@/components/ui/table";
import { cn } from "@/lib/utils";

export function useChartTheme(): ChartTheme {
  const { resolvedTheme } = useTheme();
  return resolvedTheme === "dark" ? DARK_THEME : LIGHT_THEME;
}

/**
 * Charts are client-only.
 *
 * Their colours come from the resolved theme, which the server cannot know, and
 * Recharts measures its own container on mount. Rendering them during SSR
 * produces a tree the client then refuses to patch - the symptom is an empty
 * chart after a theme change. Deferring one frame costs nothing and removes the
 * whole class of problem.
 */
function useMounted(): boolean {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  return mounted;
}

/**
 * Chart container with a table view.
 *
 * Every chart in the console can be switched to its underlying rows. That is the
 * accessibility relief for colour-carried information, and it is also what an
 * investigator wants when a number has to be quoted in a case note.
 */
export function ChartCard({
  title,
  description,
  children,
  tableColumns,
  tableRows,
  className,
  action,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  tableColumns?: string[];
  tableRows?: Array<Array<string | number>>;
  className?: string;
  action?: React.ReactNode;
}) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const mounted = useMounted();
  const hasTable = Boolean(tableColumns?.length && tableRows);

  return (
    <section className={cn("panel flex flex-col", className)}>
      <header className="panel-header">
        <div className="min-w-0">
          <h2 className="truncate text-xs font-semibold">{title}</h2>
          {description && (
            <p className="mt-0.5 truncate text-2xs text-muted-foreground">{description}</p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {action}
          {hasTable && (
            <div className="flex rounded-md border p-0.5">
              <Button
                variant={view === "chart" ? "secondary" : "ghost"}
                size="icon-sm"
                onClick={() => setView("chart")}
                aria-label="Chart view"
                aria-pressed={view === "chart"}
              >
                <BarChart3 className="size-3.5" />
              </Button>
              <Button
                variant={view === "table" ? "secondary" : "ghost"}
                size="icon-sm"
                onClick={() => setView("table")}
                aria-label="Table view"
                aria-pressed={view === "table"}
              >
                <TableIcon className="size-3.5" />
              </Button>
            </div>
          )}
        </div>
      </header>

      <div className="flex-1 p-3">
        {!mounted ? (
          <div
            className="h-[196px] animate-pulse rounded-md bg-muted/60"
            aria-hidden
            role="presentation"
          />
        ) : view === "chart" || !hasTable ? (
          children
        ) : (
          <TableWrap className="max-h-[260px]">
            <Table>
              <TableHeader>
                <TableRow>
                  {tableColumns!.map((column) => (
                    <TableHead key={column}>{column}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {tableRows!.map((row, index) => (
                  <TableRow key={index}>
                    {row.map((cell, cellIndex) => (
                      <TableCell key={cellIndex} className={cellIndex > 0 ? "tabular" : undefined}>
                        {cell}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableWrap>
        )}
      </div>
    </section>
  );
}

export function ChartTooltip({
  active,
  payload,
  label,
  theme,
  suffix,
}: {
  active?: boolean;
  payload?: Array<{ name?: string; value?: number | string; color?: string; payload?: any }>;
  label?: string | number;
  theme: ChartTheme;
  suffix?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="rounded-md border px-2.5 py-2 text-2xs shadow-lg"
      style={{ background: theme.tooltipBg, borderColor: theme.tooltipBorder, color: theme.ink }}
    >
      {label !== undefined && <p className="mb-1 font-semibold">{label}</p>}
      <ul className="space-y-0.5">
        {payload.map((entry, index) => (
          <li key={index} className="flex items-center gap-2">
            {entry.color && (
              <span
                className="inline-block size-2 shrink-0 rounded-sm"
                style={{ background: entry.color }}
                aria-hidden
              />
            )}
            <span style={{ color: theme.inkMuted }}>{entry.name}</span>
            <span className="tabular ml-auto font-semibold">
              {entry.value}
              {suffix ?? ""}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ChartLegend({
  items,
  className,
}: {
  items: Array<{ label: string; color: string }>;
  className?: string;
}) {
  return (
    <ul className={cn("flex flex-wrap items-center gap-x-4 gap-y-1", className)}>
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5 text-2xs text-muted-foreground">
          <span
            className="inline-block size-2 rounded-sm"
            style={{ background: item.color }}
            aria-hidden
          />
          {item.label}
        </li>
      ))}
    </ul>
  );
}
