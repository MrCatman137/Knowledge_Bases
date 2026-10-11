import pandas as pd
import faiss
from sentence_transformers import SentenceTransformer
from search_engine import BM25Searcher
import config

print("Завантаження даних та індексів...")
corpus_df = pd.read_csv(config.CORPUS_PATH)
doc_ids = corpus_df["doc_id"].tolist()
texts = corpus_df["text"].tolist()

embedder = SentenceTransformer(config.MODEL_NAME)

# Завантаження збережених індексів FAISS
index_flat = faiss.read_index(str(config.INDEX_DIR / "index_flat_ip.faiss"))
index_hnsw = faiss.read_index(str(config.INDEX_DIR / "index_hnsw_flat.faiss"))
index_ivf = faiss.read_index(str(config.INDEX_DIR / "index_ivf_flat.faiss"))

# Лексичний BM25 пошукач
bm25_searcher = BM25Searcher(doc_ids=doc_ids, texts=texts)

def get_hit_attr(hit, attr_name):
    """Універсальне вилучення атрибута з SearchHit або словника"""
    if hasattr(hit, attr_name):
        return getattr(hit, attr_name)
    if isinstance(hit, dict):
        return hit[attr_name]
    return hit[0] if attr_name == "doc_id" else hit[1]

def run_demo(query_text: str, k: int = 3, rrf_k: int = 60):
    print("\n" + "=" * 90)
    print(f"ПОШУКОВИЙ ЗАПИТ: «{query_text}» (top-{k})")
    print("=" * 90)

    # 1. Векторизація та L2-нормалізація запиту
    q_vec = embedder.encode([query_text], convert_to_numpy=True)
    faiss.normalize_L2(q_vec)

    # 2. Точний векторний пошук (IndexFlatIP)
    scores_flat, ids_flat = index_flat.search(q_vec, 20)
    print("\n--- [1] IndexFlatIP (Точний векторний перебір) ---")
    for rank in range(k):
        idx = ids_flat[0][rank]
        score = scores_flat[0][rank]
        print(f" {rank+1}. [{doc_ids[idx]}] (Cosine: {score:.4f}) -> {texts[idx]}")

    # 3. Графовий векторний пошук (IndexHNSWFlat, efSearch=32)
    index_hnsw.hnsw.efSearch = 32
    scores_hnsw, ids_hnsw = index_hnsw.search(q_vec, k)
    print("\n--- [2] IndexHNSWFlat (Графовий ANN, efSearch=32) ---")
    for rank in range(k):
        idx = ids_hnsw[0][rank]
        score = scores_hnsw[0][rank]
        print(f" {rank+1}. [{doc_ids[idx]}] (Cosine: {score:.4f}) -> {texts[idx]}")

    # 4. Кластеризований векторний пошук (IndexIVFFlat, nprobe=2)
    index_ivf.nprobe = 2
    scores_ivf, ids_ivf = index_ivf.search(q_vec, k)
    print("\n--- [3] IndexIVFFlat (Кластерний ANN, nprobe=2) ---")
    for rank in range(k):
        idx = ids_ivf[0][rank]
        score = scores_ivf[0][rank]
        print(f" {rank+1}. [{doc_ids[idx]}] (Cosine: {score:.4f}) -> {texts[idx]}")

    # 5. Лексичний пошук BM25
    bm_res = bm25_searcher.search(query_text, k=20)
    print("\n--- [4] Чистий BM25 (Лексичний інвертований індекс) ---")
    for rank, item in enumerate(bm_res[:k], 1):
        d_id = get_hit_attr(item, "doc_id")
        score = get_hit_attr(item, "score")
        idx = doc_ids.index(d_id)
        print(f" {rank}. [{d_id}] (BM25: {score:.4f}) -> {texts[idx]}")

    # 6. Гібридний пошук Reciprocal Rank Fusion (RRF)
    rrf_scores = {}
    for rank_idx, idx in enumerate(ids_flat[0]):
        d_id = doc_ids[idx]
        rrf_scores[d_id] = rrf_scores.get(d_id, 0.0) + (1.0 / (rrf_k + rank_idx + 1))

    for rank_idx, item in enumerate(bm_res):
        d_id = get_hit_attr(item, "doc_id")
        rrf_scores[d_id] = rrf_scores.get(d_id, 0.0) + (1.0 / (rrf_k + rank_idx + 1))

    sorted_rrf = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:k]

    print(f"\n--- [5] Гібридний пошук RRF (FAISS + BM25, k_rrf={rrf_k}) ---")
    for rank, (d_id, rrf_val) in enumerate(sorted_rrf, 1):
        idx = doc_ids.index(d_id)
        print(f" {rank}. [{d_id}] (RRF: {rrf_val:.5f}) -> {texts[idx]}")

if __name__ == "__main__":
    # Демонстрація 1: Семантичний запит (події та спад швидкості)
    run_demo("ДТП та дорожні події з уповільненням потоку", k=3)

    # Демонстрація 2: Пошук точної сутності (автобус 24)
    run_demo("Автобус маршрут номер 24 курсування", k=3)