"""Command line entry point.

``python -m app.cli <command>``

The CLI is a thin adapter: it parses arguments, calls the same services the
HTTP API calls, and formats the result for a terminal. No business logic lives
here -- if a command needs new behaviour, the behaviour belongs in a service.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from app.connectors import available_connectors
from app.core.config import Settings, get_settings
from app.core.errors import DriftDetectorError
from app.core.factory import build_scoring_engine, build_vector_store
from app.core.logging import configure_logging
from app.db.migrations import (
    current_revision,
    downgrade_to,
    head_revision,
    upgrade_to_head,
)
from app.db.session import session_scope
from app.domain.golden_set import GoldenSet
from app.domain.metrics import EvaluationResult
from app.embeddings import available_embedding_providers
from app.repositories.golden_sets import GoldenSetRepository
from app.repositories.runs import RunRepository
from app.services.bootstrap import bootstrap
from app.services.corpus import load_documents, seed_documents
from app.services.golden_set_service import GoldenSetService
from app.services.goldenset.loader import load_golden_set


def _prepare_database(settings: Settings) -> None:
    """Migrate, and bootstrap demo data, before touching the database.

    Deliberately the same code path the API runs at startup: `evaluate` from
    the CLI and "Run Evaluation Now" from the dashboard must not disagree
    about whether a fresh install has a golden set.
    """
    bootstrap(settings=settings)


# ----------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------
def command_seed(args: argparse.Namespace, settings: Settings) -> int:
    """Index a document corpus into the configured vector store."""
    corpus_path = Path(args.corpus) if args.corpus else settings.demo_documents_path
    documents = load_documents(corpus_path)

    with build_vector_store(settings) as store:
        if args.reset:
            store.delete_documents(  # type: ignore[attr-defined]
                [record.document_id for record in documents]
            )
        written = seed_documents(store, documents)
        total = store.count_documents()

    print(f"Seeded {written} documents from {corpus_path}")
    print(f"Collection '{settings.chroma_collection}' now holds {total} documents")
    return 0


def command_evaluate(args: argparse.Namespace, settings: Settings) -> int:
    """Score a golden set and, by default, record the run in history."""
    if args.no_save:
        golden_set = _golden_set_from_file_or_demo(args, settings)
        with build_vector_store(settings) as store:
            result = build_scoring_engine(settings, connector=store).evaluate(
                golden_set
            )
        _print_report(result, show_queries=args.verbose)
        print("(not saved: --no-save)\n")
        return 0

    _prepare_database(settings)
    with session_scope(settings) as session, build_vector_store(settings) as store:
        golden_sets = GoldenSetService(GoldenSetRepository(session))
        if args.golden_set:
            # Scoring a file directly still records history; the run keeps the
            # set's name, version and fingerprint even with no stored parent.
            golden_set = load_golden_set(Path(args.golden_set))
            golden_set_id = None
        else:
            stored = golden_sets.get_active()
            golden_set, golden_set_id = stored.golden_set, stored.golden_set_id

        result = build_scoring_engine(settings, connector=store).evaluate(golden_set)
        record = RunRepository(session).save(
            result, golden_set_id=golden_set_id, trigger="cli"
        )
        record_json = record.model_dump_json(indent=2)
        run_id = record.run_id

    if args.json:
        print(record_json)
        return 0

    _print_report(result, show_queries=args.verbose)
    print(f"Saved as run {run_id}\n")
    return 0


def command_history(args: argparse.Namespace, settings: Settings) -> int:
    """List recorded runs, newest first."""
    _prepare_database(settings)
    with session_scope(settings) as session:
        page = RunRepository(session).list_runs(limit=args.limit)

    if not page.items:
        print("No runs recorded yet. Run `evaluate` to create one.")
        return 0

    header = (
        f"{'started (UTC)':<20} {'run id':<10} {'golden set':<24} "
        f"{'recall':>7} {'ndcg':>7} {'mrr':>7} {'docs':>6}"
    )
    print(header)
    print("-" * len(header))
    for record in page.items:
        metrics = record.primary_metrics
        print(
            f"{record.started_at:%Y-%m-%d %H:%M:%S} "
            f"{record.run_id[:8]:<10} "
            f"{record.golden_set.name[:22]:<24} "
            f"{metrics.recall_at_k:>7.4f} {metrics.ndcg_at_k:>7.4f} "
            f"{metrics.mrr:>7.4f} {record.store.document_count:>6}"
        )
    print(
        f"\nShowing {len(page.items)} of {page.total} runs "
        f"(primary cutoff k={page.items[0].primary_k})"
    )
    return 0


def command_db(args: argparse.Namespace, settings: Settings) -> int:
    """Inspect or move the database schema."""
    if args.db_command == "upgrade":
        upgrade_to_head(settings)
        print(f"Database is at revision {current_revision(settings)}")
        return 0

    if args.db_command == "downgrade":
        downgrade_to(args.revision, settings)
        print(f"Database is at revision {current_revision(settings) or 'base'}")
        return 0

    current = current_revision(settings)
    head = head_revision(settings)
    print(f"  url       {settings.resolved_database_url}")
    print(f"  current   {current or '(not initialised)'}")
    print(f"  head      {head}")
    print(f"  status    {'up to date' if current == head else 'MIGRATION PENDING'}")
    return 0 if current == head else 1


def command_import_golden_set(args: argparse.Namespace, settings: Settings) -> int:
    """Import a golden set file into the database."""
    _prepare_database(settings)
    path = Path(args.path) if args.path else settings.demo_golden_set_path
    with session_scope(settings) as session:
        service = GoldenSetService(GoldenSetRepository(session))
        stored = service.import_from_file(
            path, name=args.name, version=args.version, activate=not args.no_activate
        )
        set_id = stored.golden_set_id
        name = stored.golden_set.name
        version = stored.golden_set.version
        queries = stored.query_count
        fingerprint = stored.fingerprint
        is_active = stored.is_active

    print(f"Imported golden set #{set_id}: '{name}' v{version}")
    print(f"  queries       {queries}")
    print(f"  fingerprint   {fingerprint}")
    print(f"  active        {'yes' if is_active else 'no'}")
    return 0


def command_info(_args: argparse.Namespace, settings: Settings) -> int:
    """Print resolved configuration and component status."""
    with build_vector_store(settings) as store:
        health = store.health_check()
        info = store.describe() if health.reachable else None

    print(f"{settings.app_name} ({settings.environment})")
    print(f"  data dir              {settings.data_dir}")
    print(f"  database              {settings.resolved_database_url}")
    print(f"  schema revision       {current_revision(settings) or '(not initialised)'}")
    print(f"  connectors available  {', '.join(available_connectors())}")
    print(f"  embedders available   {', '.join(available_embedding_providers())}")
    print(f"  connector             {settings.connector} ({settings.chroma_mode})")
    print(f"  collection            {settings.chroma_collection}")
    print(f"  reachable             {'yes' if health.reachable else 'no'}")
    if health.message:
        print(f"  message               {health.message}")
    if info is not None:
        print(f"  documents indexed     {info.document_count}")
        print(
            f"  index embedding model {info.embedding_model} "
            f"(dim {info.embedding_dimensions})"
        )
        print(f"  query embedding model {info.extra.get('query_embedding_model')}")
    print(
        f"  eval cutoffs          {list(settings.eval_k_values)} "
        f"(primary k={settings.eval_primary_k})"
    )
    return 0


def command_golden_set(args: argparse.Namespace, settings: Settings) -> int:
    """Validate a golden set file and summarise it."""
    golden_path = Path(args.path) if args.path else settings.demo_golden_set_path
    golden_set = load_golden_set(golden_path)

    print(f"Golden set '{golden_set.name}' v{golden_set.version}")
    print(f"  source        {golden_path}")
    print(f"  fingerprint   {golden_set.fingerprint}")
    print(f"  queries       {len(golden_set)}")
    print(
        f"  documents     {len(golden_set.all_expected_document_ids)} distinct expected"
    )
    graded = sum(
        1
        for query in golden_set.queries
        for doc in query.expected_documents
        if doc.relevance not in (0, 1)
    )
    print(f"  graded pairs  {graded}")

    if args.check_index:
        with build_vector_store(settings) as store:
            present = store.existing_document_ids(
                sorted(golden_set.all_expected_document_ids)
            )
        missing = sorted(golden_set.all_expected_document_ids - present)
        if missing:
            print(f"  MISSING from index ({len(missing)}): {', '.join(missing[:10])}")
            if len(missing) > 10:
                print(f"    ...and {len(missing) - 10} more")
            return 1
        print("  all expected documents are present in the index")
    return 0


def command_serve(args: argparse.Namespace, settings: Settings) -> int:
    """Run the HTTP API with uvicorn."""
    import uvicorn

    print(f"Serving {settings.app_name} on http://{args.host}:{args.port}")
    print(f"  API docs   http://{args.host}:{args.port}/docs")
    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=settings.log_level.lower(),
    )
    return 0


# ----------------------------------------------------------------------
# Formatting
# ----------------------------------------------------------------------
def _golden_set_from_file_or_demo(
    args: argparse.Namespace, settings: Settings
) -> GoldenSet:
    path = Path(args.golden_set) if args.golden_set else settings.demo_golden_set_path
    return load_golden_set(path)


def _print_report(result: EvaluationResult, *, show_queries: bool = False) -> None:
    print()
    print(
        f"Golden set : {result.golden_set_name} v{result.golden_set_version} "
        f"({result.golden_set_fingerprint})"
    )
    print(
        f"Store      : {result.store.connector}/{result.store.collection} "
        f"- {result.store.document_count} documents"
    )
    print(f"Embeddings : {result.store.embedding_model}")
    print(f"Queries    : {result.query_count}   Duration: {result.duration_ms:.0f} ms")
    print()

    header = f"{'k':>3}  {'Recall@k':>9}  {'Precision@k':>12}  {'MRR':>7}  {'NDCG@k':>8}"
    print(header)
    print("-" * len(header))
    for metric_set in result.metrics:
        marker = " *" if metric_set.k == result.primary_k else "  "
        print(
            f"{metric_set.k:>3}  {metric_set.recall_at_k:>9.4f}  "
            f"{metric_set.precision_at_k:>12.4f}  {metric_set.mrr:>7.4f}  "
            f"{metric_set.ndcg_at_k:>8.4f}{marker}"
        )
    print(f"\n* primary cutoff (k={result.primary_k}) - the one drift detection tests")

    misses = result.missed_queries
    if misses:
        print(f"\nComplete misses at k={result.primary_k} ({len(misses)}):")
        for score in misses[:10]:
            print(f"  - [{score.query_id}] {score.query}")
            print(f"      expected {list(score.relevant_ids)}")
            print(f"      got      {list(score.retrieved_ids[:5])}")
        if len(misses) > 10:
            print(f"  ...and {len(misses) - 10} more")
    else:
        print(f"\nNo complete misses at k={result.primary_k}.")

    if show_queries:
        print(f"\nPer-query detail at k={result.primary_k}:")
        detail_header = (
            f"  {'query_id':<24} {'recall':>7} {'prec':>7} "
            f"{'rr':>7} {'ndcg':>7} {'rank':>5}"
        )
        print(detail_header)
        print("  " + "-" * (len(detail_header) - 2))
        for score in sorted(result.query_scores, key=lambda s: s.ndcg_at_k):
            rank = score.first_relevant_rank or "-"
            print(
                f"  {score.query_id:<24} {score.recall_at_k:>7.3f} "
                f"{score.precision_at_k:>7.3f} {score.reciprocal_rank:>7.3f} "
                f"{score.ndcg_at_k:>7.3f} {rank:>5}"
            )
    print()


# ----------------------------------------------------------------------
# Argument parsing
# ----------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="drift",
        description="RAG Drift Detector - monitor retrieval quality over time.",
    )
    parser.add_argument(
        "--log-level", default=None, help="Override DRIFT_LOG_LEVEL for this run."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed = subparsers.add_parser("seed", help="Index a document corpus.")
    seed.add_argument("--corpus", help="Path to a corpus JSON file (default: demo).")
    seed.add_argument(
        "--reset",
        action="store_true",
        help="Delete the corpus ids before re-indexing them.",
    )
    seed.set_defaults(handler=command_seed)

    evaluate = subparsers.add_parser(
        "evaluate", help="Score a golden set and record the run."
    )
    evaluate.add_argument(
        "--golden-set", help="Score this file instead of the active stored golden set."
    )
    evaluate.add_argument(
        "--no-save", action="store_true", help="Score without recording history."
    )
    evaluate.add_argument("--json", action="store_true", help="Emit the stored record.")
    evaluate.add_argument(
        "-v", "--verbose", action="store_true", help="Include per-query detail."
    )
    evaluate.set_defaults(handler=command_evaluate)

    history = subparsers.add_parser("history", help="List recorded runs.")
    history.add_argument("-n", "--limit", type=int, default=20)
    history.set_defaults(handler=command_history)

    database = subparsers.add_parser("db", help="Inspect or migrate the schema.")
    db_sub = database.add_subparsers(dest="db_command", required=True)
    db_sub.add_parser("status", help="Show current and head revisions.")
    db_sub.add_parser("upgrade", help="Apply all pending migrations.")
    db_downgrade = db_sub.add_parser("downgrade", help="Roll back to a revision.")
    db_downgrade.add_argument("revision", help="Target revision, or 'base'.")
    database.set_defaults(handler=command_db)

    import_gs = subparsers.add_parser(
        "import-golden-set", help="Store a golden set file in the database."
    )
    import_gs.add_argument("path", nargs="?", help="JSON or CSV file (default: demo).")
    import_gs.add_argument("--name", help="Override the name in the file.")
    import_gs.add_argument("--version", help="Override the version in the file.")
    import_gs.add_argument(
        "--no-activate",
        action="store_true",
        help="Store without making it the active golden set.",
    )
    import_gs.set_defaults(handler=command_import_golden_set)

    info = subparsers.add_parser("info", help="Show configuration and store status.")
    info.set_defaults(handler=command_info)

    golden = subparsers.add_parser("golden-set", help="Validate a golden set file.")
    golden.add_argument("path", nargs="?", help="Path to the golden set file.")
    golden.add_argument(
        "--check-index",
        action="store_true",
        help="Also verify every expected document exists in the vector store.",
    )
    golden.set_defaults(handler=command_golden_set)

    serve = subparsers.add_parser("serve", help="Run the HTTP API.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true", help="Reload on code changes.")
    serve.set_defaults(handler=command_serve)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(args.log_level or settings.log_level)

    try:
        return int(args.handler(args, settings))
    except DriftDetectorError as exc:
        # Expected, actionable failures: report them cleanly rather than
        # dumping a traceback the user cannot act on.
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:  # pragma: no cover
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
