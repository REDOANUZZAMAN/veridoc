import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function PageHeader({
  title,
  description,
  actions,
  breadcrumb,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  breadcrumb?: ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("flex flex-col gap-4 md:flex-row md:items-start md:justify-between", className)}>
      <div className="min-w-0 space-y-1">
        {breadcrumb && <div className="text-2xs text-muted-foreground">{breadcrumb}</div>}
        <h1 className="truncate text-xl font-semibold">{title}</h1>
        {description && (
          <p className="max-w-3xl text-xs leading-relaxed text-muted-foreground">{description}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2.5 px-6 py-16 text-center">
      {icon && (
        <div className="mb-1 inline-flex size-11 items-center justify-center rounded-xl border bg-surface text-muted-foreground/80">
          {icon}
        </div>
      )}
      <p className="text-sm font-medium">{title}</p>
      {description && <p className="max-w-md text-xs leading-relaxed text-muted-foreground">{description}</p>}
      {action && <div className="pt-2">{action}</div>}
    </div>
  );
}

export function KeyValue({
  items,
  columns = 2,
  className,
}: {
  items: Array<{ label: string; value: ReactNode; mono?: boolean; hint?: string }>;
  columns?: 1 | 2 | 3;
  className?: string;
}) {
  return (
    <dl
      className={cn(
        "grid gap-x-8 gap-y-4",
        columns === 1 && "grid-cols-1",
        columns === 2 && "grid-cols-1 sm:grid-cols-2",
        columns === 3 && "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
        className,
      )}
    >
      {items.map((item) => (
        <div key={item.label} className="min-w-0 space-y-0.5">
          <dt className="eyebrow font-medium">{item.label}</dt>
          <dd className={cn("break-words text-xs leading-relaxed", item.mono && "font-mono text-2xs")}>
            {item.value ?? "—"}
          </dd>
          {item.hint && <p className="text-2xs text-muted-foreground/80">{item.hint}</p>}
        </div>
      ))}
    </dl>
  );
}
