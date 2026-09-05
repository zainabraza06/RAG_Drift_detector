import { LineChart } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { MetricTrendChart } from "@/components/MetricTrendChart";
import { RunEvaluationButton } from "@/components/RunEvaluationButton";
import { EmptyState } from "@/components/states/EmptyState";
import { ErrorState } from "@/components/states/ErrorState";
import { ChartSkeleton } from "@/components/states/LoadingState";
import { Card } from "@/components/ui/Card";
import { Select } from "@/components/ui/Select";
import { useCutoffs, useDriftEvents, useTrends } from "@/lib/queries";
import type { DriftVerdict } from "@/lib/types";
import { METRIC_NAMES } from "@/lib/types";

const HISTORY_OPTIONS = [20, 50, 100, 200];

export function TrendsPage() {
  const navigate = useNavigate();
  const cutoffs = useCutoffs();
  const [selectedK, setSelectedK] = useState<number | null>(null);
  const [limit, setLimit] = useState(50);

  // Default to the cutoff the drift verdict is decided on, which is the one a
  // reader is most likely to want first.
  const k = selectedK ?? cutoffs.data?.find((value) => value === 5) ?? cutoffs.data?.[0] ?? 5;

  const trends = useTrends(k, limit);
  const events = useDriftEvents();

  const verdicts = useMemo(() => {
    const map = new Map<string, DriftVerdict>();
    for (const event of events.data?.items ?? []) map.set(event.run_id, event.verdict);
    return map;
  }, [events.data]);

  if (trends.isPending || cutoffs.isPending) {
    return (
      <div className="space-y-6">
        <PageHeading />
        <div className="grid gap-4 xl:grid-cols-2">
          {[0, 1, 2, 3].map((index) => (
            <ChartSkeleton key={index} />
          ))}
        </div>
      </div>
    );
  }

  if (trends.isError) {
    return <ErrorState error={trends.error} onRetry={() => void trends.refetch()} />;
  }

  const hasPoints = trends.data.some((series) => series.points.length > 0);
  const pointCount = trends.data[0]?.points.length ?? 0;
  const regressionCount = trends.data[0]?.points.filter(
    (point) => verdicts.get(point.run_id) === "degraded",
  ).length;

  return (
    <div className="space-y-6">
      <PageHeading
        controls={
          hasPoints ? (
            <div className="flex flex-wrap items-center gap-2">
              <Select
                label="Cutoff"
                value={k}
                onChange={(event) => setSelectedK(Number(event.target.value))}
              >
                {(cutoffs.data ?? [k]).map((value) => (
                  <option key={value} value={value}>
                    k = {value}
                  </option>
                ))}
              </Select>
              <Select
                label="History"
                value={limit}
                onChange={(event) => setLimit(Number(event.target.value))}
              >
                {HISTORY_OPTIONS.map((value) => (
                  <option key={value} value={value}>
                    last {value}
                  </option>
                ))}
              </Select>
            </div>
          ) : null
        }
      />

      {hasPoints ? (
        <>
          <p className="text-small text-ink-secondary">
            Showing {pointCount} run{pointCount === 1 ? "" : "s"} at k={k}.
            {regressionCount ? (
              <>
                {" "}
                <span className="inline-flex items-center gap-1.5">
                  <span
                    className="inline-block h-1.5 w-1.5 rounded-full bg-danger"
                    aria-hidden
                  />
                  {regressionCount} marked regression
                  {regressionCount === 1 ? "" : "s"} — click a marker to open its
                  assessment.
                </span>
              </>
            ) : (
              " No regressions detected in this window."
            )}
          </p>

          <div className="grid gap-4 xl:grid-cols-2">
            {METRIC_NAMES.map((metric) => {
              const series = trends.data.find((item) => item.metric === metric);
              if (!series) return null;
              return (
                <MetricTrendChart
                  key={metric}
                  metric={metric}
                  k={k}
                  series={series}
                  verdicts={verdicts}
                  onSelectRun={(runId) => navigate(`/drift?run=${runId}`)}
                />
              );
            })}
          </div>
        </>
      ) : (
        <Card>
          <EmptyState
            icon={LineChart}
            title="No history to plot yet"
            description="Trends need at least one recorded evaluation. Run one, then run it again after changing your index to see the line move."
            action={<RunEvaluationButton />}
          />
        </Card>
      )}
    </div>
  );
}

function PageHeading({ controls }: { controls?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-title text-ink">Metric trends</h1>
        <p className="mt-1.5 max-w-prose text-body text-ink-secondary">
          Retrieval quality over time, with detected regressions marked in place.
        </p>
      </div>
      {controls}
    </div>
  );
}
