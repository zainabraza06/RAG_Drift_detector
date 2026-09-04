import { AlertTriangle, RefreshCw, ServerCrash, WifiOff } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";

interface ErrorStateProps {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}

/**
 * A readable failure.
 *
 * The backend's error envelope carries a machine-readable `code`, so the UI
 * can say something specific rather than printing an exception. Retry is only
 * offered when retrying could plausibly help.
 */
export function ErrorState({ error, onRetry, className }: ErrorStateProps) {
  const api = error instanceof ApiError ? error : null;
  const isNetwork = api?.code === "network_error";
  const isStoreDown = api?.status === 503;

  const Icon = isNetwork ? WifiOff : isStoreDown ? ServerCrash : AlertTriangle;

  const title = isNetwork
    ? "Cannot reach the API"
    : isStoreDown
      ? "The vector store is unavailable"
      : "Something went wrong";

  const description =
    api?.message ??
    (error instanceof Error ? error.message : "An unexpected error occurred.");

  const canRetry = onRetry && (!api || api.isTransient || isNetwork);

  return (
    <div
      role="alert"
      className={cn(
        "flex animate-fade-in flex-col items-center justify-center px-6 py-12 text-center",
        className,
      )}
    >
      <span className="mb-4 grid h-12 w-12 place-items-center rounded-xl border border-critical/25 bg-critical-soft">
        <Icon className="h-5 w-5 text-critical" aria-hidden />
      </span>
      <h3 className="text-base font-semibold text-content">{title}</h3>
      <p className="mt-1.5 max-w-md text-sm leading-relaxed text-content-muted">
        {description}
      </p>
      {api?.detail?.length ? (
        <ul className="mt-3 space-y-1 text-left text-xs text-content-muted">
          {api.detail.map((item) => (
            <li key={item.field} className="flex gap-1.5">
              <span className="font-mono text-critical">{item.field}</span>
              <span>{item.message}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {canRetry ? (
        <Button
          className="mt-5"
          onClick={onRetry}
          icon={<RefreshCw className="h-3.5 w-3.5" aria-hidden />}
        >
          Try again
        </Button>
      ) : null}
    </div>
  );
}
