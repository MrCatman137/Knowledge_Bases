"""Embedding generation and FAISS index construction/persistence."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from config import (
    EMBEDDING_BATCH_SIZE,
    FLAT_INDEX_PATH,
    HNSW_EF_CONSTRUCTION,
    HNSW_INDEX_PATH,
    HNSW_M,
    INDEX_META_PATH,
    INDEX_DIR,
    IVF_INDEX_PATH,
    IVF_NLIST,
    MODEL_NAME,
    NORMALIZE_EMBEDDINGS,
)


@dataclass
class IndexBuildResult:
    index_name: str
    path: str
    build_time_ms: float
    file_size_bytes: int
    dimension: int
    ntotal: int


class EmbeddingModel:
    """Lazy wrapper around SentenceTransformer."""

    def __init__(self, model_name: str = MODEL_NAME):
        self.model_name = model_name
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(self, texts: list[str], batch_size: int = EMBEDDING_BATCH_SIZE) -> np.ndarray:
        vectors = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=True,
            convert_to_numpy=True,
        ).astype("float32")
        if NORMALIZE_EMBEDDINGS:
            faiss.normalize_L2(vectors)
        return vectors


def save_embeddings(embeddings: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, embeddings)


def load_embeddings(path: Path) -> np.ndarray:
    if not path.exists():
        raise FileNotFoundError(f"Не знайдено embeddings: {path}")
    return np.load(path).astype("float32")


def _write_index(index: faiss.Index, path: Path) -> tuple[float, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    faiss.write_index(index, str(path))
    elapsed_ms = (time.perf_counter() - started) * 1000
    return elapsed_ms, path.stat().st_size


def build_flat_ip(embeddings: np.ndarray, path: Path = FLAT_INDEX_PATH) -> IndexBuildResult:
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    started = time.perf_counter()
    index.add(embeddings)
    build_ms = (time.perf_counter() - started) * 1000
    faiss.write_index(index, str(path))
    return IndexBuildResult("IndexFlatIP", str(path), build_ms, path.stat().st_size, dim, index.ntotal)


def build_hnsw(embeddings: np.ndarray, path: Path = HNSW_INDEX_PATH) -> IndexBuildResult:
    dim = embeddings.shape[1]
    index = faiss.IndexHNSWFlat(dim, HNSW_M, faiss.METRIC_INNER_PRODUCT)
    index.hnsw.efConstruction = HNSW_EF_CONSTRUCTION
    started = time.perf_counter()
    index.add(embeddings)
    build_ms = (time.perf_counter() - started) * 1000
    faiss.write_index(index, str(path))
    return IndexBuildResult("IndexHNSWFlat", str(path), build_ms, path.stat().st_size, dim, index.ntotal)


def build_ivf(embeddings: np.ndarray, path: Path = IVF_INDEX_PATH) -> IndexBuildResult:
    dim = embeddings.shape[1]
    quantizer = faiss.IndexFlatIP(dim)
    index = faiss.IndexIVFFlat(quantizer, dim, IVF_NLIST, faiss.METRIC_INNER_PRODUCT)
    started = time.perf_counter()
    index.train(embeddings)
    index.add(embeddings)
    build_ms = (time.perf_counter() - started) * 1000
    faiss.write_index(index, str(path))
    return IndexBuildResult("IndexIVFFlat", str(path), build_ms, path.stat().st_size, dim, index.ntotal)


def build_all_indexes(embeddings: np.ndarray) -> list[IndexBuildResult]:
    results = [
        build_flat_ip(embeddings),
        build_hnsw(embeddings),
        build_ivf(embeddings),
    ]
    INDEX_META_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_META_PATH.write_text(
        json.dumps([asdict(x) for x in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return results


def load_index(path: Path) -> faiss.Index:
    if not path.exists():
        raise FileNotFoundError(f"FAISS index не знайдено: {path}")
    return faiss.read_index(str(path))
