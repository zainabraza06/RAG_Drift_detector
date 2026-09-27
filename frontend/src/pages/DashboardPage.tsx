import {
  ArrowRight,
  Database,
  FileSearch,
  Layers,
  Rocket,
  Target,
  Timer,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";

import { DemoPanel } from "@/components/DemoPanel";
import { LeadingHypothesis } from "@/components/DiagnosticsPanel";
import { VerdictBadge } from "@/components/DriftAssessmentCard";
import { HealthBadge } from "@/components/HealthBadge";
import { RunEvaluationButton } from "@/components/RunEvaluationButton";
import { StatCard } from "@/components/StatCard";
import { EmptyState } from "@/components/states/EmptyState";
import { ErrorState } from "@/components/states/ErrorState";
import { StatCardsSkeleton } from "@/components/states/LoadingState";
import { Code } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader, SectionHeading } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/lib/cn";
import { HEALTH_META } from "@/lib/display";
import { formatDuration, formatInteger, formatRelative, shortId } from "@/lib/format";
import { useDashboard } from "@/lib/queries";
import type { DashboardSummary } from "@/lib/types";
import { METRIC_DESCRIPTIONS, METRIC_LABELS, METRIC_NAMES } from "@/lib/types";

export function DashboardPage() {
  const { data, isPending, isError, error, refetch } = useDashboard();

  if (isPending) {
    return (
      <div className="space-y-8">
        <Skeleton className="h-[168px] w-full rounded-lg" />
        <StatCardsSkeleton />
      </div>
    );
  }

  if (isError) return <ErrorState error={error} onRetry={() => void refetch()} />;
  if (!data.has_runs) return <FirstRunState />;

  return (
    <div className="space-y-8">
      <StatusPanel summary={data} />
      <DemoPanel />

      <section>
        <SectionHeading>Latest metrics · k={data.latest_run?.primary_k}</SectionHeading>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {METRIC_NAMES.map((metric) => {
            // Prefer the drift assessment's own comparison: it measures
            // against the same multi-run baseline the verdict used, so these
            // cards cannot contradict the headline above them.
            const comparison = data.latest_drift?.comparisons.find(
              (item) => item.metric === metric,
            );
            return (
              <StatCard
                key={metric}
                label={
                  METRIC_LABELS[metric] +
                  (metric === "mrr" ? "" : `@${data.latest_run?.primary_k}`)
                }
                value={data.primary_metrics?.[metric] ?? null}
                delta={comparison?.difference ?? data.metric_deltas[metric] ?? null}
                comparedTo={comparison ? "baseline" : "previous"}
                hint={METRIC_DESCRIPTIONS[metric]}
                primary={data.latest_drift?.config.primary_metric === metric}
              />
            );
          })}
        </div>
      </section>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <LatestAssessment summary={data} />
        <IndexPanel summary={data} />
      </div>
    </div>
  );
}

/**
 * The at-a-glance panel.
 *
 * Health colour comes straight from the backend verdict, so the headline can
 * never disagree with the assessment beneath it. Colour appears only in the
 * status chip and a single hairline rule — the panel itself stays neutral, so
 * a regression reads as serious rather than as decoration.
 */
function StatusPanel({ summary }: { summary: DashboardSummary }) {
  const meta = HEALTH_META[summary.health];

  return (
    <section className="overflow-hidden rounded-lg border border-line bg-surface shadow-xs">
      <span className={cn("block h-0.5 w-full", meta.solid)} aria-hidden />

      {/* Stacks below sm: side by side, the action squeezes the summary into a
          column too narrow to read. */}
      <div className="flex flex-col gap-5 px-5 py-5 sm:flex-row sm:items-start sm:justify-between sm:gap-6 sm:px-6">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <HealthBadge status={summary.health} />
            {summary.latest_drift ? (
              <VerdictBadge verdict={summary.latest_drift.verdict} />
            ) : null}
            {summary.last_run_at ? (
              <span className="text-small text-ink-tertiary">
                {formatRelative(summary.last_run_at)}
              </span>
            ) : null}
          </div>

          <h1 className="mt-3 text-title text-ink">
            {summary.health === "critical"
              ? "Retrieval quality has regressed"
              : summary.health === "unknown"
                ? "Retrieval health is not yet established"
                : "Retrieval quality is holding"}
          </h1>

          <p className="mt-1.5 max-w-prose text-body text-ink-secondary">
            {summary.latest_drift?.summary ?? meta.hint}
          </p>

          {summary.latest_drift?.diagnostics ? (
            <div className="mt-4 border-t border-line-subtle pt-4">
              <LeadingHypothesis report={summary.latest_drift.diagnostics} />
            </div>
          ) : null}

          {summary.latest_drift ? (
            <Link
              to={`/drift?run=${summary.latest_drift.run_id}`}
              className="mt-4 inline-flex items-center gap-1.5 text-small font-medium text-accent-text transition-colors duration-fast hover:text-accent"
            >
              View the full statistical assessment
              <ArrowRight className="h-3.5 w-3.5" aria-hidden />
            </Link>
          ) : null}
        </div>

        <RunEvaluationButton size="lg" className="w-full sm:w-auto" />
      </div>
    </section>
  );
}

function LatestAssessment({ summary }: { summary: DashboardSummary }) {
  const drift = summary.latest_drift;

  return (
    <Card>
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
            className="text-small font-medium text-accent-text hover:text-accent"
          >
            All events
          </Link>
        }
      />
      <CardBody>
        {drift ? (
          <div className="space-y-4">
            <p className="max-w-prose text-body text-ink-secondary">{drift.summary}</p>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-4 border-t border-line-subtle pt-4 sm:grid-cols-4">
              <Fact label="Queries" value={formatInteger(drift.query_count)} />
              <Fact
                label="Confidence"
                value={`${(drift.config.confidence_level * 100).toFixed(0)}%`}
              />
              <Fact label="Resamples" value={formatInteger(drift.config.resamples)} />
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
            className="py-10"
          />
        )}
      </CardBody>
    </Card>
  );
}

function IndexPanel({ summary }: { summary: DashboardSummary }) {
  const run = summary.latest_run;

  return (
    <Card>
      <CardHeader title="Index" description="What the last run scored against" />
      <CardBody className="space-y-4">
        <IconFact
          icon={Database}
          label="Documents indexed"
          value={
            summary.document_count === null ? "—" : formatInteger(summary.document_count)
          }
        />
        <IconFact
          icon={Layers}
          label="Embedding model"
          value={run?.store.embedding_model ?? "—"}
          mono
        />
        <IconFact
          icon={Target}
          label="Golden set"
          value={run ? `${run.golden_set.name} v${run.golden_set.version}` : "—"}
        />
        <IconFact
          icon={Timer}
          label="Run duration"
          value={run ? formatDuration(run.duration_ms) : "—"}
        />
        {run ? (
          <div className="flex flex-wrap items-center gap-1.5 border-t border-line-subtle pt-4">
            <Code>{shortId(run.run_id)}</Code>
            <Code>{run.golden_set.fingerprint}</Code>
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-micro uppercase text-ink-tertiary">{label}</dt>
      <dd className="tnum mt-1 text-body font-medium text-ink">{value}</dd>
    </div>
  );
}

function IconFact({
  icon: Icon,
  label,
  value,
  mono,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-start gap-3">
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-ink-tertiary" aria-hidden />
      <div className="min-w-0">
        <p className="text-micro uppercase text-ink-tertiary">{label}</p>
        <p
          className={cn(
            "mt-0.5 truncate text-body font-medium text-ink",
            mono && "font-mono text-small",
          )}
          title={value}
        >
          {value}
        </p>
      </div>
    </div>
  );
}

/** The first screen a new installation shows. */
function FirstRunState() {
  return (
    <Card className="mx-auto max-w-xl">
      <EmptyState
        icon={Rocket}
        title="Run your first evaluation"
        description="The demo corpus and golden set are already indexed. An evaluation scores every golden query against the vector store and records the result. Drift detection needs a second run to compare against, so run it twice to see the whole flow."
        action={<RunEvaluationButton size="lg" />}
      />
    </Card>
  );
}
