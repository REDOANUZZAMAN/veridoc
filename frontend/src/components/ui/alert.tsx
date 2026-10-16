import * as React from "react";
import { type VariantProps, cva } from "class-variance-authority";

import { cn } from "@/lib/utils";

const alertVariants = cva(
  "relative flex w-full gap-3 rounded-lg border p-3.5 text-xs leading-relaxed [&>svg]:size-4 [&>svg]:shrink-0 [&>svg]:translate-y-0.5",
  {
    variants: {
      variant: {
        default: "border-border bg-muted/50 text-foreground",
        info: "border-primary/25 bg-primary/8 text-foreground [&>svg]:text-primary",
        warning: "border-risk-review/30 bg-risk-review/8 text-foreground [&>svg]:text-risk-review",
        danger: "border-risk-high/30 bg-risk-high/8 text-foreground [&>svg]:text-risk-high",
        success: "border-risk-low/30 bg-risk-low/8 text-foreground [&>svg]:text-risk-low",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

const Alert = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof alertVariants>
>(({ className, variant, ...props }, ref) => (
  <div ref={ref} role="alert" className={cn(alertVariants({ variant }), className)} {...props} />
));
Alert.displayName = "Alert";

const AlertTitle = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("mb-0.5 font-semibold", className)} {...props} />
);

const AlertDescription = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("text-muted-foreground", className)} {...props} />
);

export { Alert, AlertTitle, AlertDescription };
