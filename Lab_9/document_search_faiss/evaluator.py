"""Retrieval metrics and latency benchmarking."""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from typing import Callable, Iterable

import numpy as np


def precision_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    top = retrieved[:k]
    return sum(doc_id in relevant for doc_id in top) / k


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    return sum(doc_id in relevant for doc_id in retrieved[:k]) / len(relevant)


def mrr_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    for rank, doc_id in enumerate(retrieved[:k], start=1):
        if doc_id in relevant:
            return 1.0 / rank
    return 0.0


def evaluate_retrieval(
    retrieved: list[str], relevant_doc_ids: Iterable[str], k: int
) -> dict[str, float]:
    relevant = set(relevant_doc_ids)
    return {
        f"precision@{k}": precision_at_k(retrieved, relevant, k),
        f"recall@{k}": recall_at_k(retrieved, relevant, k),
        f"mrr@{k}": mrr_at_k(retrieved, relevant, k),
    }


@dataclass
class LatencyStats:
    average_ms: float
    p95_ms: float
    samples: int


def benchmark_latency(
    search_fn: Callable[[], object],
    warmup_runs: int = 2,
    repeats: int = 5,
) -> LatencyStats:
    if repeats <= 0:
        raise ValueError("repeats має бути > 0.")
    for _ in range(max(0, warmup_runs)):
        search_fn()

    measurements = []
    for _ in range(repeats):
        start = time.perf_counter_ns()
        search_fn()
        measurements.append((time.perf_counter_ns() - start) / 1_000_000)

    return LatencyStats(
        average_ms=float(statistics.fmean(measurements)),
        p95_ms=float(np.percentile(measurements, 95)),
        samples=len(measurements),
    )
