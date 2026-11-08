import { useState, useCallback, useRef, useEffect } from "react";
import { X, CheckCircle, AlertCircle, Info, AlertTriangle } from "lucide-react";

export interface Toast {
  id: string;
  type: "success" | "error" | "info" | "warning";
  title: string;
  message?: string;
  duration?: number;
}

interface ToastItemProps {
  toast: Toast;
  onDismiss: (id: string) => void;
}

function ToastItem({ toast, onDismiss }: ToastItemProps) {
  const icons = {
    success: CheckCircle,
    error: AlertCircle,
    info: Info,
    warning: AlertTriangle,
  };
  const Icon = icons[toast.type];
  const colors = {
    success: "bg-green-50 border-green-200 text-green-800",
    error: "bg-red-50 border-red-200 text-red-800",
    info: "bg-blue-50 border-blue-200 text-blue-800",
    warning: "bg-amber-50 border-amber-200 text-amber-800",
  };
  const borderColors = {
    success: "border-l-green-500",
    error: "border-l-red-500",
    info: "border-l-blue-500",
    warning: "border-l-amber-500",
  };

  return (
    <div
      className={`pointer-events-auto flex w-96 shrink-0 flex-col gap-2 rounded-lg border border-rg-border bg-white shadow-lg border-l-4 ${borderColors[toast.type]} ${colors[toast.type]} animate-slide-in`}
      role="alert"
    >
      <div className="flex items-start gap-3">
        <Icon className="h-4 w-4 shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold">{toast.title}</p>
          {toast.message && (
            <p className="mt-0.5 text-xs opacity-80">{toast.message}</p>
          )}
        </div>
        <button
          onClick={() => onDismiss(toast.id)}
          className="shrink-0 rounded p-0.5 hover:bg-black/5 transition-colors"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}

export function ToastContainer() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counterRef = useRef(0);

  const addToast = useCallback(
    (toast: Omit<Toast, "id">) => {
      const id = `toast-${++counterRef.current}`;
      setToasts((prev) => [...prev, { ...toast, id }]);
      const duration = toast.duration || 5000;
      if (duration > 0) {
        setTimeout(() => {
          setToasts((prev) => prev.filter((t) => t.id !== id));
        }, duration);
      }
    },
    []
  );

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  // Expose addToast globally for easy use
  useEffect(() => {
    (window as any).__rgToast = addToast;
  }, [addToast]);

  return (
    <div
      className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 z-50"
      aria-live="polite"
      aria-label="Notifications"
    >
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={dismiss} />
      ))}
    </div>
  );
}

// Convenience function for adding toasts from anywhere
export function toast(
  type: Toast["type"],
  title: string,
  message?: string,
  duration?: number
) {
  const addToast = (window as any).__rgToast;
  if (addToast) {
    addToast({ type, title, message, duration });
  }
}
