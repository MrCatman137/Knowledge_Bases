"""End-to-end runner for the Document Search in FAISS Vector Database lab."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import faiss
import numpy as np
import pandas as pd
from tabulate import tabulate

from config import (
    EMBEDDINGS_PATH,
    FLAT_INDEX_PATH,
    HNSW_EF_SEARCH_VALUES,
    HNSW_INDEX_PATH,
    INDEX_BENCHMARK_CSV,
    INDEX_DIR,
    INDEX_META_PATH,
    IVF_INDEX_PATH,
    IVF_NPROBE_VALUES,
    LATENCY_BENCHMARK_CSV,
    LATENCY_REPEATS,
    LATENCY_WARMUP_RUNS,
    OUTPUT_DIR,
    RESULTS_CSV,
    SUMMARY_MD,
    TOP_K_VALUES,
)
from data_generator import build_dataset
from evaluator import benchmark_latency, evaluate_retrieval
from indexer import EmbeddingModel, build_all_indexes, load_embeddings, load_index, save_embeddings
from search_engine import BM25Searcher, DenseSearcher, HybridSearcher, configure_faiss_search


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild", action="store_true", help="Regenerate data, embeddings and indexes.")
    parser.add_argument("--num-documents", type=int, default=560, choices=range(500, 601))
    return parser.parse_args()


def ensure_dataset(rebuild: bool, num_documents: int):
    from config import CORPUS_PATH, QUERIES_PATH
    if rebuild or not CORPUS_PATH.exists() or not QUERIES_PATH.exists():
        return build_dataset(num_documents=num_documents)
    corpus = pd.read_csv(CORPUS_PATH)
    queries = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))
    return corpus, queries


def ensure_embeddings(corpus: pd.DataFrame, rebuild: bool) -> np.ndarray:
    if not rebuild and EMBEDDINGS_PATH.exists():
        return load_embeddings(EMBEDDINGS_PATH)
    model = EmbeddingModel()
    embeddings = model.encode(corpus["text"].tolist())
    save_embeddings(embeddings, EMBEDDINGS_PATH)
    return embeddings


def ensure_indexes(embeddings: np.ndarray, rebuild: bool):
    expected = [FLAT_INDEX_PATH, HNSW_INDEX_PATH, IVF_INDEX_PATH]
    if rebuild or not all(p.exists() for p in expected):
        return build_all_indexes(embeddings)
    metadata = json.loads(INDEX_META_PATH.read_text(encoding="utf-8"))
    return metadata


def load_query_encoder():
    return EmbeddingModel()


def run_experiments(corpus: pd.DataFrame, queries: list[dict], encoder: EmbeddingModel) -> tuple[pd.DataFrame, pd.DataFrame]:
    doc_ids = corpus["doc_id"].tolist()
    texts = corpus["text"].tolist()
    bm25 = BM25Searcher(doc_ids, texts)

    indexes = {
        "IndexFlatIP": load_index(FLAT_INDEX_PATH),
        "IndexHNSWFlat": load_index(HNSW_INDEX_PATH),
        "IndexIVFFlat": load_index(IVF_INDEX_PATH),
    }

    experiment_rows = []
    latency_rows = []

    for index_name, index in indexes.items():
        parameter_values = [None]
        if index_name == "IndexHNSWFlat":
            parameter_values = list(HNSW_EF_SEARCH_VALUES)
        elif index_name == "IndexIVFFlat":
            parameter_values = list(IVF_NPROBE_VALUES)

        for parameter in parameter_values:
            if parameter is not None:
                configure_faiss_search(index, parameter)

            dense = DenseSearcher(index, doc_ids, encoder)
            hybrid = HybridSearcher(dense, bm25)

            for k in TOP_K_VALUES:
                for query_record in queries:
                    qid = query_record["query_id"]
                    query = query_record["query"]
                    relevant = query_record["relevant_doc_ids"]

                    dense_hits = dense.search(query, k)
                    dense_ids = [h.doc_id for h in dense_hits]
                    metrics = evaluate_retrieval(dense_ids, relevant, k)
                    experiment_rows.append({
                        "method": "dense",
                        "index": index_name,
                        "parameter": parameter,
                        "query_id": qid,
                        "k": k,
                        **metrics,
                    })

                    # BM25 is independent of FAISS and is recorded once per KQ/k.
                    if index_name == "IndexFlatIP" and parameter is None:
                        bm25_hits = bm25.search(query, k)
                        bm25_ids = [h.doc_id for h in bm25_hits]
                        metrics = evaluate_retrieval(bm25_ids, relevant, k)
                        experiment_rows.append({
                            "method": "bm25",
                            "index": "N/A",
                            "parameter": None,
                            "query_id": qid,
                            "k": k,
                            **metrics,
                        })

                    hybrid_hits = hybrid.search(query, k)
                    hybrid_ids = [h.doc_id for h in hybrid_hits]
                    metrics = evaluate_retrieval(hybrid_ids, relevant, k)
                    experiment_rows.append({
                        "method": "hybrid_rrf",
                        "index": index_name,
                        "parameter": parameter,
                        "query_id": qid,
                        "k": k,
                        **metrics,
                    })

                # Query-level latency over all KQs, measured independently.
                query_set = [q["query"] for q in queries]
                dense_latency = benchmark_latency(
                    lambda: [dense.search(q, k) for q in query_set],
                    LATENCY_WARMUP_RUNS, LATENCY_REPEATS,
                )
                hybrid_latency = benchmark_latency(
                    lambda: [hybrid.search(q, k) for q in query_set],
                    LATENCY_WARMUP_RUNS, LATENCY_REPEATS,
                )
                latency_rows.extend([
                    {
                        "method": "dense",
                        "index": index_name,
                        "parameter": parameter,
                        "k": k,
                        "average_ms_all_queries": dense_latency.average_ms,
                        "p95_ms_all_queries": dense_latency.p95_ms,
                        "samples": dense_latency.samples,
                    },
                    {
                        "method": "hybrid_rrf",
                        "index": index_name,
                        "parameter": parameter,
                        "k": k,
                        "average_ms_all_queries": hybrid_latency.average_ms,
                        "p95_ms_all_queries": hybrid_latency.p95_ms,
                        "samples": hybrid_latency.samples,
                    },
                ])

    # BM25 latency is independent of FAISS.
    for k in TOP_K_VALUES:
        query_set = [q["query"] for q in queries]
        stats = benchmark_latency(
            lambda: [bm25.search(q, k) for q in query_set],
            LATENCY_WARMUP_RUNS, LATENCY_REPEATS,
        )
        latency_rows.append({
            "method": "bm25",
            "index": "N/A",
            "parameter": None,
            "k": k,
            "average_ms_all_queries": stats.average_ms,
            "p95_ms_all_queries": stats.p95_ms,
            "samples": stats.samples,
        })

    return pd.DataFrame(experiment_rows), pd.DataFrame(latency_rows)


def build_summary(results: pd.DataFrame, index_benchmark: pd.DataFrame, latency: pd.DataFrame) -> str:
    # The columns above are sparse because each row contains only its own k.
    # Produce a simpler per-k summary instead.
    compact = (
        results.groupby(["method", "index", "parameter", "k"], dropna=False)
        [["precision@" + str(k) for k in TOP_K_VALUES] +
         ["recall@" + str(k) for k in TOP_K_VALUES] +
         ["mrr@" + str(k) for k in TOP_K_VALUES]]
        .mean(numeric_only=True)
    )
    lines = [
        "# Benchmark Summary",
        "",
        "## Index build",
        "",
        index_benchmark.to_markdown(index=False),
        "",
        "## Retrieval quality",
        "",
        compact.to_markdown(),
        "",
        "## Latency",
        "",
        latency.to_markdown(index=False),
        "",
        "Metrics are macro-averaged across the 12 competency queries. "
        "Latency includes query encoding for dense methods.",
    ]
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    corpus, queries = ensure_dataset(args.rebuild, args.num_documents)
    embeddings = ensure_embeddings(corpus, args.rebuild)
    build_info = ensure_indexes(embeddings, args.rebuild)

    if isinstance(build_info[0], dict):
        index_benchmark = pd.DataFrame(build_info)
    else:
        from dataclasses import asdict
        index_benchmark = pd.DataFrame([asdict(x) for x in build_info])
    index_benchmark.to_csv(INDEX_BENCHMARK_CSV, index=False)

    encoder = load_query_encoder()
    results, latency = run_experiments(corpus, queries, encoder)

    results.to_csv(RESULTS_CSV, index=False)
    latency.to_csv(LATENCY_BENCHMARK_CSV, index=False)
    SUMMARY_MD.write_text(build_summary(results, index_benchmark, latency), encoding="utf-8")

    print("\n=== Index build benchmark ===")
    print(tabulate(index_benchmark, headers="keys", tablefmt="github", showindex=False))
    print("\n=== Macro retrieval metrics by method/index/parameter/k ===")
    summary = (
        results.groupby(["method", "index", "parameter", "k"], dropna=False)
        [["precision@" + str(k) for k in TOP_K_VALUES] +
         ["recall@" + str(k) for k in TOP_K_VALUES] +
         ["mrr@" + str(k) for k in TOP_K_VALUES]]
        .mean(numeric_only=True)
    )
    print(tabulate(summary.reset_index(), headers="keys", tablefmt="github", showindex=False))
    print("\n=== Latency ===")
    print(tabulate(latency, headers="keys", tablefmt="github", showindex=False))
    print(f"\nГотово. Результати збережено у: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
