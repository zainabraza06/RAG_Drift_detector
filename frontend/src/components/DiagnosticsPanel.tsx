import { Check, FlaskConical, Lightbulb, MinusCircle, Search } from "lucide-react";

import { Badge, Code } from "@/components/ui/Badge";
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
        <p className="max-w-prose rounded-md border border-line-subtle bg-inset px-4 py-3 text-body text-ink-secondary">
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
 * The backend ships `basis: "heuristic"` and a disclaimer on every report so
 * this cannot be forgotten at render time. It sits above the findings, not
 * below: a caveat printed after the conclusions is read once they have already
 * landed.
 */
function HeuristicNotice() {
  return (
    <div className="flex gap-3 rounded-md border border-line bg-inset px-4 py-3">
      <FlaskConical className="mt-0.5 h-4 w-4 shrink-0 text-ink-tertiary" aria-hidden />
      <div className="max-w-prose">
        <p className="text-subheading text-ink">
          Heuristics, not statistical findings
        </p>
        <p className="mt-1 text-small leading-5 text-ink-secondary">
          The verdict above came from a hypothesis test with a stated confidence
          interval. What follows did not. These checks report facts that changed
          alongside the regression, ranked by how directly each links to the queries
          that broke. They do not establish causation.
        </p>
      </div>
    </div>
  );
}

function FindingCard({ finding, rank }: { finding: DiagnosticFinding; rank: number }) {
  const meta = STRENGTH_META[finding.strength];
  const hasCoverage = finding.explains !== null && Boolean(finding.out_of);

  return (
    <li className="relative overflow-hidden rounded-lg border border-line bg-surface shadow-xs transition-colors duration-fast ease-out hover:border-line-strong">
      {/* A 2px rail carries the strength without tinting the whole card. */}
      <span className={cn("absolute inset-y-0 left-0 w-0.5", meta.rail)} aria-hidden />

      <div className="py-4 pl-5 pr-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="tnum text-label text-ink-disabled">{rank}</span>
          <h4 className="text-subheading text-ink">{finding.title}</h4>
          <span title={meta.explanation}>
            <Badge tone={meta.tone}>{meta.label}</Badge>
          </span>
          {hasCoverage ? (
            <span
              title="A count of the queries that actually broke and reference this finding. Arithmetic over observed data, not an estimate."
              className="tnum text-label text-ink-tertiary"
            >
              accounts for {finding.explains} of {finding.out_of}
            </span>
          ) : null}
        </div>

        <p className="mt-2 max-w-prose text-body text-ink-secondary">
          {finding.summary}
        </p>

        <EvidenceList finding={finding} />

        {finding.suggested_action ? (
          <p className="mt-4 flex max-w-prose gap-2 border-t border-line-subtle pt-3 text-small leading-5 text-ink-secondary">
            <Lightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-tertiary" aria-hidden />
            {finding.suggested_action}
          </p>
        ) : null}
      </div>
    </li>
  );
}

/** Concrete ids a human can go and look at. */
function EvidenceList({ finding }: { finding: DiagnosticFinding }) {
  const lists = Object.entries(finding.evidence).filter(
    (entry): entry is [string, string[]] =>
      Array.isArray(entry[1]) && entry[1].length > 0,
  );
  if (lists.length === 0) return null;

  return (
    <dl className="mt-4 space-y-3">
      {lists.map(([key, values]) => (
        <div key={key}>
          <dt className="text-micro uppercase text-ink-tertiary">
            {key.replace(/_/g, " ")}
          </dt>
          <dd className="mt-1.5 flex flex-wrap gap-1.5">
            {values.slice(0, 8).map((value) => (
              <Code key={value}>{value}</Code>
            ))}
            {values.length > 8 ? (
              <span className="self-center text-label text-ink-tertiary">
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
 * Ruled out and could-not-check are shown separately, because collapsing them
 * would overstate what the tool knows: "we checked and it is fine" and "we
 * could not check" are different claims.
 */
function ChecksSummary({ report }: { report: DiagnosticReport }) {
  const skipped = Object.entries(report.checks_skipped);
  if (report.checks_passed.length === 0 && skipped.length === 0) return null;

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {report.checks_passed.length > 0 ? (
        <div className="rounded-md border border-line-subtle bg-inset px-4 py-3">
          <h5 className="flex items-center gap-1.5 text-micro uppercase text-ink-tertiary">
            <Check className="h-3 w-3 text-success" aria-hidden />
            Ruled out
          </h5>
          <ul className="mt-2 space-y-1">
            {report.checks_passed.map((rule) => (
              <li key={rule} className="text-small text-ink-secondary">
                {RULE_LABELS[rule] ?? rule}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {skipped.length > 0 ? (
        <div className="rounded-md border border-line-subtle bg-inset px-4 py-3">
          <h5 className="flex items-center gap-1.5 text-micro uppercase text-ink-tertiary">
            <MinusCircle className="h-3 w-3 text-ink-disabled" aria-hidden />
            Could not check
          </h5>
          <ul className="mt-2 space-y-1">
            {skipped.map(([rule, reason]) => (
              <li key={rule} className="text-small text-ink-secondary">
                {RULE_LABELS[rule] ?? rule}
                <span className="text-ink-tertiary"> — {reason}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

/** One-line hint used on the dashboard. */
export function LeadingHypothesis({ report }: { report: DiagnosticReport }) {
  const finding = report.findings[0];
  if (!finding) return null;

  return (
    <p className="flex max-w-prose items-start gap-2 text-small leading-5 text-ink-secondary">
      <Search className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-tertiary" aria-hidden />
      <span>
        <span className="font-medium text-ink">Likely cause (heuristic): </span>
        {finding.summary}
      </span>
    </p>
  );
}
