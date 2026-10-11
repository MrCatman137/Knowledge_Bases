"""Dense FAISS, BM25, and RRF hybrid retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

import faiss
import numpy as np
from rank_bm25 import BM25Okapi

from config import RRF_K


def tokenize_ukrainian(text: str) -> list[str]:
    """Simple deterministic tokenizer suitable for this synthetic corpus."""
    text = text.lower().replace("’", "'")
    return re.findall(r"[a-zа-яіїєґ0-9]+", text)


@dataclass
class SearchHit:
    doc_id: str
    score: float
    rank: int


class DenseSearcher:
    def __init__(self, index: faiss.Index, doc_ids: list[str], query_encoder):
        if index.ntotal != len(doc_ids):
            raise ValueError("Кількість документів у FAISS та doc_ids не збігається.")
        self.index = index
        self.doc_ids = doc_ids
        self.query_encoder = query_encoder

    def search(self, query: str, k: int = 10) -> list[SearchHit]:
        if k <= 0:
            return []
        vector = self.query_encoder.encode([query])[0].astype("float32")
        scores, ids = self.index.search(vector.reshape(1, -1), min(k, self.index.ntotal))
        hits = []
        for rank, (score, idx) in enumerate(zip(scores[0], ids[0]), start=1):
            if idx < 0:
                continue
            hits.append(SearchHit(self.doc_ids[int(idx)], float(score), rank))
        return hits


class BM25Searcher:
    def __init__(self, doc_ids: list[str], texts: list[str]):
        if len(doc_ids) != len(texts):
            raise ValueError("doc_ids та texts повинні мати однакову довжину.")
        self.doc_ids = doc_ids
        self.tokenized_corpus = [tokenize_ukrainian(t) for t in texts]
        self.bm25 = BM25Okapi(self.tokenized_corpus)

    def search(self, query: str, k: int = 10) -> list[SearchHit]:
        if k <= 0:
            return []
        scores = self.bm25.get_scores(tokenize_ukrainian(query))
        order = np.argsort(-scores, kind="stable")[: min(k, len(scores))]
        return [
            SearchHit(self.doc_ids[int(idx)], float(scores[int(idx)]), rank)
            for rank, idx in enumerate(order, start=1)
        ]


def reciprocal_rank_fusion(
    result_lists: Iterable[list[SearchHit]],
    rrf_k: int = RRF_K,
    top_k: int = 10,
) -> list[SearchHit]:
    """RRF score(d) = sum_r 1 / (rrf_k + rank_r(d)), with rank starting at 1."""
    if rrf_k <= 0:
        raise ValueError("rrf_k має бути додатним.")
    scores: dict[str, float] = {}
    for hits in result_lists:
        for hit in hits:
            scores[hit.doc_id] = scores.get(hit.doc_id, 0.0) + 1.0 / (rrf_k + hit.rank)

    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:top_k]
    return [
        SearchHit(doc_id, score, rank)
        for rank, (doc_id, score) in enumerate(ranked, start=1)
    ]


class HybridSearcher:
    def __init__(self, dense: DenseSearcher, bm25: BM25Searcher, rrf_k: int = RRF_K):
        self.dense = dense
        self.bm25 = bm25
        self.rrf_k = rrf_k

    def search(self, query: str, k: int = 10) -> list[SearchHit]:
        dense_hits = self.dense.search(query, k=k)
        lexical_hits = self.bm25.search(query, k=k)
        return reciprocal_rank_fusion([dense_hits, lexical_hits], self.rrf_k, k)


def configure_faiss_search(index: faiss.Index, parameter: int) -> None:
    """Set HNSW efSearch or IVF nprobe; harmless for Flat."""
    if hasattr(index, "hnsw"):
        index.hnsw.efSearch = int(parameter)
    elif hasattr(index, "nprobe"):
        index.nprobe = int(parameter)
