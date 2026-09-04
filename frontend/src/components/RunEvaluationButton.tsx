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
}: RunEvaluationButtonProps) {
  const { push } = useToast();
  const mutation = useRunEvaluation();

  return (
    <Button
      variant={variant}
      size={size}
      className={className}
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
      {mutation.isPending ? "Running…" : "Run evaluation"}
    </Button>
  );
}
