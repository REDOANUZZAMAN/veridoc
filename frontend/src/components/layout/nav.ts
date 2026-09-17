import {
  Activity, ClipboardList, Cog, FileSearch, FileStack, Gauge, PlugZap, ScrollText,
  ShieldCheck, SlidersHorizontal, Users,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: typeof Gauge;
  permission?: string;
  description: string;
  group: "operations" | "configuration";
}

/** The sidebar. Items the signed-in role cannot use are not rendered at all. */
export const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: Gauge, permission: "dashboard:read",
    description: "Queue health and risk distribution", group: "operations" },
  { href: "/documents", label: "Documents", icon: FileStack, permission: "document:read",
    description: "Every ingested document and its analysis", group: "operations" },
  { href: "/claims", label: "Claims", icon: ClipboardList, permission: "claim:read",
    description: "Claim bundles and decisions", group: "operations" },
  { href: "/investigations", label: "Investigations", icon: FileSearch,
    permission: "investigation:read", description: "Open and closed cases", group: "operations" },
  { href: "/verification", label: "Verification", icon: ShieldCheck,
    permission: "verification:read", description: "Trusted-source check history", group: "operations" },
  { href: "/reports", label: "Reports", icon: ScrollText, permission: "report:read",
    description: "Generated evidence reports", group: "operations" },
  { href: "/rules", label: "Rules", icon: SlidersHorizontal, permission: "rule:read",
    description: "Detection rules and risk weights", group: "configuration" },
  { href: "/integrations", label: "Integrations", icon: PlugZap, permission: "provider:read",
    description: "OCR, detection and verification providers", group: "configuration" },
  { href: "/users", label: "Users", icon: Users, permission: "user:read",
    description: "Accounts and roles", group: "configuration" },
  { href: "/audit-logs", label: "Audit Logs", icon: Activity, permission: "audit:read",
    description: "Append-only activity trail", group: "configuration" },
  { href: "/settings", label: "Settings", icon: Cog, permission: "settings:read",
    description: "Thresholds, retention and privacy", group: "configuration" },
];

export function visibleNav(permissions: string[]): NavItem[] {
  return NAV_ITEMS.filter((item) => !item.permission || permissions.includes(item.permission));
}
