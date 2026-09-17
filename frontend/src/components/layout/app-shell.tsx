"use client";

import { useState } from "react";
import { Menu, X } from "lucide-react";

import { Sidebar } from "@/components/layout/sidebar";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { UserMenu } from "@/components/layout/user-menu";
import { DemoBadge } from "@/components/shared/demo-notice";
import { Button } from "@/components/ui/button";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { SessionUser } from "@/lib/types";

export function AppShell({
  user,
  appName,
  version,
  demoMode,
  children,
}: {
  user: SessionUser;
  appName: string;
  version: string;
  demoMode: boolean;
  children: React.ReactNode;
}) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <TooltipProvider>
      <div className="flex min-h-screen">
        {/* Desktop navigation */}
        <aside className="hidden w-60 shrink-0 border-r border-white/5 lg:block">
          <div className="sticky top-0 h-screen">
            <Sidebar permissions={user.permissions} appName={appName} version={version} />
          </div>
        </aside>

        {/* Mobile navigation */}
        {mobileOpen && (
          <div className="fixed inset-0 z-50 lg:hidden">
            <button
              type="button"
              aria-label="Close navigation"
              className="absolute inset-0 bg-slate-950/60 backdrop-blur-sm"
              onClick={() => setMobileOpen(false)}
            />
            <div className="absolute inset-y-0 left-0 w-64 animate-slide-up shadow-2xl">
              <Sidebar
                permissions={user.permissions}
                appName={appName}
                version={version}
                onNavigate={() => setMobileOpen(false)}
              />
            </div>
          </div>
        )}

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-40 flex h-14 items-center gap-2 border-b bg-background/85 px-4 backdrop-blur">
            <Button
              variant="ghost"
              size="icon-sm"
              className="lg:hidden"
              onClick={() => setMobileOpen((open) => !open)}
              aria-label="Toggle navigation"
            >
              {mobileOpen ? <X className="size-4" /> : <Menu className="size-4" />}
            </Button>

            <div className="flex min-w-0 flex-1 items-center gap-2">
              {demoMode && (
                <DemoBadge label="Demo environment — bundled sample data" className="hidden sm:inline-flex" />
              )}
            </div>

            <ThemeToggle />
            <UserMenu user={user} />
          </header>

          <main className="min-w-0 flex-1 px-4 py-5 md:px-6 lg:px-7">
            <div className="mx-auto w-full max-w-[1560px] space-y-5">{children}</div>
          </main>
        </div>
      </div>
    </TooltipProvider>
  );
}
