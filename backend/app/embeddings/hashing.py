"""A deterministic, dependency-free embedding provider.

Why this exists: the demo, the test suite and CI must all be able to build a
real vector index without downloading a transformer model. This provider uses
the *hashing trick* (signed feature hashing over word unigrams, word bigrams
and character trigrams, sub-linear term weighting, L2 normalisation), which
gives cosine similarity that behaves sensibly on lexical overlap.

It is intentionally **not** a semantic model. It is a fast, offline,
reproducible stand-in that makes the whole pipeline runnable out of the box;
production deployments register a real provider under a different name and the
recorded ``model_id`` makes the swap visible to drift diagnostics.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Iterator, Sequence
from itertools import pairwise

from app.embeddings.base import EmbeddingProvider, Vector
from app.embeddings.registry import register_embedding_provider

_TOKEN_RE = re.compile(r"[a-z0-9]+")

#: Bumped whenever the feature extraction changes in a way that would alter
#: vectors, so that ``model_id`` never silently means two different things.
_ALGORITHM_VERSION = "v1"

DEFAULT_DIMENSIONS = 384
_CHAR_NGRAM = 3


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _features(text: str) -> Iterator[str]:
    """Yield the feature strings extracted from ``text``.

    Three feature families, each namespaced so they cannot collide:
    ``w:`` word unigrams, ``b:`` word bigrams (local word order), and ``c:``
    character trigrams (robustness to morphology and typos).
    """
    tokens = _tokenize(text)
    for token in tokens:
        yield f"w:{token}"
        if len(token) > _CHAR_NGRAM:
            for i in range(len(token) - _CHAR_NGRAM + 1):
                yield f"c:{token[i : i + _CHAR_NGRAM]}"
    for left, right in pairwise(tokens):
        yield f"b:{left}_{right}"


def _hash(feature: str) -> int:
    """Process-stable 64-bit hash.

    ``hash()`` is salted per interpreter run, which would make vectors
    irreproducible across restarts — blake2b is used instead.
    """
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


@register_embedding_provider
class HashingEmbeddingProvider(EmbeddingProvider):
    """Signed feature hashing with sub-linear term frequency weighting."""

    name = "hashing"

    def __init__(self, dimensions: int = DEFAULT_DIMENSIONS) -> None:
        if dimensions < 16:
            raise ValueError("dimensions must be >= 16 for stable hashing")
        self._dimensions = dimensions

    @property
    def model_id(self) -> str:
        return f"hashing-{_ALGORITHM_VERSION}-d{self._dimensions}"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> Vector:
        counts = Counter(_features(text))
        vector = [0.0] * self._dimensions

        for feature, count in counts.items():
            bits = _hash(feature)
            index = bits % self._dimensions
            # Signed hashing keeps collisions unbiased in expectation.
            sign = 1.0 if (bits >> 63) & 1 else -1.0
            # Sub-linear TF: a term appearing 10x is not 10x as informative.
            vector[index] += sign * (1.0 + math.log(count))

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            # Empty or purely non-alphanumeric text; a zero vector would make
            # cosine distance undefined, so fall back to a fixed unit vector.
            vector[0] = 1.0
            return vector
        return [value / norm for value in vector]
