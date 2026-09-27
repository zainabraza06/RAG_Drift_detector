import { FileMinus, Layers, RotateCcw } from "lucide-react";
import type { ReactNode } from "react";

import { RunEvaluationButton } from "@/components/RunEvaluationButton";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { useToast } from "@/components/ui/toast-context";
import { ApiError } from "@/lib/api";
import { useApplyScenario, useDemoState } from "@/lib/queries";
import type { DemoIndexState, DemoScenario } from "@/lib/types";

const SCENARIO_TOAST: Record<DemoScenario, string> = {
  "delete-documents": "Six documents the golden set expects were deleted.",
  rechunk: "Every document was split into sentence fragments.",
  restore: "The index is back to the clean demo corpus.",
};

/**
 * Lets a visitor cause drift and watch it be caught.
 *
 * Nothing else writes to the demo index, so without this every evaluation
 * scores the same and the verdict is always "stable". The buttons only change
 * the index, as an outside pipeline would; the verdict and the diagnosis come
 * from the real detector on the next run. Renders nothing unless the
 * deployment has opted in.
 */
export function DemoPanel() {
  const { data } = useDemoState();
  const mutation = useApplyScenario();
  const { push } = useToast();

  if (!data?.enabled) return null;

  const apply = (scenario: DemoScenario) =>
    mutation.mutate(scenario, {
      onSuccess: () =>
        push({
          tone: "success",
          title: "Index changed",
          description: `${SCENARIO_TOAST[scenario]} Now run an evaluation.`,
        }),
      onError: (error) =>
        push({
          tone: "error",
          title: "Could not change the index",
          description:
            error instanceof ApiError ? error.message : "The request failed.",
        }),
    });

  const pending = mutation.isPending ? mutation.variables : undefined;

  return (
    <Card>
      <CardHeader
        title="Try it: simulate drift"
        description="Nothing else changes this demo's index, so every run would score the same. Break it yourself and watch the detector catch it."
      />
      <CardBody className="space-y-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-small text-ink-secondary">Index now:</span>
          <IndexBadge state={data} />
        </div>

        <Step number={1} title="Change the index">
          <div className="flex flex-wrap gap-2">
            <Button
              icon={<FileMinus className="h-3.5 w-3.5" aria-hidden />}
              loading={pending === "delete-documents"}
              disabled={mutation.isPending || data.missing_documents > 0}
              onClick={() => apply("delete-documents")}
            >
              Delete 6 documents
            </Button>
            <Button
              icon={<Layers className="h-3.5 w-3.5" aria-hidden />}
              loading={pending === "rechunk"}
              disabled={mutation.isPending || data.fragment_documents > 0}
              onClick={() => apply("rechunk")}
            >
              Botched re-chunk
            </Button>
            <Button
              variant="ghost"
              icon={<RotateCcw className="h-3.5 w-3.5" aria-hidden />}
              loading={pending === "restore"}
              disabled={mutation.isPending || data.healthy}
              onClick={() => apply("restore")}
            >
              Restore
            </Button>
          </div>
          <p className="mt-2 text-small text-ink-tertiary">
            Deleting documents is a <em>content</em> failure: the right answers
            are gone. A re-chunk loses nothing but buries the originals under
            fragments, which is a <em>ranking</em> failure. The diagnostics
            should tell them apart.
          </p>
        </Step>

        <Step number={2} title="Run an evaluation">
          <RunEvaluationButton variant="primary" />
          <p className="mt-2 text-small text-ink-tertiary">
            Each run is compared with the previous three, so the change shows
            up on the first run after it. The verdict and diagnosis appear at
            the top of this page.
          </p>
        </Step>
      </CardBody>
    </Card>
  );
}

function IndexBadge({ state }: { state: DemoIndexState }) {
  if (state.healthy) {
    return (
      <Badge tone="success">Healthy · {state.document_count} documents</Badge>
    );
  }
  return (
    <>
      {state.missing_documents > 0 ? (
        <Badge tone="danger">
          {state.missing_documents} expected document
          {state.missing_documents === 1 ? "" : "s"} missing
        </Badge>
      ) : null}
      {state.fragment_documents > 0 ? (
        <Badge tone="warning">
          {state.fragment_documents} re-chunk fragments added
        </Badge>
      ) : null}
    </>
  );
}

function Step({
  number,
  title,
  children,
}: {
  number: number;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="flex gap-3">
      <span
        className="tnum grid h-5 w-5 shrink-0 place-items-center rounded-full bg-inset text-label font-medium text-ink-secondary"
        aria-hidden
      >
        {number}
      </span>
      <div className="min-w-0 flex-1">
        <h3 className="mb-2 text-small font-medium text-ink">{title}</h3>
        {children}
      </div>
    </div>
  );
}
