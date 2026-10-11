import numpy as np
import pandas as pd
import pytest

faiss = pytest.importorskip("faiss")
pytest.importorskip("rank_bm25")

from data_generator import generate_corpus, generate_queries
from evaluator import precision_at_k, recall_at_k, mrr_at_k
from search_engine import reciprocal_rank_fusion, tokenize_ukrainian, SearchHit


def test_corpus_size_and_unique_texts():
    corpus = generate_corpus(560, seed=42)
    assert len(corpus) == 560
    assert corpus["text"].str.lower().nunique() == 560
    assert set(corpus["doc_type"]) == {
        "road_segment", "bus_route", "traffic_incident", "sensor_telemetry"
    }


def test_queries_have_at_least_three_relevant_documents():
    corpus = generate_corpus(560, seed=42)
    queries = generate_queries(corpus)
    assert len(queries) == 12
    assert all(q["relevant_count"] >= 3 for q in queries)


def test_metrics():
    relevant = {"D1", "D2", "D3"}
    retrieved = ["D9", "D2", "D8", "D3", "D1"]
    assert precision_at_k(retrieved, relevant, 5) == 3 / 5
    assert recall_at_k(retrieved, relevant, 5) == 1.0
    assert mrr_at_k(retrieved, relevant, 5) == 1 / 2


def test_tokenizer():
    tokens = tokenize_ukrainian("ДТП: 40 км/год, Городоцька!")
    assert "дтп" in tokens
    assert "40" in tokens
    assert "км" in tokens
    assert "год" in tokens


def test_rrf():
    a = [SearchHit("D1", 0.9, 1), SearchHit("D2", 0.8, 2)]
    b = [SearchHit("D2", 4.0, 1), SearchHit("D3", 3.0, 2)]
    fused = reciprocal_rank_fusion([a, b], rrf_k=60, top_k=3)
    assert fused[0].doc_id == "D2"
    assert [h.rank for h in fused] == [1, 2, 3]


def test_faiss_ip_small():
    rng = np.random.default_rng(42)
    vectors = rng.normal(size=(10, 8)).astype("float32")
    faiss.normalize_L2(vectors)
    index = faiss.IndexFlatIP(8)
    index.add(vectors)
    scores, ids = index.search(vectors[:1], 3)
    assert ids.shape == (1, 3)
    assert ids[0, 0] == 0
    assert scores[0, 0] > 0.999
