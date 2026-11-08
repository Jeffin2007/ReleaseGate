import { forwardRef, HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export interface TooltipProps extends HTMLAttributes<HTMLDivElement> {
  content: string;
  side?: "top" | "right" | "bottom" | "left";
}

const Tooltip = forwardRef<HTMLDivElement, TooltipProps>(
  ({ className, content, children, side = "top", ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn("relative inline-flex", className)}
        title={content}
        {...props}
      >
        {children}
      </div>
    );
  }
);
Tooltip.displayName = "Tooltip";

export { Tooltip };
