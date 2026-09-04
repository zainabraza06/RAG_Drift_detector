/**
 * Frontend smoke and behaviour tests.
 *
 * Two jobs. The first is to prove the component tree actually mounts, which a
 * type-check cannot tell you. The second is to protect the one thing in this
 * UI that is a *design* commitment rather than a rendering detail: heuristic
 * diagnostics must never be presented with the authority of the statistical
 * verdict they sit beside.
 */

import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DiagnosticsPanel } from "@/components/DiagnosticsPanel";
import { DriftAssessmentCard } from "@/components/DriftAssessmentCard";
import { HealthBadge } from "@/components/HealthBadge";
import { StatCard } from "@/components/StatCard";
import { EmptyState } from "@/components/states/EmptyState";
import { ErrorState } from "@/components/states/ErrorState";
import { ApiError } from "@/lib/api";
import { formatDelta, formatInterval, formatMetric, formatPValue } from "@/lib/format";
import { renderWithProviders } from "@/test/render";
import { assessment, comparison, diagnostics } from "@/test/fixtures";
import { Radar } from "lucide-react";

// ----------------------------------------------------------------------
// The framing boundary, carried into the UI
// ----------------------------------------------------------------------
describe("diagnostics framing", () => {
  it("tells the reader these are heuristics before showing any hypothesis", () => {
    renderWithProviders(<DiagnosticsPanel report={diagnostics()} />);

    const notice = screen.getByText(/heuristics, not statistical findings/i);
    expect(notice).toBeInTheDocument();

    // The notice must precede the findings in document order; a disclaimer
    // below the conclusions is read after they have already landed.
    const firstFinding = screen.getByText(/Expected documents missing/i);
    expect(
      notice.compareDocumentPosition(firstFinding) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("renders evidence strength as a word, never a number or a bar", () => {
    const { container } = renderWithProviders(
      <DiagnosticsPanel report={diagnostics()} />,
    );

    expect(screen.getByText("Direct")).toBeInTheDocument();
    expect(screen.getByText("Circumstantial")).toBeInTheDocument();

    // A progress bar or a percentage next to "direct" would reintroduce the
    // numeric confidence the backend deliberately refuses to produce.
    expect(container.querySelector("progress")).toBeNull();
    expect(container.querySelector('[role="progressbar"]')).toBeNull();
    expect(container.textContent).not.toMatch(/\d+%\s*(confident|likely|probability)/i);
  });

  it("shows coverage as a plain count of affected queries", () => {
    renderWithProviders(<DiagnosticsPanel report={diagnostics()} />);
    expect(screen.getByText(/accounts for 5 of 5/i)).toBeInTheDocument();
  });

  it("omits coverage entirely for a finding that cannot count", () => {
    renderWithProviders(<DiagnosticsPanel report={diagnostics()} />);
    // The corpus-size finding has explains: null and must not invent a figure.
    const findings = screen.getAllByRole("listitem");
    const corpus = findings.find((item) =>
      item.textContent?.includes("Indexed document count"),
    );
    expect(corpus).toBeDefined();
    expect(within(corpus as HTMLElement).queryByText(/accounts for/i)).toBeNull();
  });

  it("separates ruled out from could-not-check", () => {
    renderWithProviders(
      <DiagnosticsPanel
        report={diagnostics({
          checks_skipped: { missing_expected_documents: "store unreachable" },
          checks_passed: ["embedding_model_changed"],
        })}
      />,
    );

    // Collapsing these would overstate what the tool knows.
    expect(screen.getByText(/ruled out/i)).toBeInTheDocument();
    expect(screen.getByText(/could not check/i)).toBeInTheDocument();
    expect(screen.getByText(/store unreachable/i)).toBeInTheDocument();
  });

  it("handles a report with no findings without breaking", () => {
    renderWithProviders(<DiagnosticsPanel report={diagnostics({ findings: [] })} />);
    expect(screen.getByText(/not one of the patterns/i)).toBeInTheDocument();
  });
});

// ----------------------------------------------------------------------
// The statistical half
// ----------------------------------------------------------------------
describe("drift assessment", () => {
  it("shows every metric with its interval and p-value", () => {
    renderWithProviders(<DriftAssessmentCard assessment={assessment()} />);

    expect(screen.getByText(/\[−0\.362, −0\.086\]/)).toBeInTheDocument();
    expect(screen.getByText("0.0089")).toBeInTheDocument();
    expect(screen.getAllByText(/primary/i).length).toBeGreaterThan(0);
  });

  it("marks the pre-specified primary metric", () => {
    renderWithProviders(<DriftAssessmentCard assessment={assessment()} />);
    expect(screen.getByText(/decided on NDCG@5/i)).toBeInTheDocument();
  });

  it("distinguishes significant from material", () => {
    renderWithProviders(
      <DriftAssessmentCard
        assessment={assessment({
          comparisons: [
            comparison({ significant: true, material: false, difference: -0.002 }),
          ],
        })}
      />,
    );
    // A change can be real and irrelevant; the UI must not merge the two.
    expect(screen.getByText(/below threshold/i)).toBeInTheDocument();
  });

  it("explains why a small number of discordant pairs cannot reach significance", () => {
    renderWithProviders(<DriftAssessmentCard assessment={assessment()} />);
    expect(screen.getByText(/McNemar exact/i)).toBeInTheDocument();
    expect(screen.getByText(/too few to reach significance/i)).toBeInTheDocument();
  });

  it("states the method and the seed so a verdict is reproducible", () => {
    renderWithProviders(<DriftAssessmentCard assessment={assessment()} />);
    expect(screen.getByText(/Paired bootstrap over 30 queries/i)).toBeInTheDocument();
    expect(screen.getByText(/Seed 20240517/i)).toBeInTheDocument();
  });

  it("renders warnings when the assessment carries caveats", () => {
    renderWithProviders(
      <DriftAssessmentCard
        assessment={assessment({ warnings: ["Golden set has 15 queries"] })}
      />,
    );
    expect(screen.getByText(/Golden set has 15 queries/)).toBeInTheDocument();
  });
});

// ----------------------------------------------------------------------
// Health
// ----------------------------------------------------------------------
describe("health status", () => {
  it("does not present an unestablished system as healthy", () => {
    renderWithProviders(<HealthBadge status="unknown" />);
    const badge = screen.getByText("Not established");
    // Green would be a claim the data does not support.
    expect(badge.className).not.toMatch(/healthy/);
  });

  it.each([
    ["healthy", "Healthy"],
    ["warning", "Caution"],
    ["critical", "Regression"],
  ] as const)("renders %s as %s", (status, label) => {
    renderWithProviders(<HealthBadge status={status} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });
});

// ----------------------------------------------------------------------
// Stat cards and states
// ----------------------------------------------------------------------
describe("stat card", () => {
  it("shows a delta in points and names the comparison", () => {
    renderWithProviders(
      <StatCard label="NDCG@5" value={0.765} delta={-0.193} primary />,
    );
    expect(screen.getByText("0.765")).toBeInTheDocument();
    expect(screen.getByText(/19\.3 pts/)).toBeInTheDocument();
    expect(screen.getByText(/vs previous/)).toBeInTheDocument();
  });

  it("says so plainly when there is nothing to compare against", () => {
    renderWithProviders(<StatCard label="NDCG@5" value={0.9} delta={null} />);
    expect(screen.getByText(/No comparable prior run/i)).toBeInTheDocument();
  });

  it("renders an em dash rather than NaN for a missing value", () => {
    renderWithProviders(<StatCard label="NDCG@5" value={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});

describe("states", () => {
  it("empty states explain what to do next", () => {
    renderWithProviders(
      <EmptyState
        icon={Radar}
        title="No assessments yet"
        description="Run an evaluation to get started."
      />,
    );
    expect(screen.getByText("No assessments yet")).toBeInTheDocument();
    expect(screen.getByText(/Run an evaluation/)).toBeInTheDocument();
  });

  it("error states use the API code rather than dumping an exception", () => {
    renderWithProviders(
      <ErrorState
        error={new ApiError(503, "vector_store_unavailable", "Chroma is unreachable.")}
      />,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/vector store is unavailable/i)).toBeInTheDocument();
    expect(screen.getByText("Chroma is unreachable.")).toBeInTheDocument();
  });

  it("offers retry only when retrying could help", () => {
    const { rerender } = renderWithProviders(
      <ErrorState error={new ApiError(503, "x", "down")} onRetry={() => {}} />,
    );
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();

    rerender(
      <ErrorState
        error={new ApiError(404, "run_not_found", "no such run")}
        onRetry={() => {}}
      />,
    );
    // Retrying a 404 will not make the run exist.
    expect(screen.queryByRole("button", { name: /try again/i })).toBeNull();
  });

  it("surfaces field-level validation detail", () => {
    renderWithProviders(
      <ErrorState
        error={
          new ApiError(422, "validation_error", "Invalid payload", [
            { field: "queries", message: "must not be empty" },
          ])
        }
      />,
    );
    expect(screen.getByText("queries")).toBeInTheDocument();
    expect(screen.getByText("must not be empty")).toBeInTheDocument();
  });
});

// ----------------------------------------------------------------------
// Formatting
// ----------------------------------------------------------------------
describe("formatting", () => {
  it("formats metrics to three decimals", () => {
    expect(formatMetric(0.9333333)).toBe("0.933");
    expect(formatMetric(null)).toBe("—");
  });

  it("expresses deltas in points, not percent", () => {
    // "4.2%" is ambiguous between an absolute and a relative change.
    expect(formatDelta(-0.042)).toBe("−4.2 pts");
    expect(formatDelta(0.017)).toBe("+1.7 pts");
    expect(formatDelta(0.00001)).toBe("no change");
  });

  it("formats intervals with explicit signs on both bounds", () => {
    expect(formatInterval(-0.362, -0.086)).toBe("[−0.362, −0.086]");
    expect(formatInterval(-0.01, 0.05)).toBe("[−0.010, +0.050]");
  });

  it("reports a p-value below the Monte Carlo floor as a bound", () => {
    expect(formatPValue(0.00001)).toBe("p < 0.0001");
    expect(formatPValue(0.0436)).toBe("p = 0.0436");
  });
});
