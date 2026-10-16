import * as React from "react";
import { type VariantProps, cva } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-2xs font-medium leading-5 transition-colors whitespace-nowrap",
  {
    variants: {
      variant: {
        default: "border-primary/20 bg-primary/10 text-primary",
        secondary: "border-border/70 bg-secondary text-secondary-foreground",
        outline: "border-border text-foreground",
        muted: "border-border/70 bg-muted text-muted-foreground",
        low: "border-risk-low/25 bg-risk-low/10 text-risk-low",
        review: "border-risk-review/25 bg-risk-review/10 text-risk-review",
        high: "border-risk-high/25 bg-risk-high/10 text-risk-high",
        success: "border-risk-low/25 bg-risk-low/10 text-risk-low",
        destructive: "border-risk-high/35 bg-risk-high/12 text-risk-high",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
