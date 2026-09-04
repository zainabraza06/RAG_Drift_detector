import { Check, FlaskConical, Lightbulb, MinusCircle, Search } from "lucide-react";

import { cn } from "@/lib/cn";
import { RULE_LABELS, STRENGTH_META } from "@/lib/display";
import type { DiagnosticFinding, DiagnosticReport } from "@/lib/types";

export function DiagnosticsPanel({ report }: { report: DiagnosticReport }) {
  return (
    <section className="space-y-4">
      <HeuristicNotice />

      {report.findings.length > 0 ? (
        <ol className="space-y-3">
          {report.findings.map((finding, index) => (
            <FindingCard key={finding.rule_id} finding={finding} rank={index + 1} />
          ))}
        </ol>
      ) : (
        <p className="rounded-lg border border-line bg-surface-muted px-4 py-3 text-sm text-content-muted">
          No heuristic found anything to point at. The regression is real, but its
          cause is not one of the patterns this tool knows how to recognise.
        </p>
      )}

      <ChecksSummary report={report} />
    </section>
  );
}

/**
 * The framing, carried into the UI.
 *
 * The backend ships `basis: "heuristic"` and a disclaimer on every report
 * precisely so this cannot be forgotten at render time. Placing it above the
 * findings, not below them, means it is read before the hypotheses are.
 */
function HeuristicNotice() {
  return (
    <div className="flex gap-3 rounded-lg border border-brand/25 bg-brand-soft/60 px-4 py-3">
      <FlaskConical className="mt-0.5 h-4 w-4 shrink-0 text-brand" aria-hidden />
      <div className="text-xs leading-relaxed">
        <p className="font-semibold text-content">
          These are heuristics, not statistical findings
        </p>
        <p className="mt-1 text-content-muted">
          The verdict above was produced by a hypothesis test with a stated
          confidence interval. What follows was not. These checks report facts that
          changed alongside the regression, ranked by how directly each one links to
          the queries that broke. They do not establish causation.
        </p>
      </div>
    </div>
  );
}

function FindingCard({ finding, rank }: { finding: DiagnosticFinding; rank: number }) {
  const meta = STRENGTH_META[finding.strength];
  const hasCoverage = finding.explains !== null && Boolean(finding.out_of);

  return (
    <li className="relative overflow-hidden rounded-xl border border-line bg-surface shadow-card transition-[border-color,box-shadow] duration-200 hover:border-line-strong hover:shadow-raised">
      <span className={cn("absolute inset-y-0 left-0 w-1", meta.rail)} aria-hidden />

      <div className="py-4 pl-5 pr-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="grid h-5 w-5 place-items-center rounded-full bg-surface-muted text-2xs font-semibold text-content-muted">
            {rank}
          </span>
          <h4 className="text-sm font-semibold text-content">{finding.title}</h4>
          <span
            title={meta.explanation}
            className={cn(
              "rounded-md px-1.5 py-0.5 text-2xs font-medium uppercase tracking-wide ring-1 ring-inset",
              meta.chip,
            )}
          >
            {meta.label}
          </span>
          {hasCoverage ? (
            <span
              title="A count of the queries that actually broke and reference this finding. Arithmetic over observed data, not an estimate."
              className="tnum rounded-md bg-surface-muted px-1.5 py-0.5 text-2xs font-medium text-content-muted"
            >
              accounts for {finding.explains} of {finding.out_of}
            </span>
          ) : null}
        </div>

        <p className="mt-2 text-sm leading-relaxed text-content-muted">
          {finding.summary}
        </p>

        <EvidenceList finding={finding} />

        {finding.suggested_action ? (
          <p className="mt-3 flex gap-2 rounded-lg bg-surface-muted px-3 py-2 text-xs leading-relaxed text-content-muted">
            <Lightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand" aria-hidden />
            {finding.suggested_action}
          </p>
        ) : null}
      </div>
    </li>
  );
}

/** Concrete ids a human can go and look at, rendered as chips. */
function EvidenceList({ finding }: { finding: DiagnosticFinding }) {
  const lists = Object.entries(finding.evidence).filter(
    (entry): entry is [string, string[]] =>
      Array.isArray(entry[1]) && entry[1].length > 0,
  );
  if (lists.length === 0) return null;

  return (
    <dl className="mt-3 space-y-2">
      {lists.map(([key, values]) => (
        <div key={key}>
          <dt className="text-2xs font-medium uppercase tracking-wide text-content-subtle">
            {key.replace(/_/g, " ")}
          </dt>
          <dd className="mt-1 flex flex-wrap gap-1">
            {values.slice(0, 8).map((value) => (
              <code
                key={value}
                className="rounded bg-surface-muted px-1.5 py-0.5 font-mono text-2xs text-content-muted"
              >
                {value}
              </code>
            ))}
            {values.length > 8 ? (
              <span className="self-center text-2xs text-content-subtle">
                +{values.length - 8} more
              </span>
            ) : null}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * Ruled out and could-not-check are shown separately.
 *
 * Collapsing them would overstate what the tool knows: "we checked and it is
 * fine" and "we could not check" are different claims.
 */
function ChecksSummary({ report }: { report: DiagnosticReport }) {
  const skipped = Object.entries(report.checks_skipped);
  if (report.checks_passed.length === 0 && skipped.length === 0) return null;

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {report.checks_passed.length > 0 ? (
        <div className="rounded-lg border border-line bg-surface-muted px-4 py-3">
          <h5 className="flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wide text-content-muted">
            <Check className="h-3 w-3 text-healthy" aria-hidden />
            Ruled out
          </h5>
          <ul className="mt-2 space-y-1">
            {report.checks_passed.map((rule) => (
              <li key={rule} className="text-xs text-content-muted">
                {RULE_LABELS[rule] ?? rule}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {skipped.length > 0 ? (
        <div className="rounded-lg border border-line bg-surface-muted px-4 py-3">
          <h5 className="flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wide text-content-muted">
            <MinusCircle className="h-3 w-3 text-content-subtle" aria-hidden />
            Could not check
          </h5>
          <ul className="mt-2 space-y-1">
            {skipped.map(([rule, reason]) => (
              <li key={rule} className="text-xs text-content-muted">
                {RULE_LABELS[rule] ?? rule}
                <span className="text-content-subtle"> — {reason}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

/** Compact single-line hint used on the dashboard. */
export function LeadingHypothesis({ report }: { report: DiagnosticReport }) {
  const finding = report.findings[0];
  if (!finding) return null;

  return (
    <p className="flex items-start gap-2 text-xs leading-relaxed text-content-muted">
      <Search className="mt-0.5 h-3.5 w-3.5 shrink-0 text-content-subtle" aria-hidden />
      <span>
        <span className="font-medium text-content">Likely cause (heuristic): </span>
        {finding.summary}
      </span>
    </p>
  );
}
