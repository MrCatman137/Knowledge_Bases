"""
Самостійна робота №16: "Тестування рекомендаційної системи"
Предметна область: "Цифрові моделі транспортних систем"

Експериментальний пайплайн:
1. Завантаження датасету та онтологічних ознак.
2. Протокол Leave-One-Out Temporal Split (User-stratified).
3. Оцінювання моделей: Top-Popular, Content-Based (OWL), SVD при k in {5, 10}.
4. Експеримент на стійкість: деградація при 50% даних у Train (Data Sparsity Stress Test).
5. Абляційний аналіз: вплив кількості прихованих факторів SVD (d in {2, 5, 10, 20}).
6. Статистична перевірка значущості: парний t-тест по nDCG@10 між моделями.
7. Візуалізація результатів у PNG-файли для звіту.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from run_lab16_recommender import (
    extract_ontology_items_and_features,
    leave_one_out_split,
    TopPopularRecommender,
    ContentBasedRecommender,
    SVDCollaborativeRecommender,
    ONTOLOGY_PATH,
    DATASET_CSV,
)

# Фіксація випадкових послідовностей
random.seed(42)
np.random.seed(42)

K_VALUES = [5, 10]


@dataclass
class ExtendedMetrics:
    precision: float
    recall: float
    map_score: float
    ndcg: float
    coverage: float
    novelty: float


def compute_extended_metrics(
    recommender,
    test_df: pd.DataFrame,
    train_df: pd.DataFrame,
    all_items: List[str],
    k: int = 10,
    item_frequencies: Dict[str, float] = None
) -> Tuple[ExtendedMetrics, Dict[str, float]]:
    """
    Рахує Precision, Recall, MAP, nDCG, Coverage, Novelty та зберігає nDCG для кожного користувача.
    """
    test_grouped = test_df.groupby("user_id")["item_id"].apply(set).to_dict()
    train_grouped = train_df.groupby("user_id")["item_id"].apply(set).to_dict()

    precisions, recalls, map_list, ndcg_list = [], [], [], []
    user_ndcg_map: Dict[str, float] = {}
    recommended_unique_items = set()
    novelty_scores = []

    total_train_interactions = sum(item_frequencies.values()) if item_frequencies else 1.0

    for uid, relevant_items in test_grouped.items():
        seen = train_grouped.get(uid, set())
        raw_recs = recommender.recommend(uid, k, seen)
        
        recs = [itm[0] if isinstance(itm, tuple) else itm for itm in raw_recs][:k]

        for itm in recs:
            recommended_unique_items.add(itm)
            if item_frequencies and itm in item_frequencies:
                prob = max(item_frequencies[itm] / total_train_interactions, 1e-6)
                novelty_scores.append(-math.log2(prob))

        # Precision & Recall
        hits = len(set(recs).intersection(relevant_items))
        precisions.append(hits / k)
        recalls.append(hits / len(relevant_items) if relevant_items else 0.0)

        # Average Precision (AP@k)
        score_ap = 0.0
        running_hits = 0
        for i, pred_item in enumerate(recs):
            if pred_item in relevant_items:
                running_hits += 1
                score_ap += running_hits / (i + 1)
        map_list.append(score_ap / min(len(relevant_items), k) if relevant_items else 0.0)

        # nDCG@k
        dcg = 0.0
        for i, pred_item in enumerate(recs):
            if pred_item in relevant_items:
                dcg += 1.0 / math.log2((i + 1) + 1)
        idcg = sum(1.0 / math.log2((r + 1) + 1) for r in range(min(len(relevant_items), k)))
        u_ndcg = dcg / idcg if idcg > 0 else 0.0
        ndcg_list.append(u_ndcg)
        user_ndcg_map[uid] = u_ndcg

    coverage = len(recommended_unique_items) / len(all_items) if all_items else 0.0
    novelty = float(np.mean(novelty_scores)) if novelty_scores else 0.0

    return ExtendedMetrics(
        precision=float(np.mean(precisions)),
        recall=float(np.mean(recalls)),
        map_score=float(np.mean(map_list)),
        ndcg=float(np.mean(ndcg_list)),
        coverage=coverage,
        novelty=novelty
    ), user_ndcg_map


def main():
    print("=" * 90)
    print("  САМОСТІЙНА РОБОТА №16: ТЕСТУВАННЯ ТА ОФЛАЙН-ОЦІНЮВАННЯ РЕКОМЕНДАЦІЙНОЇ СИСТЕМИ")
    print("=" * 90)

    # 1. Завантаження даних
    if not DATASET_CSV.exists():
        raise FileNotFoundError(f"Файл {DATASET_CSV} не знайдено. Спочатку запустіть run_lab16_recommender.py!")
    
    ratings_df = pd.read_csv(DATASET_CSV)
    items_df = extract_ontology_items_and_features(ONTOLOGY_PATH)
    all_item_ids = items_df["item_id"].tolist()

    # Розрахунок частот елементів для метрики Novelty
    item_freqs = ratings_df["item_id"].value_counts().to_dict()

    # 2. Розбиття Leave-One-Out
    train_df, val_df, test_df = leave_one_out_split(ratings_df)
    print(f"\n[Протокол] Temporal Leave-One-Out: Train={len(train_df)}, Val={len(val_df)}, Test={len(test_df)}.")

    # 3. Базове тренування моделей
    pop_model = TopPopularRecommender()
    pop_model.fit(train_df)

    cb_model = ContentBasedRecommender(items_df)
    cb_model.fit(train_df)

    svd_model = SVDCollaborativeRecommender(n_factors=10, lr=0.015, reg=0.05, n_epochs=50)
    svd_model.fit(train_df, all_item_ids)

    # 4. Розрахунок метрик для k in {5, 10}
    models = {
        "Top-Popular": pop_model,
        "Content-Based (OWL)": cb_model,
        "SVD (Factors=10)": svd_model
    }

    full_eval_results = {}
    user_ndcgs = {}

    print("\n" + "=" * 90)
    print("  ТАБЛИЦЯ 1: МЕТРИКИ РАНЖУВАННЯ ПРИ k ∈ {5, 10}")
    print("=" * 90)
    print(f"{'Модель':<22} | {'k':>2} | {'P@k':>7} | {'R@k':>7} | {'MAP@k':>7} | {'nDCG@k':>7} | {'Coverage':>8} | {'Novelty':>7}")
    print("-" * 90)

    for name, model in models.items():
        for k in K_VALUES:
            metrics, u_map = compute_extended_metrics(model, test_df, train_df, all_item_ids, k=k, item_frequencies=item_freqs)
            full_eval_results[(name, k)] = metrics
            if k == 10:
                user_ndcgs[name] = u_map
            print(f"{name:<22} | {k:>2} | {metrics.precision:>7.4f} | {metrics.recall:>7.4f} | {metrics.map_score:>7.4f} | {metrics.ndcg:>7.4f} | {metrics.coverage:>7.1%} | {metrics.novelty:>7.2f}")

    # 5. Експеримент на стійкість: Subsample 50% Train (Скудні дані)
    print("\n" + "=" * 90)
    print("  ЕКСПЕРИМЕНТ НА СТІЙКІСТЬ: ДЕГРАДАЦІЯ ПРИ 50% ДАНИХ (SPARSITY TEST)")
    print("=" * 90)
    train_50 = train_df.sample(frac=0.5, random_state=42).reset_index(drop=True)
    
    cb_50 = ContentBasedRecommender(items_df)
    cb_50.fit(train_50)

    svd_50 = SVDCollaborativeRecommender(n_factors=10, lr=0.015, reg=0.05, n_epochs=50)
    svd_50.fit(train_50, all_item_ids)

    m_cb_full = full_eval_results[("Content-Based (OWL)", 10)]
    m_cb_50, _ = compute_extended_metrics(cb_50, test_df, train_50, all_item_ids, k=10, item_frequencies=item_freqs)

    m_svd_full = full_eval_results[("SVD (Factors=10)", 10)]
    m_svd_50, _ = compute_extended_metrics(svd_50, test_df, train_50, all_item_ids, k=10, item_frequencies=item_freqs)

    print(f"Content-Based nDCG@10: 100% Train = {m_cb_full.ndcg:.4f}  -->  50% Train = {m_cb_50.ndcg:.4f} (Спад: {((m_cb_full.ndcg - m_cb_50.ndcg) / m_cb_full.ndcg)*100:.1f}%)")
    print(f"SVD           nDCG@10: 100% Train = {m_svd_full.ndcg:.4f}  -->  50% Train = {m_svd_50.ndcg:.4f} (Спад: {((m_svd_full.ndcg - m_svd_50.ndcg) / m_svd_full.ndcg)*100:.1f}%)")

    # 6. Абляційний аналіз: Вплив кількості прихованих факторів (d)
    print("\n" + "=" * 90)
    print("  АБЛЯЦІЙНИЙ АНАЛІЗ: ВПЛИВ КІЛЬКОСТІ ФАКТОРІВ SVD (d in {2, 5, 10, 20})")
    print("=" * 90)
    factors_list = [2, 5, 10, 20]
    ablation_ndcg = []
    
    for f in factors_list:
        model_ab = SVDCollaborativeRecommender(n_factors=f, lr=0.015, reg=0.05, n_epochs=50)
        model_ab.fit(train_df, all_item_ids)
        m_ab, _ = compute_extended_metrics(model_ab, test_df, train_df, all_item_ids, k=10, item_frequencies=item_freqs)
        ablation_ndcg.append(m_ab.ndcg)
        print(f"  • Факторів d = {f:>2} --> nDCG@10 = {m_ab.ndcg:.4f}, Coverage = {m_ab.coverage:.1%}")

    # 7. Статистична перевірка значущості (Paired t-test по nDCG@10)
    print("\n" + "=" * 90)
    print("  СТАТИСТИЧНА ПЕРЕВІРКА ЗНАЧУЩОСТІ (PAIRED t-TEST)")
    print("=" * 90)
    common_users = sorted(list(set(user_ndcgs["Content-Based (OWL)"].keys()).intersection(user_ndcgs["Top-Popular"].keys())))
    scores_cb = [user_ndcgs["Content-Based (OWL)"][u] for u in common_users]
    scores_pop = [user_ndcgs["Top-Popular"][u] for u in common_users]
    scores_svd = [user_ndcgs["SVD (Factors=10)"][u] for u in common_users]

    t_stat_cb_pop, p_val_cb_pop = stats.ttest_rel(scores_cb, scores_pop)
    t_stat_cb_svd, p_val_cb_svd = stats.ttest_rel(scores_cb, scores_svd)

    print(f"Content-Based vs Top-Popular : t-statistic = {t_stat_cb_pop:.4f}, p-value = {p_val_cb_pop:.4e}")
    if p_val_cb_pop < 0.05:
        print("  -> Різниця є статистично значущою (p < 0.05), перевага онтологічної моделі підтверджена.")

    print(f"Content-Based vs SVD         : t-statistic = {t_stat_cb_svd:.4f}, p-value = {p_val_cb_svd:.4e}")
    if p_val_cb_svd < 0.05:
        print("  -> Різниця є статистично значущою (p < 0.05).")

    # 8. Побудова графіків для звіту
    plt.figure(figsize=(10, 4))
    
    # Графік 1: nDCG@5 vs nDCG@10
    plt.subplot(1, 2, 1)
    models_names = ["Top-Popular", "Content-Based", "SVD"]
    ndcg_5 = [full_eval_results[(m, 5)].ndcg for m in ["Top-Popular", "Content-Based (OWL)", "SVD (Factors=10)"]]
    ndcg_10 = [full_eval_results[(m, 10)].ndcg for m in ["Top-Popular", "Content-Based (OWL)", "SVD (Factors=10)"]]
    
    x = np.arange(len(models_names))
    width = 0.35
    plt.bar(x - width/2, ndcg_5, width, label='nDCG@5', color='#4dabf7')
    plt.bar(x + width/2, ndcg_10, width, label='nDCG@10', color='#1864ab')
    plt.ylabel('nDCG Score')
    plt.title('Порівняння nDCG при k ∈ {5, 10}')
    plt.xticks(x, models_names)
    plt.legend()
    plt.grid(axis='y', linestyle='--', alpha=0.7)

    # Графік 2: Абляційний графік
    plt.subplot(1, 2, 2)
    plt.plot(factors_list, ablation_ndcg, marker='o', linewidth=2, color='#e03131')
    plt.xlabel('Кількість латентних факторів (d)')
    plt.ylabel('nDCG@10')
    plt.title('Абляція: вплив гіперпараметра d у SVD')
    plt.grid(True, linestyle='--', alpha=0.7)

    plt.tight_layout()
    plot_file = Path("sr16_eval_plots.png")
    plt.savefig(plot_file, dpi=300)
    print(f"\n[Графіки] Збережено візуалізації до: {plot_file}")
    print("=" * 90)


if __name__ == "__main__":
    main()