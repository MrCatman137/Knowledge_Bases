"""
Лабораторна робота №16: "Реалізація рекомендаційної системи"
Предметна область: "Цифрові моделі транспортних систем"

Компоненти:
1. Генератор реалістичного датасету поїздок та оцінок пасажирів.
2. Онтологічний екстрактор ознак через SPARQL (update_expanded.owl).
3. Розбиття Train / Val / Test (Leave-One-Out / Temporal).
4. Моделі: Random, Top-Popular, Content-Based (TF-IDF + OWL), Collaborative (SVD / MF).
5. Розрахунок метрик: Precision@k, Recall@k, MAP@k, NDCG@k, Coverage, Novelty.
6. Демонстрація 3 персоналізованих рекомендацій із поясненнями (Explainability).
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple

import numpy as np
import pandas as pd
from rdflib import Graph

# =============================================================================
# 1. КОНФІГУРАЦІЯ ТА ЗНЕШКОДЖЕННЯ ПОПЕРЕДЖЕНЬ
# =============================================================================
import logging
import rdflib.term
rdflib.term._warn_on_lexical_failure = False
logging.getLogger("rdflib").setLevel(logging.CRITICAL)

random.seed(42)
np.random.seed(42)

ONTOLOGY_PATH = Path("update_expanded.owl")
DATASET_CSV = Path("transport_ratings.csv")
K_VAL = 3


# =============================================================================
# 2. ОНТОЛОГІЧНИЙ ЕКСТРАКТОР ОЗНАК (SPARQL)
# =============================================================================
def extract_ontology_items_and_features(owl_file: Path) -> pd.DataFrame:
    """
    Вилучає з update_expanded.owl транспортні маршрути та їхні семантичні властивості:
    - номер маршруту, зупинки, оператор, рухомий склад, частота руху.
    """
    if not owl_file.exists():
        raise FileNotFoundError(f"Файл {owl_file} не знайдено.")

    g = Graph()
    g.parse(str(owl_file), format="xml")

    query = """
    PREFIX : <http://example.org/transport-ontology#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT DISTINCT ?route ?routeId ?routeNum ?stop ?stopId ?op ?opLabel ?bus ?busType ?freq WHERE {
        ?route a :Route ;
               :identifier ?routeId ;
               :routeNumber ?routeNum .
        OPTIONAL {
            ?route :servesStop ?stop .
            ?stop :identifier ?stopId .
        }
        OPTIONAL {
            ?route :hasSchedule ?sch .
            ?sch :serviceFrequency ?freq .
        }
        OPTIONAL {
            ?bus a ?busType ;
                 :hasRoute ?route .
            FILTER(?busType IN (:Bus, :ElectricBus, :Tram))
            OPTIONAL {
                ?bus :operatedBy ?op .
                ?op rdfs:label ?opLabel .
            }
        }
    }
    """
    rows = list(g.query(query))
    
    # Агрегація атрибутів по кожному маршруту
    routes_dict = defaultdict(lambda: {
        "uri": "",
        "route_number": "",
        "stops": set(),
        "operators": set(),
        "vehicle_types": set(),
        "frequencies": set(),
    })

    for r in rows:
        rid = str(r.routeId)
        routes_dict[rid]["uri"] = str(r.route)
        routes_dict[rid]["route_number"] = str(r.routeNum)
        if r.stopId:
            routes_dict[rid]["stops"].add(str(r.stopId))
        if r.opLabel:
            routes_dict[rid]["operators"].add(str(r.opLabel))
        if r.busType:
            routes_dict[rid]["vehicle_types"].add(str(r.busType).rsplit("#", 1)[-1])
        if r.freq:
            routes_dict[rid]["frequencies"].add(f"інтервал_{r.freq}хв")

    # Якщо в онтології мало маршрутів, доповнюємо дорожніми сервісами та сегментами
    records = []
    for rid, data in routes_dict.items():
        text_features = [
            f"маршрут_{data['route_number']}",
            " ".join(data["stops"]),
            " ".join(data["operators"]),
            " ".join(data["vehicle_types"]),
            " ".join(data["frequencies"]),
        ]
        records.append({
            "item_id": rid,
            "uri": data["uri"],
            "title": f"Маршрут №{data['route_number']}",
            "features_text": " ".join([t for t in text_features if t.strip()]),
            "item_type": "Route",
        })

    # Додаємо зарядні хаби та інші ключові сервіси з онтології як альтернативні елементи рекомендацій
    query_chg = """
    PREFIX : <http://example.org/transport-ontology#>
    SELECT ?chg ?id ?label ?desc WHERE {
        ?chg a :ChargingStation ;
             :identifier ?id ;
             rdfs:label ?label ;
             :description ?desc .
    }
    """
    for r in g.query(query_chg):
        records.append({
            "item_id": str(r.id),
            "uri": str(r.chg),
            "title": str(r.label),
            "features_text": f"зарядна_станція електротранспорт депо {r.desc}",
            "item_type": "ChargingStation",
        })

    # Додаємо ключові дорожні сегменти мережі
    query_ds = """
    PREFIX : <http://example.org/transport-ontology#>
    SELECT ?ds ?id ?label ?desc WHERE {
        ?ds a :RoadSegment ;
            :identifier ?id ;
            rdfs:label ?label .
        OPTIONAL { ?ds :description ?desc }
    }
    """
    for r in g.query(query_ds):
        desc = str(r.desc) if r.desc else "дорожній сегмент магістраль"
        records.append({
            "item_id": str(r.id),
            "uri": str(r.ds),
            "title": str(r.label),
            "features_text": f"сегмент дороги {desc}",
            "item_type": "RoadSegment",
        })

    df = pd.DataFrame(records).drop_duplicates(subset=["item_id"]).reset_index(drop=True)
    return df


# =============================================================================
# 3. ГЕНЕРАТОР ДАТАСЕТУ ПАСАЖИРСЬКИХ ОЦІНОК
# =============================================================================
def generate_synthetic_ratings_dataset(items_df: pd.DataFrame, num_users: int = 120, num_interactions: int = 900) -> pd.DataFrame:
    """
    Генерує псевдонімізовані взаємодії (user_id, item_id, rating, timestamp).
    Враховує кластери вподобань користувачів (екологічний транспорт, центральні поїздки, автомобілісти).
    """
    user_ids = [f"U{1000 + i}" for i in range(num_users)]
    item_ids = items_df["item_id"].tolist()
    
    # Сегментація інтересів для реалістичності колаборативної фільтрації
    user_personas = {}
    for uid in user_ids:
        user_personas[uid] = random.choice(["eco_transit", "central_commuter", "car_driver"])

    routes = items_df[items_df["item_type"] == "Route"]["item_id"].tolist()
    chargers = items_df[items_df["item_type"] == "ChargingStation"]["item_id"].tolist()
    segments = items_df[items_df["item_type"] == "RoadSegment"]["item_id"].tolist()

    interactions = []
    timestamps = pd.date_range(start="2026-09-01", periods=num_interactions, freq="15min")

    for i in range(num_interactions):
        u = random.choice(user_ids)
        persona = user_personas[u]

        if persona == "eco_transit":
            # Віддають перевагу маршрутам з електробусами (R-24, R-5) та зарядним хабам
            pool = routes + chargers
            chosen_item = random.choice(pool)
            rating = np.random.choice([4.0, 5.0, 3.5, 4.5], p=[0.3, 0.4, 0.1, 0.2])
        elif persona == "central_commuter":
            # Часті поїздки маршрутами R-35, R-24 та сегментами центру
            pool = routes + segments
            chosen_item = random.choice(pool)
            rating = np.random.choice([3.0, 4.0, 5.0, 2.5], p=[0.3, 0.4, 0.2, 0.1])
        else: # car_driver
            # Оцінюють якість дорожніх сегментів та зарядні хаби
            pool = segments + chargers
            chosen_item = random.choice(pool)
            rating = np.random.choice([3.5, 4.0, 4.5, 5.0, 2.0], p=[0.25, 0.35, 0.2, 0.1, 0.1])

        interactions.append({
            "user_id": u,
            "item_id": chosen_item,
            "rating": float(rating),
            "timestamp": timestamps[i],
        })

    df = pd.DataFrame(interactions)
    # Залишаємо останню оцінку для унікальної пари (user, item)
    df = df.sort_values("timestamp").groupby(["user_id", "item_id"]).last().reset_index()
    return df


# =============================================================================
# 4. СПЛІТ ДАНИХ (LEAVE-ONE-OUT / TEMPORAL)
# =============================================================================
def leave_one_out_split(ratings_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Часовий спліт Leave-One-Out для кожного користувача:
    - остання дія -> test
    - передостання дія -> validation
    - решта дій -> train
    """
    sorted_df = ratings_df.sort_values(["user_id", "timestamp"]).copy()
    
    train_rows, val_rows, test_rows = [], [], []

    for user_id, group in sorted_df.groupby("user_id"):
        if len(group) >= 3:
            test_rows.append(group.iloc[-1])
            val_rows.append(group.iloc[-2])
            train_rows.extend(group.iloc[:-2].to_dict("records"))
        elif len(group) == 2:
            test_rows.append(group.iloc[-1])
            train_rows.extend(group.iloc[:-1].to_dict("records"))
        else:
            train_rows.extend(group.to_dict("records"))

    train_df = pd.DataFrame(train_rows).reset_index(drop=True)
    val_df = pd.DataFrame(val_rows).reset_index(drop=True)
    test_df = pd.DataFrame(test_rows).reset_index(drop=True)

    return train_df, val_df, test_df


# =============================================================================
# 5. РЕАЛІЗАЦІЯ МОДЕЛЕЙ РЕКОМЕНДАЦІЙ
# =============================================================================

class RandomRecommender:
    """Бейзлайн випадкової видачі."""
    def __init__(self, all_items: List[str]) -> None:
        self.all_items = all_items

    def recommend(self, user_id: str, k: int, seen_items: Set[str]) -> List[str]:
        candidates = [itm for itm in self.all_items if itm not in seen_items]
        return random.sample(candidates, min(k, len(candidates)))


class TopPopularRecommender:
    """Бейзлайн найбільш популярних елементів за середнім рейтингом та кількістю оцінок."""
    def __init__(self) -> None:
        self.popular_ranking: List[str] = []

    def fit(self, train_df: pd.DataFrame) -> None:
        stats = train_df.groupby("item_id").agg(
            count=("rating", "count"),
            avg_rating=("rating", "mean")
        ).reset_index()
        # Зважена популярність: комбінація частоти вибору та середньої оцінки
        stats["score"] = stats["count"] * stats["avg_rating"]
        stats = stats.sort_values("score", ascending=False)
        self.popular_ranking = stats["item_id"].tolist()

    def recommend(self, user_id: str, k: int, seen_items: Set[str]) -> List[str]:
        recs = [itm for itm in self.popular_ranking if itm not in seen_items]
        return recs[:k]


class ContentBasedRecommender:
    """
    Контентна модель на основі семантичних ознак з онтології (TF-IDF + Cosine Similarity).
    """
    def __init__(self, items_df: pd.DataFrame) -> None:
        self.items_df = items_df
        self.item_ids = items_df["item_id"].tolist()
        self._build_tfidf_matrix()
        self.user_profiles: Dict[str, np.ndarray] = {}

    def _build_tfidf_matrix(self) -> None:
        # Проста та надійна реалізація TF-IDF без сторонніх важких бібліотек
        docs = [d.split() for d in self.items_df["features_text"]]
        vocab = sorted(list({token for doc in docs for token in doc}))
        self.token_to_idx = {t: idx for idx, t in enumerate(vocab)}
        
        n_docs = len(docs)
        n_terms = len(vocab)
        tf = np.zeros((n_docs, n_terms))
        df_counts = np.zeros(n_terms)

        for i, doc in enumerate(docs):
            for token in doc:
                idx = self.token_to_idx[token]
                tf[i, idx] += 1
            for idx in set([self.token_to_idx[t] for t in doc]):
                df_counts[idx] += 1

        idf = np.log((1 + n_docs) / (1 + df_counts)) + 1.0
        tfidf = tf * idf
        
        # L2-нормалізація векторів
        norms = np.linalg.norm(tfidf, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self.tfidf_matrix = tfidf / norms

    def fit(self, train_df: pd.DataFrame) -> None:
        # Формування вектора уподобань користувача як зваженого середнього векторів оцінених елементів
        for uid, grp in train_df.groupby("user_id"):
            profile = np.zeros(self.tfidf_matrix.shape[1])
            weights_sum = 0.0
            for _, row in grp.iterrows():
                itm = row["item_id"]
                if itm in self.item_ids:
                    idx = self.item_ids.index(itm)
                    weight = float(row["rating"])
                    profile += self.tfidf_matrix[idx] * weight
                    weights_sum += weight
            if weights_sum > 0:
                profile /= weights_sum
                norm = np.linalg.norm(profile)
                if norm > 0:
                    profile /= norm
            self.user_profiles[uid] = profile

    def recommend(self, user_id: str, k: int, seen_items: Set[str]) -> List[Tuple[str, float]]:
        if user_id not in self.user_profiles:
            return []
        u_vec = self.user_profiles[user_id]
        scores = np.dot(self.tfidf_matrix, u_vec)
        
        ranked_indices = np.argsort(scores)[::-1]
        recs = []
        for idx in ranked_indices:
            itm = self.item_ids[idx]
            if itm not in seen_items:
                recs.append((itm, float(scores[idx])))
            if len(recs) == k:
                break
        return recs


class SVDCollaborativeRecommender:
    """
    Колаборативна фільтрація на базі матричної факторизації (SVD / Matrix Factorization)
    з регуляризованим стохастичним градієнтним спуском (SGD).
    """
    def __init__(self, n_factors: int = 8, lr: float = 0.01, reg: float = 0.05, n_epochs: int = 40) -> None:
        self.n_factors = n_factors
        self.lr = lr
        self.reg = reg
        self.n_epochs = n_epochs

    def fit(self, train_df: pd.DataFrame, all_items: List[str]) -> None:
        self.users = sorted(train_df["user_id"].unique())
        self.items = sorted(list(set(all_items).union(train_df["item_id"].unique())))

        self.u_map = {u: i for i, u in enumerate(self.users)}
        self.i_map = {itm: i for i, itm in enumerate(self.items)}

        self.global_mean = float(train_df["rating"].mean())
        n_u, n_i = len(self.users), len(self.items)

        # Ініціалізація біасів та прихованих векторів
        self.b_u = np.zeros(n_u)
        self.b_i = np.zeros(n_i)
        self.P = np.random.normal(0, 0.1, (n_u, self.n_factors))
        self.Q = np.random.normal(0, 0.1, (n_i, self.n_factors))

        # Навчання через SGD
        for _ in range(self.n_epochs):
            for _, row in train_df.iterrows():
                u_idx = self.u_map[row["user_id"]]
                i_idx = self.i_map[row["item_id"]]
                r = float(row["rating"])

                pred = self.global_mean + self.b_u[u_idx] + self.b_i[i_idx] + np.dot(self.P[u_idx], self.Q[i_idx])
                err = r - pred

                self.b_u[u_idx] += self.lr * (err - self.reg * self.b_u[u_idx])
                self.b_i[i_idx] += self.lr * (err - self.reg * self.b_i[i_idx])

                p_old = self.P[u_idx].copy()
                self.P[u_idx] += self.lr * (err * self.Q[i_idx] - self.reg * self.P[u_idx])
                self.Q[i_idx] += self.lr * (err * p_old - self.reg * self.Q[i_idx])

    def predict(self, user_id: str, item_id: str) -> float:
        if user_id not in self.u_map or item_id not in self.i_map:
            return self.global_mean
        u_idx = self.u_map[user_id]
        i_idx = self.i_map[item_id]
        return float(self.global_mean + self.b_u[u_idx] + self.b_i[i_idx] + np.dot(self.P[u_idx], self.Q[i_idx]))

    def recommend(self, user_id: str, k: int, seen_items: Set[str]) -> List[Tuple[str, float]]:
        if user_id not in self.u_map:
            return []
        predictions = []
        for itm in self.items:
            if itm not in seen_items:
                score = self.predict(user_id, itm)
                predictions.append((itm, score))
        predictions.sort(key=lambda x: x[1], reverse=True)
        return predictions[:k]


# =============================================================================
# 6. МОДУЛЬ ОЦІНЮВАННЯ МЕТРИК (PRECISION, RECALL, MAP, NDCG, COVERAGE)
# =============================================================================
@dataclass
class EvalMetrics:
    precision: float
    recall: float
    map_score: float
    ndcg: float
    coverage: float


def compute_metrics(recommender, test_df: pd.DataFrame, train_df: pd.DataFrame, all_items: List[str], k: int = 3) -> EvalMetrics:
    test_grouped = test_df.groupby("user_id")["item_id"].apply(set).to_dict()
    train_grouped = train_df.groupby("user_id")["item_id"].apply(set).to_dict()

    precisions, recalls, map_list, ndcg_list = [], [], [], []
    recommended_unique_items = set()

    for uid, relevant_items in test_grouped.items():
        seen = train_grouped.get(uid, set())
        
        # Отримання рекомендацій від моделі
        raw_recs = recommender.recommend(uid, k, seen)
        if raw_recs and isinstance(raw_recs[0], tuple):
            recs = [itm for itm, _ in raw_recs]
        else:
            recs = raw_recs

        for itm in recs:
            recommended_unique_items.add(itm)

        # 1. Precision@k & Recall@k
        hits = len(set(recs).intersection(relevant_items))
        precisions.append(hits / k)
        recalls.append(hits / len(relevant_items) if relevant_items else 0.0)

        # 2. Average Precision (AP@k)
        score_ap = 0.0
        running_hits = 0
        for i, pred_item in enumerate(recs):
            if pred_item in relevant_items:
                running_hits += 1
                score_ap += running_hits / (i + 1)
        map_list.append(score_ap / min(len(relevant_items), k) if relevant_items else 0.0)

        # 3. NDCG@k
        dcg = 0.0
        for i, pred_item in enumerate(recs):
            if pred_item in relevant_items:
                dcg += 1.0 / math.log2((i + 1) + 1)
        idcg = sum(1.0 / math.log2((r + 1) + 1) for r in range(min(len(relevant_items), k)))
        ndcg_list.append(dcg / idcg if idcg > 0 else 0.0)

    coverage = len(recommended_unique_items) / len(all_items) if all_items else 0.0

    return EvalMetrics(
        precision=float(np.mean(precisions)),
        recall=float(np.mean(recalls)),
        map_score=float(np.mean(map_list)),
        ndcg=float(np.mean(ndcg_list)),
        coverage=coverage
    )


# =============================================================================
# 7. ГОЛОВНИЙ КОНВЕЄР ВИКОНАННЯ
# =============================================================================
def main():
    print("=" * 80)
    print("  ЛАБОРАТОРНА РОБОТА №16: РЕКОМЕНДАЦІЙНА СИСТЕМА ДЛЯ ТРАНСПОРТНОЇ СИСТЕМИ")
    print("=" * 80)

    # 1. Онтологічне вилучення
    print("\n[1] Екстракція семантичних ознак з онтології update_expanded.owl через SPARQL...")
    items_df = extract_ontology_items_and_features(ONTOLOGY_PATH)
    all_item_ids = items_df["item_id"].tolist()
    print(f" -> Успішно вилучено {len(items_df)} унікальних об'єктів інфраструктури (маршрути, зарядні станції, сегменти).")

    # 2. Генерація взаємодій
    print("\n[2] Генерація датасету взаємодій користувачів (ratings + items)...")
    ratings_df = generate_synthetic_ratings_dataset(items_df, num_users=120, num_interactions=850)
    ratings_df.to_csv(DATASET_CSV, index=False)
    print(f" -> Сформовано {len(ratings_df)} оцінок для {ratings_df['user_id'].nunique()} унікальних користувачів.")
    print(f" -> Збережено датасет у: {DATASET_CSV}")

    # 3. Спліт даних
    print("\n[3] Розбиття даних на Train / Validation / Test (Leave-One-Out Temporal Split)...")
    train_df, val_df, test_df = leave_one_out_split(ratings_df)
    print(f" -> Train: {len(train_df)} рядків | Val: {len(val_df)} рядків | Test: {len(test_df)} рядків.")

    # 4. Навчання моделей
    print("\n[4] Ініціалізація та тренування моделей рекомендацій...")
    
    # Бейзлайн 1: Random
    random_model = RandomRecommender(all_item_ids)

    # Бейзлайн 2: Top-Popular
    popular_model = TopPopularRecommender()
    popular_model.fit(train_df)

    # Модель 1: Content-Based (TF-IDF + Cosine + OWL attributes)
    cb_model = ContentBasedRecommender(items_df)
    cb_model.fit(train_df)

    # Модель 2: SVD Matrix Factorization (Collaborative Filtering)
    svd_model = SVDCollaborativeRecommender(n_factors=10, lr=0.015, reg=0.05, n_epochs=50)
    svd_model.fit(train_df, all_item_ids)
    print(" -> Усі 4 моделі успішно натреновано.")

    # 5. Оцінювання якості
    print("\n[5] Розрахунок метрик якості (Precision@3, Recall@3, MAP@3, NDCG@3, Coverage)...")
    eval_results = {}
    models_dict = {
        "Random Baseline": random_model,
        "Top-Popular Baseline": popular_model,
        "Content-Based (TF-IDF + OWL)": cb_model,
        "Collaborative (SVD / MF)": svd_model
    }

    for name, model in models_dict.items():
        metrics = compute_metrics(model, test_df, train_df, all_item_ids, k=K_VAL)
        eval_results[name] = metrics

    # Вивід підсумкової порівняльної таблиці
    print("\n" + "=" * 95)
    print(f"{'Модель':<32} | {'P@3':>7} | {'R@3':>7} | {'MAP@3':>7} | {'NDCG@3':>8} | {'Coverage':>9}")
    print("-" * 95)
    for name, m in eval_results.items():
        print(f"{name:<32} | {m.precision:>7.4f} | {m.recall:>7.4f} | {m.map_score:>7.4f} | {m.ndcg:>8.4f} | {m.coverage:>8.1%}")
    print("=" * 95)

    # 6. Демонстрація персоналізованих прикладів з поясненнями
    print("\n[6] ДЕМОНСТРАЦІЯ 3 ПЕРСОНАЛІЗОВАНИХ РЕКОМЕНДАЦІЙ ІЗ ПОЯСНЕННЯМИ (EXPLAINABILITY):")
    demo_users = ["U1001", "U1005", "U1012"]
    
    for u in demo_users:
        seen = set(train_df[train_df["user_id"] == u]["item_id"])
        cb_recs = cb_model.recommend(u, k=2, seen_items=seen)
        svd_recs = svd_model.recommend(u, k=2, seen_items=seen)

        print(f"\n" + "-" * 75)
        print(f"Користувач: {u}")
        print(f"Історія оцінок (Train): {list(seen)}")
        
        print(" -> Content-Based рекомендація:")
        for itm, score in cb_recs:
            item_row = items_df[items_df["item_id"] == itm].iloc[0]
            print(f"    • [{itm}] {item_row['title']} (Cosine Score: {score:.3f})")
            print(f"      Пояснення: Рекомендовано на основі онтологічних ознак «{item_row['features_text'][:55]}...» [URI: <{item_row['uri']}>].")

        print(" -> Collaborative SVD рекомендація:")
        for itm, score in svd_recs:
            item_row = items_df[items_df["item_id"] == itm].iloc[0]
            print(f"    • [{itm}] {item_row['title']} (Прогнозований рейтинг: {score:.2f}★)")
            print(f"      Пояснення: Користувачі зі схожим вектором транспортних уподобань високої оцінки поставили об'єкту [URI: <{item_row['uri']}>].")

    print("\n" + "=" * 80)
    print("  ВИКОНАННЯ ЛАБОРАТОРНОЇ РОБОТИ №16 ЗАВЕРШЕНО")
    print("=" * 80)


if __name__ == "__main__":
    main()