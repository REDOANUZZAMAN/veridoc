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
    <div className="flex h-full flex-col bg-sidebar text-sidebar-foreground">
      <div className="flex items-center gap-2.5 px-4 py-4">
        <span className="inline-flex size-8 items-center justify-center rounded-md bg-sidebar-active/15 text-sidebar-active">
          <ShieldCheck className="size-4.5" style={{ width: "1.125rem", height: "1.125rem" }} />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold tracking-tight text-white">{appName}</p>
          <p className="truncate text-2xs text-sidebar-muted">Document Intelligence</p>
        </div>
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto px-2 pb-4 scrollbar-thin">
        {groups.map((group) => {
          const groupItems = items.filter((item) => item.group === group.key);
          if (!groupItems.length) return null;
          return (
            <div key={group.key} className="space-y-1">
              <p className="px-3 pb-1 text-2xs font-semibold uppercase tracking-wider text-sidebar-muted/80">
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
                    className={cn(
                      "group flex items-center gap-2.5 rounded-md px-3 py-2 text-xs font-medium transition-colors",
                      active
                        ? "bg-sidebar-active/15 text-white"
                        : "text-sidebar-foreground/85 hover:bg-white/5 hover:text-white",
                    )}
                  >
                    <Icon
                      className={cn(
                        "size-4 shrink-0",
                        active ? "text-sidebar-active" : "text-sidebar-muted group-hover:text-white",
                      )}
                    />
                    <span className="truncate">{item.label}</span>
                    {active && <span className="ml-auto size-1.5 rounded-full bg-sidebar-active" />}
                  </Link>
                );
              })}
            </div>
          );
        })}
      </nav>

      <div className="space-y-1 border-t border-white/10 px-4 py-3">
        <p className="text-2xs text-sidebar-muted">Pipeline {version}</p>
        <p className="text-2xs leading-relaxed text-sidebar-muted/80">
          Decision-support only. Findings are signals for human review, never verdicts.
        </p>
      </div>
    </div>
  );
}
