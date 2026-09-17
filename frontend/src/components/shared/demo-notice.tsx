import { FlaskConical } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/**
 * Wherever a result originates from a bundled demo provider, this marker must
 * appear next to it. Presenting demo output as a real external confirmation is
 * the single most damaging thing this product could do.
 */
export function DemoBadge({ className, label = "Demo provider" }: { className?: string; label?: string }) {
  return (
    <Badge variant="outline" className={cn("border-dashed text-muted-foreground", className)}>
      <FlaskConical className="size-3" />
      {label}
    </Badge>
  );
}

export function DemoNotice({
  title = "Demo data source",
  children,
  className,
}: {
  title?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Alert variant="warning" className={className}>
      <FlaskConical />
      <div>
        <AlertTitle>{title}</AlertTitle>
        <AlertDescription>{children}</AlertDescription>
      </div>
    </Alert>
  );
}
