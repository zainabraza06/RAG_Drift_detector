import { ChevronDown, Radar } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { DiagnosticsPanel } from "@/components/DiagnosticsPanel";
import { DriftAssessmentCard } from "@/components/DriftAssessmentCard";
import { RunEvaluationButton } from "@/components/RunEvaluationButton";
import { EmptyState } from "@/components/states/EmptyState";
import { ErrorState } from "@/components/states/ErrorState";
import { ListSkeleton } from "@/components/states/LoadingState";
import { Code } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
import { VERDICT_META } from "@/lib/display";
import { formatDateTime, formatRelative, shortId } from "@/lib/format";
import { useDriftEvents } from "@/lib/queries";
import type { DriftAssessment, DriftVerdict } from "@/lib/types";

const FILTERS: { value: DriftVerdict | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "degraded", label: "Regressions" },
  { value: "stable", label: "Stable" },
  { value: "improved", label: "Improved" },
  { value: "insufficient_data", label: "No baseline" },
];

export function DriftEventsPage() {
  const [params, setParams] = useSearchParams();
  const focusedRun = params.get("run");
  const [filter, setFilter] = useState<DriftVerdict | "all">("all");
  const [expanded, setExpanded] = useState<string | null>(focusedRun);

  const { data, isPending, isError, error, refetch } = useDriftEvents(
    filter === "all" ? undefined : filter,
  );

  // Arriving from a chart marker should open that event, not just list it.
  useEffect(() => {
    if (focusedRun) setExpanded(focusedRun);
  }, [focusedRun]);

  const events = useMemo(() => {
    const items = data?.items ?? [];
    if (!focusedRun) return items;
    // Float the linked event to the top so a deep link lands on it directly.
    return [...items].sort((a, b) =>
      a.run_id === focusedRun ? -1 : b.run_id === focusedRun ? 1 : 0,
    );
  }, [data?.items, focusedRun]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-title text-ink">Drift events</h1>
          <p className="mt-1.5 max-w-prose text-body text-ink-secondary">
            Every assessment, with the statistical reasoning that produced it.
          </p>
        </div>

        <div
          role="tablist"
          aria-label="Filter by verdict"
          className="flex flex-wrap gap-0.5 rounded-md border border-line bg-inset p-0.5"
        >
          {FILTERS.map((option) => (
            <button
              key={option.value}
              role="tab"
              aria-selected={filter === option.value}
              onClick={() => {
                setFilter(option.value);
                if (focusedRun) setParams({}, { replace: true });
              }}
              className={cn(
                "rounded px-2.5 py-1 text-label transition-colors duration-fast ease-out",
                filter === option.value
                  ? "bg-surface text-ink shadow-xs"
                  : "text-ink-tertiary hover:text-ink-secondary",
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {isPending ? (
        <ListSkeleton />
      ) : isError ? (
        <ErrorState error={error} onRetry={() => void refetch()} />
      ) : events.length === 0 ? (
        <Card>
          <EmptyState
            icon={Radar}
            title={
              filter === "all"
                ? "No assessments recorded yet"
                : `No ${FILTERS.find((f) => f.value === filter)?.label.toLowerCase()} events`
            }
            description={
              filter === "all"
                ? "An assessment is produced automatically after every evaluation. Run one to get started."
                : "Try a different filter, or run another evaluation."
            }
            action={filter === "all" ? <RunEvaluationButton /> : null}
          />
        </Card>
      ) : (
        <ol className="space-y-3">
          {events.map((event) => (
            <DriftEventRow
              key={event.run_id}
              event={event}
              expanded={expanded === event.run_id}
              highlighted={focusedRun === event.run_id}
              onToggle={() =>
                setExpanded(expanded === event.run_id ? null : event.run_id)
              }
            />
          ))}
        </ol>
      )}
    </div>
  );
}

/**
 * One event in the timeline.
 *
 * Collapsed it shows the verdict and the plain-English summary; expanded it
 * shows the full comparison table and, separately, the heuristic diagnostics.
 * Raw JSON never reaches the screen.
 */
function DriftEventRow({
  event,
  expanded,
  highlighted,
  onToggle,
}: {
  event: DriftAssessment;
  expanded: boolean;
  highlighted: boolean;
  onToggle: () => void;
}) {
  const meta = VERDICT_META[event.verdict];

  return (
    <li
      className={cn(
        "overflow-hidden rounded-lg border bg-surface shadow-xs transition-colors duration-fast",
        highlighted ? "border-accent-line" : "border-line hover:border-line-strong",
      )}
    >
      <button
        onClick={onToggle}
        aria-expanded={expanded}
        className="flex w-full items-start gap-3 px-5 py-4 text-left transition-colors duration-fast ease-out hover:bg-surface-hover"
      >
        <span
          className={cn("mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full", meta.rail)}
          aria-hidden
        />

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-subheading text-ink">{meta.label}</span>
            <span
              className="text-small text-ink-tertiary"
              title={formatDateTime(event.detected_at)}
            >
              {formatRelative(event.detected_at)}
            </span>
            <Code>{shortId(event.run_id)}</Code>
          </div>
          <p className="mt-1.5 max-w-prose text-body text-ink-secondary">
            {event.summary}
          </p>
        </div>

        <ChevronDown
          className={cn(
            "mt-1 h-4 w-4 shrink-0 text-ink-tertiary transition-transform duration-fast",
            expanded && "rotate-180",
          )}
          aria-hidden
        />
      </button>

      {expanded ? (
        <div className="animate-fade-in space-y-8 border-t border-line-subtle px-5 py-6">
          <section>
            <h3 className="mb-4 text-micro uppercase text-ink-tertiary">
              Statistical assessment
            </h3>
            <DriftAssessmentCard assessment={event} hideSummary />
          </section>

          {event.diagnostics ? (
            <section>
              <h3 className="mb-4 text-micro uppercase text-ink-tertiary">
                Root-cause diagnostics
              </h3>
              <DiagnosticsPanel report={event.diagnostics} />
            </section>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}
