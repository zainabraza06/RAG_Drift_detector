import {
  ArrowRight,
  Database,
  FileSearch,
  Gauge,
  Layers,
  Rocket,
  Timer,
} from "lucide-react";
import { Link } from "react-router-dom";

import { HealthBadge } from "@/components/HealthBadge";
import { LeadingHypothesis } from "@/components/DiagnosticsPanel";
import { RunEvaluationButton } from "@/components/RunEvaluationButton";
import { StatCard } from "@/components/StatCard";
import { EmptyState } from "@/components/states/EmptyState";
import { ErrorState } from "@/components/states/ErrorState";
import { StatCardsSkeleton } from "@/components/states/LoadingState";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { VerdictBadge } from "@/components/DriftAssessmentCard";
import { cn } from "@/lib/cn";
import { HEALTH_META } from "@/lib/display";
import {
  formatDuration,
  formatInteger,
  formatRelative,
  shortId,
} from "@/lib/format";
import { useDashboard } from "@/lib/queries";
import type { DashboardSummary } from "@/lib/types";
import { METRIC_DESCRIPTIONS, METRIC_LABELS, METRIC_NAMES } from "@/lib/types";

export function DashboardPage() {
  const { data, isPending, isError, error, refetch } = useDashboard();

  if (isPending) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-28 w-full rounded-2xl" />
        <StatCardsSkeleton />
      </div>
    );
  }

  if (isError) {
    return <ErrorState error={error} onRetry={() => void refetch()} />;
  }

  if (!data.has_runs) {
    return <FirstRunState />;
  }

  return (
    <div className="space-y-6">
      <HealthHeader summary={data} />

      <section>
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-content-muted">
          Latest metrics at k={data.latest_run?.primary_k}
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {METRIC_NAMES.map((metric) => (
            <StatCard
              key={metric}
              label={
                METRIC_LABELS[metric] +
                (metric === "mrr" ? "" : `@${data.latest_run?.primary_k}`)
              }
              value={data.primary_metrics?.[metric] ?? null}
              delta={data.metric_deltas[metric] ?? null}
              hint={METRIC_DESCRIPTIONS[metric]}
              primary={data.latest_drift?.config.primary_metric === metric}
            />
          ))}
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-3">
        <LatestAssessment summary={data} />
        <RunFacts summary={data} />
      </div>
    </div>
  );
}

/**
 * The at-a-glance banner.
 *
 * The health colour comes straight from the backend's verdict, so the headline
 * a user sees can never disagree with the assessment underneath it.
 */
function HealthHeader({ summary }: { summary: DashboardSummary }) {
  const meta = HEALTH_META[summary.health];

  return (
    <section
      className={cn(
        "relative overflow-hidden rounded-2xl border bg-surface p-6 shadow-card",
        summary.health === "critical" ? "border-critical/30" : "border-line",
      )}
    >
      <span
        className={cn("absolute inset-x-0 top-0 h-1", meta.dot)}
        aria-hidden
      />

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2.5">
            <HealthBadge status={summary.health} />
            {summary.latest_drift ? (
              <VerdictBadge verdict={summary.latest_drift.verdict} />
            ) : null}
          </div>

          <h1 className="mt-3 text-2xl font-semibold tracking-tight text-content">
            {summary.health === "critical"
              ? "Retrieval quality has regressed"
              : summary.health === "unknown"
                ? "Retrieval health is not yet established"
                : "Retrieval quality is holding"}
          </h1>

          <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-content-muted">
            {summary.latest_drift?.summary ?? meta.hint}
          </p>

          {summary.latest_drift?.diagnostics ? (
            <div className="mt-3 max-w-2xl">
              <LeadingHypothesis report={summary.latest_drift.diagnostics} />
            </div>
          ) : null}
        </div>

        <div className="flex shrink-0 flex-col items-end gap-2">
          <RunEvaluationButton size="lg" />
          {summary.last_run_at ? (
            <p className="text-xs text-content-subtle">
              Last run {formatRelative(summary.last_run_at)}
            </p>
          ) : null}
        </div>
      </div>

      {summary.latest_drift ? (
        <Link
          to={`/drift?run=${summary.latest_drift.run_id}`}
          className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-brand transition-transform duration-150 hover:gap-1.5"
        >
          View the full statistical assessment
          <ArrowRight className="h-3.5 w-3.5" aria-hidden />
        </Link>
      ) : null}
    </section>
  );
}

function LatestAssessment({ summary }: { summary: DashboardSummary }) {
  const drift = summary.latest_drift;

  return (
    <Card className="lg:col-span-2">
      <CardHeader
        title="Most recent assessment"
        description={
          drift
            ? `Compared against ${drift.baseline_run_ids.length} earlier run${drift.baseline_run_ids.length === 1 ? "" : "s"}`
            : "No comparison has been made yet"
        }
        action={
          <Link
            to="/drift"
            className="text-xs font-medium text-brand hover:underline"
          >
            All events
          </Link>
        }
      />
      <CardBody>
        {drift ? (
          <div className="space-y-3">
            <p className="text-sm leading-relaxed text-content">{drift.summary}</p>
            <dl className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
              <Fact label="Queries" value={formatInteger(drift.query_count)} />
              <Fact
                label="Confidence"
                value={`${(drift.config.confidence_level * 100).toFixed(0)}%`}
              />
              <Fact
                label="Resamples"
                value={formatInteger(drift.config.resamples)}
              />
              <Fact
                label="Baseline"
                value={`${drift.baseline_run_ids.length} run${drift.baseline_run_ids.length === 1 ? "" : "s"}`}
              />
            </dl>
          </div>
        ) : (
          <EmptyState
            icon={FileSearch}
            title="Nothing to compare against yet"
            description="A second evaluation of the same golden set is needed before drift can be assessed."
            className="py-8"
          />
        )}
      </CardBody>
    </Card>
  );
}

function RunFacts({ summary }: { summary: DashboardSummary }) {
  const run = summary.latest_run;

  return (
    <Card>
      <CardHeader title="Index" description="What the last run scored against" />
      <CardBody className="space-y-3">
        <IconFact
          icon={Database}
          label="Documents indexed"
          value={
            summary.document_count === null
              ? "—"
              : formatInteger(summary.document_count)
          }
        />
        <IconFact
          icon={Layers}
          label="Embedding model"
          value={run?.store.embedding_model ?? "—"}
          mono
        />
        <IconFact
          icon={Gauge}
          label="Golden set"
          value={
            run ? `${run.golden_set.name} v${run.golden_set.version}` : "—"
          }
        />
        <IconFact
          icon={Timer}
          label="Run duration"
          value={run ? formatDuration(run.duration_ms) : "—"}
        />
        {run ? (
          <p className="border-t border-line pt-3 font-mono text-2xs text-content-subtle">
            run {shortId(run.run_id)} · fingerprint {run.golden_set.fingerprint}
          </p>
        ) : null}
      </CardBody>
    </Card>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-surface-muted px-3 py-2">
      <dt className="text-2xs uppercase tracking-wide text-content-subtle">
        {label}
      </dt>
      <dd className="tnum mt-0.5 text-sm font-medium text-content">{value}</dd>
    </div>
  );
}

function IconFact({
  icon: Icon,
  label,
  value,
  mono,
}: {
  icon: typeof Database;
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-start gap-3">
      <span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-surface-muted">
        <Icon className="h-3.5 w-3.5 text-content-subtle" aria-hidden />
      </span>
      <div className="min-w-0">
        <p className="text-2xs uppercase tracking-wide text-content-subtle">
          {label}
        </p>
        <p
          className={cn(
            "truncate text-sm font-medium text-content",
            mono && "font-mono text-xs",
          )}
          title={value}
        >
          {value}
        </p>
      </div>
    </div>
  );
}

/** The very first screen a new installation shows. */
function FirstRunState() {
  return (
    <Card className="mx-auto max-w-2xl">
      <EmptyState
        icon={Rocket}
        title="Run your first evaluation"
        description={
          <>
            The demo corpus and golden set are already indexed. Running an
            evaluation scores every golden query against the vector store and
            records the result. Drift detection needs a second run to compare
            against, so run it twice to see the whole flow.
          </>
        }
        action={<RunEvaluationButton size="lg" />}
      />
    </Card>
  );
}

