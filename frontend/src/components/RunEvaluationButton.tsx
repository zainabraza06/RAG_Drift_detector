import { Play } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/toast-context";
import { ApiError } from "@/lib/api";
import { formatMetric } from "@/lib/format";
import { useRunEvaluation } from "@/lib/queries";

interface RunEvaluationButtonProps {
  size?: "sm" | "md" | "lg";
  variant?: "primary" | "secondary";
  className?: string;
  /**
   * Hides the label below the `sm` breakpoint. Used in the header, where the
   * full label wraps to two lines on a narrow phone; the icon still carries
   * the meaning and the accessible name is kept on the button.
   */
  compactOnMobile?: boolean;
}

/**
 * The one action this tool has.
 *
 * Evaluation is synchronous on the backend, so the button reports the actual
 * result rather than "queued" — and the toast quotes the headline metric, so a
 * user learns something from clicking even when nothing changed.
 */
export function RunEvaluationButton({
  size = "md",
  variant = "primary",
  className,
  compactOnMobile,
}: RunEvaluationButtonProps) {
  const { push } = useToast();
  const mutation = useRunEvaluation();

  return (
    <Button
      variant={variant}
      size={size}
      className={className}
      aria-label="Run evaluation"
      loading={mutation.isPending}
      icon={<Play className="h-3.5 w-3.5" aria-hidden />}
      onClick={() =>
        mutation.mutate(undefined, {
          onSuccess: (run) => {
            const primary = run.metrics.find((m) => m.k === run.primary_k);
            push({
              tone: "success",
              title: "Evaluation complete",
              description: primary
                ? `Scored ${run.query_count} queries — NDCG@${run.primary_k} ${formatMetric(primary.ndcg_at_k)}.`
                : `Scored ${run.query_count} queries.`,
            });
          },
          onError: (error) => {
            const api = error instanceof ApiError ? error : null;
            push({
              tone: "error",
              title:
                api?.code === "no_active_golden_set"
                  ? "No active golden set"
                  : "Evaluation failed",
              description:
                api?.message ?? "The evaluation could not be completed.",
            });
          },
        })
      }
    >
      <span className={compactOnMobile ? "hidden sm:inline" : undefined}>
        <span className={compactOnMobile ? "hidden sm:inline" : undefined}>
        {mutation.isPending ? "Running…" : "Run evaluation"}
      </span>
      </span>
    </Button>
  );
}
