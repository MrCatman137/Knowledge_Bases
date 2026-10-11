"""Central configuration for the FAISS document-search laboratory."""

from pathlib import Path

# Reproducibility
RANDOM_SEED = 42
NUM_DOCUMENTS = 560

# Embedding model
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_BATCH_SIZE = 32
NORMALIZE_EMBEDDINGS = True

# Corpus / retrieval
TOP_K_VALUES = (5, 10)
HNSW_M = 32
HNSW_EF_CONSTRUCTION = 64
HNSW_EF_SEARCH_VALUES = (16, 32, 64, 128)
IVF_NLIST = 16
IVF_NPROBE_VALUES = (1, 2, 4, 8)
RRF_K = 60

# Benchmarking
LATENCY_WARMUP_RUNS = 2
LATENCY_REPEATS = 5
LATENCY_BATCH_SIZE = 1

# Paths
ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
INDEX_DIR = ROOT_DIR / "indexes"
OUTPUT_DIR = ROOT_DIR / "outputs"


LATENCY_BENCHMARK_CSV = OUTPUT_DIR / "latency_benchmark.csv"


CORPUS_PATH = DATA_DIR / "corpus.csv"
QUERIES_PATH = DATA_DIR / "queries.json"
EMBEDDINGS_PATH = DATA_DIR / "embeddings.npy"
BM25_PATH = DATA_DIR / "bm25_metadata.json"

FLAT_INDEX_PATH = INDEX_DIR / "index_flat_ip.faiss"
HNSW_INDEX_PATH = INDEX_DIR / "index_hnsw_flat.faiss"
IVF_INDEX_PATH = INDEX_DIR / "index_ivf_flat.faiss"
INDEX_META_PATH = INDEX_DIR / "index_metadata.json"

RESULTS_CSV = OUTPUT_DIR / "evaluation_results.csv"
INDEX_BENCHMARK_CSV = OUTPUT_DIR / "index_benchmark.csv"
LATENCY_CSV = OUTPUT_DIR / "latency_benchmark.csv"
SUMMARY_MD = OUTPUT_DIR / "summary.md"

for directory in (DATA_DIR, INDEX_DIR, OUTPUT_DIR):
    directory.mkdir(parents=True, exist_ok=True)
