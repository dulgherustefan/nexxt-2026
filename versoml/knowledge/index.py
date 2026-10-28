"""Retrieval signals and their fusion: BM25 (own implementation), dense cosine, character n-gram TF-IDF, RRF, MMR."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence

import numpy as np

from versoml.knowledge.text import char_ngram_text, tokenize


class BM25:
    """Okapi BM25 over token lists. Postings are numpy arrays, so a query costs a few vector operations."""

    def __init__(self, docs: Sequence[Sequence[str]], k1: float = 1.2, b: float = 0.75):
        self.k1, self.b = k1, b
        self.n = len(docs)
        self.doc_len = np.array([len(d) for d in docs], dtype=np.float32)
        self.avgdl = float(self.doc_len.mean()) if self.n else 0.0
        postings: dict[str, tuple[list[int], list[int]]] = {}
        for i, doc in enumerate(docs):
            for term, tf in Counter(doc).items():
                entry = postings.get(term)
                if entry is None:
                    postings[term] = ([i], [tf])
                else:
                    entry[0].append(i)
                    entry[1].append(tf)
        norm = self.k1 * (1 - self.b + self.b * self.doc_len / (self.avgdl or 1.0))
        self._postings: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        self.idf: dict[str, float] = {}
        for term, (ids, tfs) in postings.items():
            ids_arr = np.asarray(ids, dtype=np.int32)
            tf_arr = np.asarray(tfs, dtype=np.float32)
            df = len(ids)
            idf = math.log(1 + (self.n - df + 0.5) / (df + 0.5))
            self.idf[term] = idf
            # the term's contribution per document, precomputed
            weight = idf * tf_arr * (self.k1 + 1) / (tf_arr + norm[ids_arr])
            self._postings[term] = (ids_arr, weight.astype(np.float32))

    def scores(self, query_tokens: Sequence[str]) -> np.ndarray:
        out = np.zeros(self.n, dtype=np.float32)
        for term, qtf in Counter(query_tokens).items():
            entry = self._postings.get(term)
            if entry is not None:
                out[entry[0]] += entry[1] * (1.0 + 0.25 * (qtf - 1))
        return out


class CharNgramTfidf:
    """Character 3-5 gram TF-IDF (hashed), cosine similarity. The offline stand-in for a query vector."""

    def __init__(self, texts: Sequence[str], ns: tuple[int, ...] = (3, 4, 5), bits: int = 20):
        from scipy import sparse

        self.ns, self.bits = ns, bits
        self.dim = 1 << bits
        rows = [self._counts(t) for t in texts]
        indptr = np.zeros(len(rows) + 1, dtype=np.int64)
        indptr[1:] = np.cumsum([len(r[0]) for r in rows])
        indices = np.concatenate([r[0] for r in rows]) if rows else np.zeros(0, dtype=np.int64)
        counts = np.concatenate([r[1] for r in rows]) if rows else np.zeros(0, dtype=np.float32)
        df = np.bincount(indices, minlength=self.dim).astype(np.float32)
        n = max(1, len(rows))
        self.idf = (np.log((1 + n) / (1 + df)) + 1.0).astype(np.float32)
        data = (1.0 + np.log(counts)) * self.idf[indices]
        matrix = sparse.csr_matrix((data.astype(np.float32), indices, indptr), shape=(len(rows), self.dim))
        norms = np.sqrt(np.asarray(matrix.multiply(matrix).sum(axis=1)).ravel())
        norms[norms == 0] = 1.0
        self.matrix = sparse.diags(1.0 / norms).dot(matrix).tocsr()

    def _counts(self, text: str) -> tuple[np.ndarray, np.ndarray]:
        s = char_ngram_text(text)
        codes = np.frombuffer(s.encode("utf-32-le"), dtype=np.uint32).astype(np.uint64)
        grams = []
        for n in self.ns:
            if len(codes) < n:
                continue
            h = np.full(len(codes) - n + 1, n, dtype=np.uint64)
            for j in range(n):
                h = h * np.uint64(1_000_003) + codes[j:len(codes) - n + 1 + j]
            grams.append((h * np.uint64(0x9E3779B97F4A7C15)) >> np.uint64(64 - self.bits))
        if not grams:
            return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float32)
        values, counts = np.unique(np.concatenate(grams), return_counts=True)
        return values.astype(np.int64), counts.astype(np.float32)

    def scores(self, text: str) -> np.ndarray:
        idx, counts = self._counts(text)
        if not len(idx):
            return np.zeros(self.matrix.shape[0], dtype=np.float32)
        weights = (1.0 + np.log(counts)) * self.idf[idx]
        weights /= np.linalg.norm(weights) or 1.0
        sub = self.matrix[:, idx]
        return np.asarray(sub.dot(weights)).ravel().astype(np.float32)

    def vectors(self, rows: Sequence[int]):
        return self.matrix[list(rows)]


def ranking(scores: np.ndarray, candidates: np.ndarray, top: int) -> list[int]:
    """Indices of the best `top` candidates with a positive score, best first (ties: lower index first)."""
    idx = np.flatnonzero(candidates & (scores > 0))
    if not len(idx):
        return []
    order = np.lexsort((idx, -scores[idx]))
    return [int(i) for i in idx[order][:top]]


def rrf(rankings: dict[str, list[int]], k: int = 60, weights: dict[str, float] | None = None) -> dict[int, float]:
    """Reciprocal rank fusion: sum of w / (k + rank) over the signals (rank is 1-based)."""
    fused: dict[int, float] = {}
    for name, ranked in rankings.items():
        w = (weights or {}).get(name, 1.0)
        for rank, doc in enumerate(ranked, start=1):
            fused[doc] = fused.get(doc, 0.0) + w / (k + rank)
    return fused


def mmr(order: list[int], relevance: dict[int, float], similarity, k: int, lam: float = 0.7) -> list[int]:
    """Maximal marginal relevance over `order`. `similarity(i, j)` is a cosine in [0, 1]."""
    if not order:
        return []
    top = max(relevance.values()) or 1.0
    chosen: list[int] = []
    pool = list(order)
    while pool and len(chosen) < k:
        best, best_score = None, -1e9
        for doc in pool:
            rel = relevance[doc] / top
            div = max((similarity(doc, c) for c in chosen), default=0.0)
            score = lam * rel - (1 - lam) * div
            if score > best_score:
                best, best_score = doc, score
        chosen.append(best)  # type: ignore[arg-type]
        pool.remove(best)
    return chosen


def tokenize_all(texts: Sequence[str]) -> list[list[str]]:
    return [tokenize(t) for t in texts]
