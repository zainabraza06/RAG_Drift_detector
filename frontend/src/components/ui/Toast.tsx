import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import {
  ToastContext,
  type ToastMessage,
  type ToastTone,
} from "@/components/ui/toast-context";
import { cn } from "@/lib/cn";

const ICONS: Record<ToastTone, ReactNode> = {
  success: <CheckCircle2 className="h-4 w-4 text-healthy" aria-hidden />,
  error: <AlertCircle className="h-4 w-4 text-critical" aria-hidden />,
  info: <Info className="h-4 w-4 text-brand" aria-hidden />,
};

const DISMISS_AFTER_MS = 6000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const push = useCallback((toast: Omit<ToastMessage, "id">) => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current, { ...toast, id }]);
  }, []);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const value = useMemo(() => ({ push }), [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        // aria-live so a screen reader hears the outcome of an action that
        // produced no visible focus change.
        aria-live="polite"
        className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-full max-w-sm flex-col gap-2"
      >
        {toasts.map((toast) => (
          <ToastItem key={toast.id} toast={toast} onDismiss={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastItem({
  toast,
  onDismiss,
}: {
  toast: ToastMessage;
  onDismiss: (id: number) => void;
}) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), DISMISS_AFTER_MS);
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);

  return (
    <div
      className={cn(
        "pointer-events-auto flex animate-fade-up items-start gap-3 rounded-xl",
        "border border-line bg-surface-raised p-3.5 shadow-popover",
      )}
    >
      <span className="mt-0.5 shrink-0">{ICONS[toast.tone]}</span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-content">{toast.title}</p>
        {toast.description ? (
          <p className="mt-0.5 text-xs leading-relaxed text-content-muted">
            {toast.description}
          </p>
        ) : null}
      </div>
      <button
        onClick={() => onDismiss(toast.id)}
        aria-label="Dismiss notification"
        className="shrink-0 rounded p-0.5 text-content-subtle transition-colors hover:bg-surface-muted hover:text-content"
      >
        <X className="h-3.5 w-3.5" aria-hidden />
      </button>
    </div>
  );
}
