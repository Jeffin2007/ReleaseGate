import { forwardRef, InputHTMLAttributes, useState } from "react";
import { cn } from "@/lib/utils";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, type = "text", label, error, hint, id, ...props }, ref) => {
    const [focused, setFocused] = useState(false);
    const inputId = id || label?.toLowerCase().replace(/\s+/g, "-");

    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={inputId}
            className={cn(
              "mb-1.5 block text-sm font-medium text-rg-text",
              className
            )}
          >
            {label}
          </label>
        )}
        <div className="relative">
          <input
            id={inputId}
            type={type}
            className={cn(
              "flex h-10 w-full rounded-lg border bg-white px-3 py-2 text-sm text-rg-text placeholder:text-rg-text-muted transition-colors",
              "file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-rg-primary",
              focused && "ring-2 ring-rg-primary/20 border-rg-primary",
              error && "border-red-300 focus:border-red-400 focus:ring-red-200",
              !error && "border-rg-border focus:border-rg-primary focus:ring-2 focus:ring-rg-primary/20",
              className
            )}
            onFocus={(e) => {
              setFocused(true);
              props.onFocus?.(e);
            }}
            onBlur={(e) => {
              setFocused(false);
              props.onBlur?.(e);
            }}
            {...props}
          />
        </div>
        {hint && !error && (
          <p className="mt-1 text-xs text-rg-text-muted">{hint}</p>
        )}
        {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
      </div>
    );
  }
);
Input.displayName = "Input";

export { Input };
