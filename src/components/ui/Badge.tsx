import { forwardRef, HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "success" | "warning" | "error" | "info" | "outline";
  size?: "sm" | "md";
}

const Badge = forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant = "default", size = "md", ...props }, ref) => {
    const variants = {
      default: "bg-rg-surface-alt text-rg-text-muted border-rg-border",
      success: "bg-green-50 text-green-700 border-green-200",
      warning: "bg-amber-50 text-amber-700 border-amber-200",
      error: "bg-red-50 text-red-700 border-red-200",
      info: "bg-blue-50 text-blue-700 border-blue-200",
      outline: "bg-transparent text-rg-text border-rg-border",
    };
    const sizes = {
      sm: "inline-flex items-center px-2 py-0.5 text-xs rounded-full gap-1",
      md: "inline-flex items-center px-2.5 py-1 text-xs rounded-full gap-1.5",
    };

    return (
      <span
        ref={ref}
        className={cn(
          "inline-flex items-center font-medium border",
          variants[variant],
          sizes[size],
          className
        )}
        {...props}
      />
    );
  }
);
Badge.displayName = "Badge";

export { Badge };
