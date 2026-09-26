import { Loader2 } from "lucide-react";

import { useBackendState, useRecoverAfterWake } from "@/lib/warmup";

/**
 * Says why the page is slow while the API wakes, instead of leaving a user
 * looking at skeletons with no explanation. Renders nothing on a warm API.
 */
export function BackendWarmup() {
  const state = useBackendState();
  useRecoverAfterWake(state);

  if (state !== "waking") return null;

  return (
    <div
      role="status"
      className="mb-6 flex items-start gap-3 rounded-lg border border-warning-line bg-warning-subtle px-4 py-3"
    >
      <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-warning-text" aria-hidden />
      <div>
        <p className="text-small font-medium text-ink">Waking the server…</p>
        <p className="mt-0.5 text-small text-ink-secondary">
          The API sleeps when nobody is using it and takes about a minute to
          start. The page will fill in by itself.
        </p>
      </div>
    </div>
  );
}
