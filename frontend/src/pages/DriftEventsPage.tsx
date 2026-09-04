import { ChevronDown, Radar } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { DiagnosticsPanel } from "@/components/DiagnosticsPanel";
import { DriftAssessmentCard } from "@/components/DriftAssessmentCard";
import { RunEvaluationButton } from "@/components/RunEvaluationButton";
import { EmptyState } from "@/components/states/EmptyState";
import { ErrorState } from "@/components/states/ErrorState";
import { ListSkeleton } from "@/components/states/LoadingState";
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
          <h1 className="text-2xl font-semibold tracking-tight text-content">
            Drift events
          </h1>
          <p className="mt-1 text-sm text-content-muted">
            Every assessment, with the statistical reasoning that produced it.
          </p>
        </div>

        <div
          role="tablist"
          aria-label="Filter by verdict"
          className="flex flex-wrap gap-0.5 rounded-lg border border-line bg-surface p-0.5"
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
                "rounded-md px-2.5 py-1 text-xs font-medium transition-colors duration-150",
                filter === option.value
                  ? "bg-surface-muted text-content"
                  : "text-content-subtle hover:text-content-muted",
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
  const Icon = meta.icon;

  return (
    <li
      className={cn(
        "overflow-hidden rounded-xl border bg-surface shadow-card transition-[border-color,box-shadow] duration-200",
        highlighted ? "border-brand/50 shadow-raised" : "border-line hover:border-line-strong",
      )}
    >
      <button
        onClick={onToggle}
        aria-expanded={expanded}
        className="flex w-full items-start gap-3 px-5 py-4 text-left transition-colors duration-150 hover:bg-surface-muted/50"
      >
        <span
          className={cn(
            "mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg ring-1 ring-inset",
            meta.tone === "critical" && "bg-critical-soft text-critical ring-critical/25",
            meta.tone === "healthy" && "bg-healthy-soft text-healthy ring-healthy/25",
            meta.tone === "neutral" && "bg-unknown-soft text-content-muted ring-unknown/20",
          )}
        >
          <Icon className="h-4 w-4" aria-hidden />
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <span className="text-sm font-semibold text-content">{meta.label}</span>
            <span
              className="text-xs text-content-subtle"
              title={formatDateTime(event.detected_at)}
            >
              {formatRelative(event.detected_at)}
            </span>
            <span className="font-mono text-2xs text-content-subtle">
              {shortId(event.run_id)}
            </span>
          </div>
          <p className="mt-1 text-sm leading-relaxed text-content-muted">
            {event.summary}
          </p>
        </div>

        <ChevronDown
          className={cn(
            "mt-1 h-4 w-4 shrink-0 text-content-subtle transition-transform duration-200",
            expanded && "rotate-180",
          )}
          aria-hidden
        />
      </button>

      {expanded ? (
        <div className="animate-fade-in space-y-6 border-t border-line bg-surface-muted/30 px-5 py-5">
          <section>
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-content-muted">
              Statistical assessment
            </h3>
            <DriftAssessmentCard assessment={event} />
          </section>

          {event.diagnostics ? (
            <section>
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-content-muted">
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
