"""Loading golden sets from JSON and CSV.

Two on-disk shapes are supported because the two audiences differ: JSON for
systems that generate golden sets programmatically (and want graded
relevance), CSV for humans maintaining them in a spreadsheet.

Every parse failure raises :class:`~app.core.errors.GoldenSetError` with the
offending row or index named, because a golden set with a typo in it produces
a *plausible-looking but wrong* quality number -- the worst possible failure
mode for a tool whose whole job is to be trusted about quality.
"""

from __future__ import annotations

import csv
import io
import json
from collections import OrderedDict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.core.errors import GoldenSetError
from app.domain.golden_set import (
    DEFAULT_RELEVANCE,
    ExpectedDocument,
    GoldenQuery,
    GoldenSet,
)

__all__ = [
    "GOLDEN_SET_CSV_COLUMNS",
    "load_golden_set",
    "parse_csv_golden_set",
    "parse_json_golden_set",
    "to_json_payload",
]

#: Accepted CSV header names, in preference order, for each logical field.
_CSV_ALIASES: dict[str, tuple[str, ...]] = {
    "query_id": ("query_id", "id", "qid"),
    "query": ("query", "question", "text"),
    "document_id": (
        "expected_document_id",
        "document_id",
        "doc_id",
        "expected_doc_id",
    ),
    "relevance": ("relevance", "grade", "rating"),
    "note": ("note", "notes", "comment"),
}

GOLDEN_SET_CSV_COLUMNS: tuple[str, ...] = (
    "query_id",
    "query",
    "expected_document_id",
    "relevance",
    "note",
)


def load_golden_set(
    path: str | Path,
    *,
    name: str | None = None,
    version: str | None = None,
) -> GoldenSet:
    """Load a golden set from ``path``, dispatching on file extension.

    ``name`` and ``version`` override whatever the file declares, which is how
    the API lets a caller re-version an uploaded set without editing it.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise GoldenSetError(f"golden set file not found: {file_path}")

    try:
        raw = file_path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise GoldenSetError(f"could not read golden set {file_path}: {exc}") from exc

    suffix = file_path.suffix.lower()
    if suffix == ".json":
        golden_set = parse_json_golden_set(raw, default_name=file_path.stem)
    elif suffix in (".csv", ".tsv"):
        golden_set = parse_csv_golden_set(
            raw,
            default_name=file_path.stem,
            delimiter="\t" if suffix == ".tsv" else ",",
        )
    else:
        raise GoldenSetError(
            f"unsupported golden set format '{suffix or file_path.name}'; "
            "expected .json, .csv or .tsv"
        )

    if name is None and version is None:
        return golden_set
    return golden_set.model_copy(
        update={
            "name": name or golden_set.name,
            "version": version or golden_set.version,
        }
    )


# ----------------------------------------------------------------------
# JSON
# ----------------------------------------------------------------------
def parse_json_golden_set(raw: str, *, default_name: str = "golden-set") -> GoldenSet:
    """Parse the JSON representation.

    Accepts either a full object::

        {"name": ..., "version": ..., "queries": [...]}

    or a bare ``[...]`` list of query objects. Within a query, expected
    documents may be given as ``expected_document_id`` (one id),
    ``expected_document_ids`` (a list of ids), or ``expected_documents``
    (objects carrying graded ``relevance``).
    """
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GoldenSetError(f"invalid JSON in golden set: {exc}") from exc

    if isinstance(payload, list):
        payload = {"queries": payload}
    if not isinstance(payload, dict):
        raise GoldenSetError(
            "golden set JSON must be an object or a list of query objects"
        )

    raw_queries = payload.get("queries")
    if not isinstance(raw_queries, list) or not raw_queries:
        raise GoldenSetError("golden set JSON must contain a non-empty 'queries' list")

    queries = [
        _query_from_mapping(entry, index) for index, entry in enumerate(raw_queries)
    ]

    return _build(
        name=str(payload.get("name") or default_name),
        version=str(payload.get("version") or "1"),
        description=payload.get("description"),
        queries=queries,
    )


def _query_from_mapping(entry: Any, index: int) -> GoldenQuery:
    where = f"queries[{index}]"
    if not isinstance(entry, Mapping):
        raise GoldenSetError(f"{where} must be an object, got {type(entry).__name__}")

    query_text = entry.get("query") or entry.get("question")
    if not isinstance(query_text, str) or not query_text.strip():
        raise GoldenSetError(f"{where} is missing a non-empty 'query'")

    query_id = str(entry.get("query_id") or entry.get("id") or f"q{index + 1}")
    expected = _expected_documents_from_mapping(entry, where)

    try:
        return GoldenQuery(
            query_id=query_id,
            query=query_text,
            expected_documents=tuple(expected),
            note=_optional_str(entry.get("note")),
        )
    except ValidationError as exc:
        raise GoldenSetError(f"{where} is invalid: {_first_error(exc)}") from exc


def _expected_documents_from_mapping(
    entry: Mapping[str, Any], where: str
) -> list[ExpectedDocument]:
    if "expected_documents" in entry:
        raw_docs = entry["expected_documents"]
        if not isinstance(raw_docs, list) or not raw_docs:
            raise GoldenSetError(f"{where}.expected_documents must be a non-empty list")
        documents: list[ExpectedDocument] = []
        for position, raw_doc in enumerate(raw_docs):
            location = f"{where}.expected_documents[{position}]"
            if isinstance(raw_doc, str):
                documents.append(ExpectedDocument(document_id=raw_doc))
                continue
            if not isinstance(raw_doc, Mapping):
                raise GoldenSetError(f"{location} must be an object or a string id")
            document_id = raw_doc.get("document_id") or raw_doc.get("id")
            if not isinstance(document_id, str) or not document_id:
                raise GoldenSetError(f"{location} is missing 'document_id'")
            try:
                documents.append(
                    ExpectedDocument(
                        document_id=document_id,
                        relevance=int(raw_doc.get("relevance", DEFAULT_RELEVANCE)),
                    )
                )
            except (TypeError, ValueError, ValidationError) as exc:
                raise GoldenSetError(f"{location} has an invalid relevance: {exc}") from exc
        return documents

    ids: list[str] = []
    if "expected_document_ids" in entry:
        raw_ids = entry["expected_document_ids"]
        if not isinstance(raw_ids, list):
            raise GoldenSetError(f"{where}.expected_document_ids must be a list")
        ids = [str(value) for value in raw_ids]
    elif "expected_document_id" in entry:
        ids = [str(entry["expected_document_id"])]

    ids = [value for value in ids if value.strip()]
    if not ids:
        raise GoldenSetError(
            f"{where} must declare at least one expected document via "
            "'expected_document_id', 'expected_document_ids' or 'expected_documents'"
        )
    return [ExpectedDocument(document_id=value) for value in ids]


# ----------------------------------------------------------------------
# CSV
# ----------------------------------------------------------------------
def parse_csv_golden_set(
    raw: str,
    *,
    default_name: str = "golden-set",
    delimiter: str = ",",
) -> GoldenSet:
    """Parse the flat CSV representation.

    One row per (query, expected document) pair; rows sharing a ``query_id``
    are folded into a single multi-document judgement. Header names are
    matched case-insensitively against a small alias table, so
    ``doc_id``/``document_id``/``expected_document_id`` all work.
    """
    reader = csv.DictReader(io.StringIO(raw), delimiter=delimiter)
    if reader.fieldnames is None:
        raise GoldenSetError("golden set CSV is empty")

    columns = _resolve_csv_columns(reader.fieldnames)
    grouped: OrderedDict[str, dict[str, Any]] = OrderedDict()

    for row_number, row in enumerate(reader, start=2):  # row 1 is the header
        query_text = _cell(row, columns.get("query"))
        document_id = _cell(row, columns.get("document_id"))
        if not query_text and not document_id:
            continue  # tolerate blank separator rows
        if not query_text:
            raise GoldenSetError(f"row {row_number}: missing query text")
        if not document_id:
            raise GoldenSetError(
                f"row {row_number}: missing expected document id for query "
                f"'{query_text[:60]}'"
            )

        query_id = _cell(row, columns.get("query_id")) or f"q{len(grouped) + 1}"
        relevance = _parse_relevance(_cell(row, columns.get("relevance")), row_number)

        bucket = grouped.setdefault(
            query_id,
            {
                "query": query_text,
                "note": _cell(row, columns.get("note")) or None,
                "documents": [],
            },
        )
        if bucket["query"] != query_text:
            raise GoldenSetError(
                f"row {row_number}: query_id '{query_id}' is reused with different "
                "query text; ids must be unique per query"
            )
        if any(doc.document_id == document_id for doc in bucket["documents"]):
            raise GoldenSetError(
                f"row {row_number}: document '{document_id}' is listed twice for "
                f"query '{query_id}'"
            )
        bucket["documents"].append(
            ExpectedDocument(document_id=document_id, relevance=relevance)
        )

    if not grouped:
        raise GoldenSetError("golden set CSV contains no usable rows")

    queries = [
        GoldenQuery(
            query_id=query_id,
            query=bucket["query"],
            expected_documents=tuple(bucket["documents"]),
            note=bucket["note"],
        )
        for query_id, bucket in grouped.items()
    ]
    return _build(name=default_name, version="1", description=None, queries=queries)


def _resolve_csv_columns(fieldnames: Sequence[str]) -> dict[str, str]:
    normalised = {
        (name or "").strip().lower(): (name or "") for name in fieldnames
    }
    resolved: dict[str, str] = {}
    for logical, aliases in _CSV_ALIASES.items():
        for alias in aliases:
            if alias in normalised:
                resolved[logical] = normalised[alias]
                break

    missing = [field for field in ("query", "document_id") if field not in resolved]
    if missing:
        expected = ", ".join(GOLDEN_SET_CSV_COLUMNS)
        raise GoldenSetError(
            f"golden set CSV is missing required column(s) for {missing}; "
            f"expected headers like: {expected}"
        )
    return resolved


def _cell(row: Mapping[str, Any], column: str | None) -> str:
    if column is None:
        return ""
    value = row.get(column)
    return str(value).strip() if value is not None else ""


def _parse_relevance(value: str, row_number: int) -> int:
    if not value:
        return DEFAULT_RELEVANCE
    try:
        relevance = int(float(value))
    except ValueError:
        raise GoldenSetError(
            f"row {row_number}: relevance '{value}' is not a number"
        ) from None
    if not 0 <= relevance <= 10:
        raise GoldenSetError(
            f"row {row_number}: relevance {relevance} is outside the range 0-10"
        )
    return relevance


# ----------------------------------------------------------------------
# Shared helpers
# ----------------------------------------------------------------------
def _build(
    *,
    name: str,
    version: str,
    description: Any,
    queries: Sequence[GoldenQuery],
) -> GoldenSet:
    try:
        return GoldenSet(
            name=name,
            version=version,
            description=_optional_str(description),
            queries=tuple(queries),
        )
    except ValidationError as exc:
        raise GoldenSetError(f"invalid golden set: {_first_error(exc)}") from exc


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_error(exc: ValidationError) -> str:
    errors: Iterable[Mapping[str, Any]] = exc.errors()
    for error in errors:
        location = ".".join(str(part) for part in error.get("loc", ()))
        message = error.get("msg", "invalid value")
        return f"{location}: {message}" if location else str(message)
    return str(exc)


def to_json_payload(golden_set: GoldenSet) -> dict[str, Any]:
    """Serialise a golden set back into the canonical JSON shape.

    Round-trips through :func:`parse_json_golden_set`, which is what lets the
    Stage 5 golden set editor save what it loaded.
    """
    return {
        "name": golden_set.name,
        "version": golden_set.version,
        "description": golden_set.description,
        "queries": [
            {
                "query_id": query.query_id,
                "query": query.query,
                "expected_documents": [
                    {"document_id": doc.document_id, "relevance": doc.relevance}
                    for doc in query.expected_documents
                ],
                **({"note": query.note} if query.note else {}),
            }
            for query in golden_set.queries
        ],
    }
