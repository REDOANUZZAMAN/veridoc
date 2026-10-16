"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ShieldCheck } from "lucide-react";

import { visibleNav } from "@/components/layout/nav";
import { cn } from "@/lib/utils";

export function Sidebar({
  permissions,
  appName,
  version,
  onNavigate,
}: {
  permissions: string[];
  appName: string;
  version: string;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const items = visibleNav(permissions);
  const groups = [
    { key: "operations" as const, label: "Operations" },
    { key: "configuration" as const, label: "Configuration" },
  ];

  return (
    <div className="relative flex h-full flex-col overflow-hidden bg-sidebar text-sidebar-foreground">
      {/* A single soft iris bloom behind the wordmark keeps the rail from
          reading as a flat black column. */}
      <div
        className="pointer-events-none absolute -left-16 -top-24 h-64 w-64 rounded-full opacity-60 blur-3xl"
        aria-hidden
        style={{ background: "radial-gradient(circle, hsl(258 90% 62% / 0.35), transparent 70%)" }}
      />

      <div className="relative flex items-center gap-3 px-4 py-5">
        <span className="inline-flex size-9 items-center justify-center rounded-xl bg-white/10 text-sidebar-active ring-1 ring-inset ring-white/15">
          <ShieldCheck className="size-[1.125rem]" />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold tracking-tight text-white">{appName}</p>
          <p className="truncate text-2xs text-sidebar-muted">Document Intelligence</p>
        </div>
      </div>

      <nav className="relative flex-1 space-y-6 overflow-y-auto px-3 pb-4 scrollbar-thin">
        {groups.map((group) => {
          const groupItems = items.filter((item) => item.group === group.key);
          if (!groupItems.length) return null;
          return (
            <div key={group.key} className="space-y-1">
              <p className="px-3 pb-1.5 text-2xs font-semibold uppercase tracking-[0.09em] text-sidebar-muted/70">
                {group.label}
              </p>
              {groupItems.map((item) => {
                const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={onNavigate}
                    title={item.description}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-xs font-medium transition-colors",
                      active
                        ? "bg-white/[0.09] text-white"
                        : "text-sidebar-foreground/80 hover:bg-white/[0.05] hover:text-white",
                    )}
                  >
                    {/* Active marker is a rail, not a colour swap: it survives
                        greyscale and forced-colours rendering. */}
                    <span
                      aria-hidden
                      className={cn(
                        "absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-sidebar-active transition-opacity",
                        active ? "opacity-100" : "opacity-0",
                      )}
                    />
                    <Icon
                      className={cn(
                        "size-4 shrink-0 transition-colors",
                        active
                          ? "text-sidebar-active"
                          : "text-sidebar-muted group-hover:text-sidebar-foreground",
                      )}
                    />
                    <span className="truncate">{item.label}</span>
                  </Link>
                );
              })}
            </div>
          );
        })}
      </nav>

      <div className="relative space-y-1.5 px-4 py-4 hairline-t">
        <p className="text-2xs font-medium text-sidebar-muted">Pipeline {version}</p>
        <p className="text-2xs leading-relaxed text-sidebar-muted/75">
          Decision-support only. Findings are signals for human review, never verdicts.
        </p>
      </div>
    </div>
  );
}
