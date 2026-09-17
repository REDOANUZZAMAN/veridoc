import { redirect } from "next/navigation";

import { AppShell } from "@/components/layout/app-shell";
import { APP_NAME, DEMO_MODE } from "@/lib/config";
import { apiSafe } from "@/lib/api";
import { getSessionUser } from "@/lib/session";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const user = await getSessionUser();
  if (!user) redirect("/login");

  const capabilities = await apiSafe<{ versions: { pipeline: string } }>("/system/capabilities");

  return (
    <AppShell
      user={user}
      appName={APP_NAME}
      version={capabilities?.versions?.pipeline ?? "—"}
      demoMode={DEMO_MODE}
    >
      {children}
    </AppShell>
  );
}
