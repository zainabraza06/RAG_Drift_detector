import {
  AlertCircle,
  Check,
  ListChecks,
  Plus,
  Save,
  Star,
  Trash2,
  Undo2,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { EmptyState } from "@/components/states/EmptyState";
import { ErrorState } from "@/components/states/ErrorState";
import { ListSkeleton } from "@/components/states/LoadingState";
import { Badge } from "@/components/ui/Badge";
import { Button, IconButton } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { useToast } from "@/components/ui/toast-context";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import {
  useActivateGoldenSet,
  useGoldenSets,
  useUpdateGoldenSet,
} from "@/lib/queries";
import type { GoldenSetInput, StoredGoldenSet } from "@/lib/types";

interface DraftDocument {
  document_id: string;
  relevance: number;
}

interface DraftQuery {
  key: string;
  query_id: string;
  query: string;
  expected_documents: DraftDocument[];
  note: string | null;
}

let keyCounter = 0;
const nextKey = () => `draft-${keyCounter++}`;

function toDraft(stored: StoredGoldenSet): DraftQuery[] {
  return stored.golden_set.queries.map((query) => ({
    key: nextKey(),
    query_id: query.query_id,
    query: query.query,
    expected_documents: query.expected_documents.map((doc) => ({ ...doc })),
    note: query.note,
  }));
}

/**
 * Validation mirrors the invariants the backend enforces.
 *
 * The server is still the authority — it re-validates and returns field-level
 * errors — but catching these here means a user is told about a duplicate id
 * while they are looking at it, rather than after a round trip.
 */
function validate(queries: DraftQuery[]): Map<string, string> {
  const errors = new Map<string, string>();
  const seenIds = new Set<string>();

  for (const query of queries) {
    if (!query.query.trim()) {
      errors.set(query.key, "Query text cannot be empty.");
      continue;
    }
    if (query.expected_documents.length === 0) {
      errors.set(query.key, "At least one expected document is required.");
      continue;
    }
    if (query.expected_documents.some((doc) => !doc.document_id.trim())) {
      errors.set(query.key, "Document ids cannot be empty.");
      continue;
    }
    const ids = query.expected_documents.map((doc) => doc.document_id.trim());
    if (new Set(ids).size !== ids.length) {
      errors.set(query.key, "The same document is listed twice for this query.");
      continue;
    }
    const queryId = query.query_id.trim();
    if (queryId) {
      if (seenIds.has(queryId)) {
        errors.set(query.key, `Query id "${queryId}" is used more than once.`);
        continue;
      }
      seenIds.add(queryId);
    }
  }
  return errors;
}

export function GoldenSetPage() {
  const { data, isPending, isError, error, refetch } = useGoldenSets();
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const sets = data?.items ?? [];
  const selected =
    sets.find((set) => set.golden_set_id === selectedId) ??
    sets.find((set) => set.is_active) ??
    sets[0];

  if (isPending) return <ListSkeleton rows={3} />;
  if (isError) return <ErrorState error={error} onRetry={() => void refetch()} />;

  if (sets.length === 0) {
    return (
      <Card>
        <EmptyState
          icon={ListChecks}
          title="No golden sets stored"
          description="A golden set defines what good retrieval looks like: queries paired with the documents that should answer them. Import one with the CLI to get started."
        />
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-title text-ink">Golden set</h1>
          <p className="mt-1.5 max-w-prose text-body text-ink-secondary">
            The ground truth every run is scored against. Editing the judgements
            changes the set's fingerprint, which deliberately stops earlier runs
            from being compared against later ones.
          </p>
        </div>

        {sets.length > 1 ? (
          <Select
            label="Set"
            value={selected?.golden_set_id}
            onChange={(event) => setSelectedId(Number(event.target.value))}
          >
            {sets.map((set) => (
              <option key={set.golden_set_id} value={set.golden_set_id}>
                {set.golden_set.name} v{set.golden_set.version}
                {set.is_active ? " (active)" : ""}
              </option>
            ))}
          </Select>
        ) : null}
      </div>

      {selected ? <GoldenSetEditor key={selected.golden_set_id} stored={selected} /> : null}
    </div>
  );
}

function GoldenSetEditor({ stored }: { stored: StoredGoldenSet }) {
  const { push } = useToast();
  const update = useUpdateGoldenSet();
  const activate = useActivateGoldenSet();

  const [queries, setQueries] = useState<DraftQuery[]>(() => toDraft(stored));
  const [pristine, setPristine] = useState<DraftQuery[]>(() => toDraft(stored));

  useEffect(() => {
    const draft = toDraft(stored);
    setQueries(draft);
    setPristine(draft);
  }, [stored]);

  const errors = useMemo(() => validate(queries), [queries]);
  const dirty = useMemo(
    () => JSON.stringify(strip(queries)) !== JSON.stringify(strip(pristine)),
    [queries, pristine],
  );

  const mutate = (updater: (current: DraftQuery[]) => DraftQuery[]) =>
    setQueries((current) => updater(current));

  const save = () => {
    const input: GoldenSetInput = {
      name: stored.golden_set.name,
      version: stored.golden_set.version,
      description: stored.golden_set.description,
      activate: stored.is_active,
      queries: queries.map((query) => ({
        query_id: query.query_id.trim() || null,
        query: query.query.trim(),
        expected_documents: query.expected_documents.map((doc) => ({
          document_id: doc.document_id.trim(),
          relevance: doc.relevance,
        })),
        note: query.note?.trim() || null,
      })),
    };

    update.mutate(
      { id: stored.golden_set_id, input },
      {
        onSuccess: (saved) => {
          push({
            tone: "success",
            title: "Golden set saved",
            description: `Fingerprint is now ${saved.golden_set.queries.length} queries. Runs from before this edit are no longer comparable.`,
          });
        },
        onError: (error) =>
          push({
            tone: "error",
            title: "Could not save",
            description:
              error instanceof ApiError
                ? error.message
                : "The golden set could not be saved.",
          }),
      },
    );
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title={
            <span className="flex items-center gap-2">
              {stored.golden_set.name}
              <span className="text-sm font-normal text-content-subtle">
                v{stored.golden_set.version}
              </span>
              {stored.is_active ? (
                <Badge tone="accent" icon={<Star className="h-3 w-3" aria-hidden />}>
                  Active
                </Badge>
              ) : null}
            </span>
          }
          description={
            stored.golden_set.description ?? `${queries.length} queries`
          }
          action={
            <div className="flex items-center gap-2">
              {!stored.is_active ? (
                <Button
                  size="sm"
                  loading={activate.isPending}
                  onClick={() =>
                    activate.mutate(stored.golden_set_id, {
                      onSuccess: () =>
                        push({
                          tone: "success",
                          title: "Golden set activated",
                          description: "New evaluations will score against this set.",
                        }),
                    })
                  }
                >
                  Make active
                </Button>
              ) : null}
              {dirty ? (
                <Button
                  size="sm"
                  icon={<Undo2 className="h-3.5 w-3.5" aria-hidden />}
                  onClick={() => setQueries(pristine)}
                >
                  Discard
                </Button>
              ) : null}
              <Button
                size="sm"
                variant="primary"
                disabled={!dirty || errors.size > 0}
                loading={update.isPending}
                icon={<Save className="h-3.5 w-3.5" aria-hidden />}
                onClick={save}
              >
                Save changes
              </Button>
            </div>
          }
        />

        {dirty || errors.size > 0 ? (
          <div
            className={cn(
              "flex items-center gap-2 border-b px-5 py-2.5 text-xs",
              errors.size > 0
                ? "border-critical/25 bg-critical-soft text-critical"
                : "border-warning/25 bg-warning-soft text-warning",
            )}
          >
            {errors.size > 0 ? (
              <>
                <AlertCircle className="h-3.5 w-3.5 shrink-0" aria-hidden />
                {errors.size} quer{errors.size === 1 ? "y" : "ies"} need fixing before
                this can be saved.
              </>
            ) : (
              <>
                <Check className="h-3.5 w-3.5 shrink-0" aria-hidden />
                Unsaved changes. Saving recomputes the fingerprint and resets the
                drift baseline.
              </>
            )}
          </div>
        ) : null}

        <CardBody className="space-y-3">
          {queries.map((query, index) => (
            <QueryRow
              key={query.key}
              query={query}
              index={index}
              error={errors.get(query.key)}
              onChange={(next) =>
                mutate((current) =>
                  current.map((item) => (item.key === query.key ? next : item)),
                )
              }
              onRemove={() =>
                mutate((current) => current.filter((item) => item.key !== query.key))
              }
            />
          ))}

          <Button
            className="w-full"
            icon={<Plus className="h-3.5 w-3.5" aria-hidden />}
            onClick={() =>
              mutate((current) => [
                ...current,
                {
                  key: nextKey(),
                  query_id: "",
                  query: "",
                  expected_documents: [{ document_id: "", relevance: 3 }],
                  note: null,
                },
              ])
            }
          >
            Add query
          </Button>
        </CardBody>
      </Card>
    </div>
  );
}

function QueryRow({
  query,
  index,
  error,
  onChange,
  onRemove,
}: {
  query: DraftQuery;
  index: number;
  error?: string;
  onChange: (next: DraftQuery) => void;
  onRemove: () => void;
}) {
  return (
    <div
      className={cn(
        "rounded-md border bg-surface px-4 py-4 transition-colors duration-fast ease-out",
        error ? "border-danger-line" : "border-line hover:border-line-strong",
      )}
    >
      {/* Row 1 — the query itself, which is what a reader scans for. */}
      <div className="flex items-start gap-3">
        <span className="tnum mt-2 w-5 shrink-0 text-right text-label text-ink-disabled">
          {index + 1}
        </span>
        <Input
          value={query.query}
          invalid={Boolean(error)}
          placeholder="How a user would actually ask this…"
          aria-label={`Query ${index + 1} text`}
          onChange={(event) => onChange({ ...query, query: event.target.value })}
        />
        <IconButton
          aria-label={`Remove query ${index + 1}`}
          size="sm"
          className="mt-0.5 hover:text-danger-text"
          icon={<Trash2 className="h-3.5 w-3.5" aria-hidden />}
          onClick={onRemove}
        />
      </div>

      <div className="mt-4 space-y-4 pl-8">
        {/* Row 2 — identifier, clearly labelled rather than a bare box. */}
        <div className="flex items-center gap-2">
          <label
            className="text-micro uppercase text-ink-tertiary"
            htmlFor={`query-id-${index}`}
          >
            Query id
          </label>
          <Input
            id={`query-id-${index}`}
            value={query.query_id}
            inputSize="sm"
            placeholder="generated if left blank"
            className="w-56 font-mono text-[11px]"
            onChange={(event) => onChange({ ...query, query_id: event.target.value })}
          />
        </div>

        {/* Row 3 — the judgements. */}
        <div>
          <p className="text-micro uppercase text-ink-tertiary">Expected documents</p>
          <div className="mt-2 space-y-2">
            {query.expected_documents.map((doc, docIndex) => (
              <div key={docIndex} className="flex items-center gap-2">
                <Input
                  value={doc.document_id}
                  inputSize="sm"
                  placeholder="document id"
                  aria-label={`Expected document ${docIndex + 1}`}
                  className="font-mono text-[11px]"
                  onChange={(event) =>
                    onChange({
                      ...query,
                      expected_documents: query.expected_documents.map((item, i) =>
                        i === docIndex
                          ? { ...item, document_id: event.target.value }
                          : item,
                      ),
                    })
                  }
                />
                <Select
                  value={doc.relevance}
                  selectSize="sm"
                  aria-label="Relevance grade"
                  className="w-36"
                  onChange={(event) =>
                    onChange({
                      ...query,
                      expected_documents: query.expected_documents.map((item, i) =>
                        i === docIndex
                          ? { ...item, relevance: Number(event.target.value) }
                          : item,
                      ),
                    })
                  }
                >
                  <option value={3}>highly relevant</option>
                  <option value={2}>relevant</option>
                  <option value={1}>marginal</option>
                </Select>
                <IconButton
                  aria-label={`Remove expected document ${docIndex + 1}`}
                  size="sm"
                  className="hover:text-danger-text"
                  icon={<Trash2 className="h-3.5 w-3.5" aria-hidden />}
                  onClick={() =>
                    onChange({
                      ...query,
                      expected_documents: query.expected_documents.filter(
                        (_, i) => i !== docIndex,
                      ),
                    })
                  }
                />
              </div>
            ))}
          </div>

          <Button
            variant="ghost"
            size="sm"
            className="mt-2"
            icon={<Plus className="h-3 w-3" aria-hidden />}
            onClick={() =>
              onChange({
                ...query,
                expected_documents: [
                  ...query.expected_documents,
                  { document_id: "", relevance: 1 },
                ],
              })
            }
          >
            Add expected document
          </Button>
        </div>

        {error ? (
          <p className="flex items-center gap-1.5 text-small text-danger-text">
            <AlertCircle className="h-3.5 w-3.5 shrink-0" aria-hidden />
            {error}
          </p>
        ) : null}
      </div>
    </div>
  );
}

/** Drops the React keys so drafts can be compared by content. */
function strip(queries: DraftQuery[]) {
  return queries.map((query) => ({
    query_id: query.query_id,
    query: query.query,
    expected_documents: query.expected_documents,
    note: query.note,
  }));
}
