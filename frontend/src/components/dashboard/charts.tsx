"use client";

import {
  Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { ChartLegend, ChartTooltip, useChartTheme } from "@/components/dashboard/chart-card";
import { BAND_LABEL } from "@/components/dashboard/palette";
import { humanise } from "@/lib/format";

const AXIS_FONT = { fontSize: 10, fontVariantNumeric: "tabular-nums" as const };

/** Risk distribution: ordered bands, so the ordinal ramp carries the ordering. */
export function RiskDistributionChart({
  data,
}: {
  data: Array<{ band: string; label: string; count: number }>;
}) {
  const theme = useChartTheme();
  const ordered = ["low_concern", "review_recommended", "high_concern"].map((band) => {
    const found = data.find((row) => row.band === band);
    return { band, label: BAND_LABEL[band], count: found?.count ?? 0 };
  });
  const total = ordered.reduce((sum, row) => sum + row.count, 0) || 1;

  return (
    <div className="space-y-3">
      {ordered.map((row, index) => (
        <div key={row.band} className="space-y-1">
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-2xs text-muted-foreground">{row.label}</span>
            <span className="tabular text-xs font-semibold">
              {row.count}
              <span className="ml-1 text-2xs font-normal text-muted-foreground">
                {Math.round((row.count / total) * 100)}%
              </span>
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-full" style={{ background: theme.grid }}>
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${Math.max(row.count ? 2 : 0, (row.count / total) * 100)}%`,
                background: theme.bands[index],
              }}
            />
          </div>
        </div>
      ))}
      <p className="pt-1 text-2xs text-muted-foreground">
        {total} assessed document{total === 1 ? "" : "s"}. Bands are triage categories, not
        conclusions about authenticity.
      </p>
    </div>
  );
}

/** Single-series horizontal magnitude bars: one colour, identity on the axis. */
export function CategoryBarChart({
  data,
  height = 220,
  labelWidth = 128,
}: {
  data: Array<{ label: string; count: number }>;
  height?: number;
  labelWidth?: number;
}) {
  const theme = useChartTheme();
  if (!data.length) {
    return <p className="py-10 text-center text-2xs text-muted-foreground">No data yet.</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 28, bottom: 0, left: 0 }}>
        <CartesianGrid horizontal={false} stroke={theme.grid} strokeDasharray="2 3" />
        <XAxis
          type="number"
          allowDecimals={false}
          tick={{ fill: theme.inkMuted, ...AXIS_FONT }}
          axisLine={{ stroke: theme.axis }}
          tickLine={false}
        />
        <YAxis
          type="category"
          dataKey="label"
          width={labelWidth}
          tick={{ fill: theme.inkMuted, ...AXIS_FONT }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          cursor={{ fill: theme.grid, fillOpacity: 0.45 }}
          content={(props) => <ChartTooltip {...(props as any)} theme={theme} />}
        />
        <Bar
          dataKey="count"
          name="Documents"
          fill={theme.primary}
          radius={[0, 4, 4, 0]}
          barSize={12}
          isAnimationActive={false}
          label={{ position: "right", fill: theme.inkMuted, fontSize: 10 }}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Daily intake, stacked by risk band. Ordinal ramp + legend + 2px segment gaps. */
export function DailyVolumeChart({
  data,
}: {
  data: Array<{
    date: string;
    documents: number;
    low_concern: number;
    review_recommended: number;
    high_concern: number;
  }>;
}) {
  const theme = useChartTheme();
  if (!data.length) {
    return (
      <p className="py-14 text-center text-2xs text-muted-foreground">
        No documents have been ingested in this window.
      </p>
    );
  }

  const series = [
    { key: "low_concern", label: BAND_LABEL.low_concern, color: theme.bands[0] },
    { key: "review_recommended", label: BAND_LABEL.review_recommended, color: theme.bands[1] },
    { key: "high_concern", label: BAND_LABEL.high_concern, color: theme.bands[2] },
  ];

  return (
    <div className="space-y-2">
      <ResponsiveContainer width="100%" height={210}>
        <BarChart data={data} margin={{ top: 6, right: 6, bottom: 0, left: -18 }}>
          <CartesianGrid vertical={false} stroke={theme.grid} strokeDasharray="2 3" />
          <XAxis
            dataKey="date"
            tickFormatter={(value: string) =>
              new Date(value).toLocaleDateString("en-GB", { day: "2-digit", month: "short" })
            }
            tick={{ fill: theme.inkMuted, ...AXIS_FONT }}
            axisLine={{ stroke: theme.axis }}
            tickLine={false}
            interval="preserveStartEnd"
            minTickGap={18}
          />
          <YAxis
            allowDecimals={false}
            tick={{ fill: theme.inkMuted, ...AXIS_FONT }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            cursor={{ fill: theme.grid, fillOpacity: 0.45 }}
            content={(props) => (
              <ChartTooltip
                {...(props as any)}
                theme={theme}
                label={
                  (props as any)?.label
                    ? new Date((props as any).label).toLocaleDateString("en-GB", {
                        weekday: "short",
                        day: "2-digit",
                        month: "short",
                      })
                    : undefined
                }
              />
            )}
          />
          {series.map((entry, index) => (
            <Bar
              key={entry.key}
              dataKey={entry.key}
              name={entry.label}
              stackId="volume"
              fill={entry.color}
              barSize={14}
              isAnimationActive={false}
              // 2px surface-coloured gap between stacked segments
              stroke={theme.surface}
              strokeWidth={1}
              radius={index === series.length - 1 ? [3, 3, 0, 0] : undefined}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
      <ChartLegend items={series.map((entry) => ({ label: entry.label, color: entry.color }))} />
    </div>
  );
}

/** Findings per detector family, split by whether a human has adjudicated them. */
export function FindingsByKindChart({
  data,
}: {
  data: Array<{ kind: string; total: number; open: number }>;
}) {
  const theme = useChartTheme();
  if (!data.length) {
    return <p className="py-10 text-center text-2xs text-muted-foreground">No findings yet.</p>;
  }

  const rows = data.map((row) => ({
    label: humanise(row.kind),
    open: row.open,
    adjudicated: Math.max(0, row.total - row.open),
  }));

  const series = [
    { key: "open", label: "Awaiting review", color: theme.bands[1] },
    { key: "adjudicated", label: "Adjudicated", color: theme.bands[0] },
  ];

  return (
    <div className="space-y-2">
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 20, bottom: 0, left: 0 }}>
          <CartesianGrid horizontal={false} stroke={theme.grid} strokeDasharray="2 3" />
          <XAxis
            type="number"
            allowDecimals={false}
            tick={{ fill: theme.inkMuted, ...AXIS_FONT }}
            axisLine={{ stroke: theme.axis }}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="label"
            width={116}
            tick={{ fill: theme.inkMuted, ...AXIS_FONT }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            cursor={{ fill: theme.grid, fillOpacity: 0.45 }}
            content={(props) => <ChartTooltip {...(props as any)} theme={theme} />}
          />
          {series.map((entry, index) => (
            <Bar
              key={entry.key}
              dataKey={entry.key}
              name={entry.label}
              stackId="findings"
              fill={entry.color}
              barSize={12}
              isAnimationActive={false}
              stroke={theme.surface}
              strokeWidth={1}
              radius={index === series.length - 1 ? [0, 4, 4, 0] : undefined}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
      <ChartLegend items={series.map((entry) => ({ label: entry.label, color: entry.color }))} />
    </div>
  );
}

/** Verification outcomes. Ordinal by how much the answer supports the document. */
export function VerificationOutcomeChart({
  data,
}: {
  data: Array<{ outcome: string; count: number }>;
}) {
  const theme = useChartTheme();
  const order = ["match", "partial_match", "mismatch", "not_found", "unavailable"];
  const rows = order
    .map((outcome) => ({
      label: humanise(outcome),
      outcome,
      count: data.find((row) => row.outcome === outcome)?.count ?? 0,
    }))
    .filter((row) => row.count > 0);

  if (!rows.length) {
    return (
      <p className="py-10 text-center text-2xs text-muted-foreground">
        No verification has been requested yet.
      </p>
    );
  }

  // Supportive answers use the light end of the ramp, contradicting answers the
  // dark end; "unavailable" is chrome-grey because it says nothing either way.
  const colourFor = (outcome: string) =>
    outcome === "match"
      ? theme.bands[0]
      : outcome === "partial_match"
        ? theme.bands[1]
        : outcome === "unavailable"
          ? theme.axis
          : theme.bands[2];

  return (
    <ResponsiveContainer width="100%" height={170}>
      <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 28, bottom: 0, left: 0 }}>
        <CartesianGrid horizontal={false} stroke={theme.grid} strokeDasharray="2 3" />
        <XAxis
          type="number"
          allowDecimals={false}
          tick={{ fill: theme.inkMuted, ...AXIS_FONT }}
          axisLine={{ stroke: theme.axis }}
          tickLine={false}
        />
        <YAxis
          type="category"
          dataKey="label"
          width={100}
          tick={{ fill: theme.inkMuted, ...AXIS_FONT }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          cursor={{ fill: theme.grid, fillOpacity: 0.45 }}
          content={(props) => <ChartTooltip {...(props as any)} theme={theme} />}
        />
        <Bar
          dataKey="count"
          name="Checks"
          radius={[0, 4, 4, 0]}
          barSize={12}
          isAnimationActive={false}
          label={{ position: "right", fill: theme.inkMuted, fontSize: 10 }}
        >
          {rows.map((row) => (
            <Cell key={row.outcome} fill={colourFor(row.outcome)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
