"""Deterministic synthetic Ukrainian corpus and competency-query generator.

The generator models the ontology concepts requested by the laboratory:
road segments, bus routes, traffic incidents, and sensor telemetry.
Each document is a compact knowledge card with both natural-language text
and structured metadata. Ground truth is generated from explicit metadata
rules, not from the embedding model, so evaluation remains reproducible.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd

from config import CORPUS_PATH, NUM_DOCUMENTS, QUERIES_PATH, RANDOM_SEED


@dataclass(frozen=True)
class Document:
    doc_id: str
    doc_type: str
    entity_id: str
    text: str
    city: str
    road: str
    route_number: int | None = None
    stop_count: int | None = None
    interval_min: int | None = None
    length_km: float | None = None
    lanes: int | None = None
    speed_limit: int | None = None
    congestion: str | None = None
    incident_type: str | None = None
    severity: str | None = None
    speed_drop_pct: int | None = None
    vehicle_count: int | None = None
    timestamp: str | None = None


CITIES = [
    ("Львів", ["вул. Городоцька", "вул. Стрийська", "вул. Личаківська", "просп. Чорновола"]),
    ("Київ", ["просп. Перемоги", "вул. Дегтярівська", "вул. Братиславська", "вул. Січових Стрільців"]),
    ("Харків", ["просп. Науки", "вул. Полтавський Шлях", "вул. Клочківська", "вул. Академіка Павлова"]),
    ("Дніпро", ["просп. Дмитра Яворницького", "вул. Набережна", "вул. Робоча", "просп. Слобожанський"]),
]

CONGESTION = ["низький", "середній", "високий", "критичний"]
INCIDENTS = [
    ("ДТП", ["легка", "середня", "тяжка"]),
    ("перекриття", ["часткове", "повне"]),
    ("об'їзд", ["локальний", "маршрутний"]),
    ("падіння швидкості", ["помірне", "значне"]),
]

STOPS = [
    "Центр", "Вокзал", "Університет", "Площа Ринок", "Автовокзал",
    "Шевченківський гай", "Парк", "Лікарня", "Стадіон", "Аеропорт",
]

QUERY_SPECS = [
    {
        "query_id": "KQ01",
        "query": "Які дорожні сегменти мають критичну затримку та обмеження швидкості до 40 км/год?",
        "rule": lambda d: d.doc_type == "road_segment" and d.congestion == "критичний" and d.speed_limit <= 40,
    },
    {
        "query_id": "KQ02",
        "query": "Які автобусні маршрути мають інтервал руху не більше 10 хвилин?",
        "rule": lambda d: d.doc_type == "bus_route" and d.interval_min <= 10,
    },
    {
        "query_id": "KQ03",
        "query": "Які маршрути мають щонайменше 15 зупинок та інтервал до 12 хвилин?",
        "rule": lambda d: d.doc_type == "bus_route" and d.stop_count >= 15 and d.interval_min <= 12,
    },
    {
        "query_id": "KQ04",
        "query": "Які дорожні інциденти спричинили повне перекриття дороги?",
        "rule": lambda d: d.doc_type == "traffic_incident" and d.incident_type == "перекриття" and d.severity == "повне",
    },
    {
        "query_id": "KQ05",
        "query": "Які інциденти характеризуються значним падінням швидкості понад 40 відсотків?",
        "rule": lambda d: d.doc_type == "traffic_incident" and d.speed_drop_pct is not None and d.speed_drop_pct >= 40,
    },
    {
        "query_id": "KQ06",
        "query": "Які сенсори зафіксували понад 900 транспортних засобів за вимірювання?",
        "rule": lambda d: d.doc_type == "sensor_telemetry" and d.vehicle_count >= 900,
    },
    {
        "query_id": "KQ07",
        "query": "Які телеметричні вимірювання показують середню швидкість нижче 30 км/год?",
        "rule": lambda d: d.doc_type == "sensor_telemetry" and _speed_from_text(d.text) < 30,
    },
    {
        "query_id": "KQ08",
        "query": "Які сегменти мають щонайменше 3 смуги та високий рівень заторів?",
        "rule": lambda d: d.doc_type == "road_segment" and d.lanes >= 3 and d.congestion == "високий",
    },
    {
        "query_id": "KQ09",
        "query": "Які автобусні маршрути обслуговують понад 18 зупинок?",
        "rule": lambda d: d.doc_type == "bus_route" and d.stop_count > 18,
    },
    {
        "query_id": "KQ10",
        "query": "Які ДТП мають тяжкі наслідки та призвели до падіння швидкості щонайменше на 30 відсотків?",
        "rule": lambda d: d.doc_type == "traffic_incident" and d.incident_type == "ДТП" and d.severity == "тяжка" and d.speed_drop_pct >= 30,
    },
    {
        "query_id": "KQ11",
        "query": "Які сенсори показують одночасно швидкість нижче 25 км/год і потік понад 800 транспортних засобів?",
        "rule": lambda d: d.doc_type == "sensor_telemetry" and _speed_from_text(d.text) < 25 and d.vehicle_count > 800,
    },
    {
        "query_id": "KQ12",
        "query": "Які дорожні сегменти мають 2 смуги, обмеження швидкості не більше 50 км/год і високий затор?",
        "rule": lambda d: d.doc_type == "road_segment" and d.lanes == 2 and d.speed_limit <= 50 and d.congestion == "високий",
    },
]


def _speed_from_text(text: str) -> float:
    match = re.search(r"середня швидкість\s+(\d+(?:[.,]\d+)?)\s*км/год", text, flags=re.IGNORECASE)
    if not match:
        raise ValueError(f"Не вдалося знайти швидкість у тексті: {text}")
    return float(match.group(1).replace(",", "."))


def _token_normalize(text: str) -> str:
    text = text.lower().replace("’", "'")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _make_road_segment(rng: random.Random, idx: int) -> Document:
    city, roads = rng.choice(CITIES)
    road = rng.choice(roads)
    length = round(rng.uniform(0.6, 7.8), 1)
    lanes = rng.choice([1, 2, 2, 3, 3, 4])
    speed = rng.choice([30, 40, 50, 60, 70])
    congestion = rng.choices(CONGESTION, weights=[25, 35, 30, 10], k=1)[0]
    text = (
        f"Дорожній сегмент RS-{idx:04d}: {city}, {road}. "
        f"Довжина {length:.1f} км, {lanes} смуги руху, "
        f"обмеження швидкості {speed} км/год. "
        f"Рівень заторів: {congestion}. "
        f"Сегмент використовується для аналізу пропускної здатності та регулювання руху."
    )
    return Document(f"D{idx:04d}", "road_segment", f"RS-{idx:04d}", text, city, road,
                    length_km=length, lanes=lanes, speed_limit=speed, congestion=congestion)


def _make_bus_route(rng: random.Random, idx: int) -> Document:
    city, roads = rng.choice(CITIES)
    route = rng.randint(1, 99)
    stop_count = rng.randint(8, 24)
    interval = rng.choice([5, 7, 8, 10, 12, 15, 18, 20])
    chosen_stops = rng.sample(STOPS, k=5)
    text = (
        f"Автобусний маршрут №{route} у місті {city}: {stop_count} зупинок, "
        f"середній інтервал {interval} хв. Ключові зупинки: "
        f"{', '.join(chosen_stops)}. Обслуговування охоплює напрямок через {roads[0]}. "
        f"Маршрут використовується для оцінювання регулярності громадського транспорту."
    )
    return Document(f"D{idx:04d}", "bus_route", f"BUS-{route:03d}-{idx:04d}", text, city, roads[0],
                    route_number=route, stop_count=stop_count, interval_min=interval)


def _make_incident(rng: random.Random, idx: int) -> Document:
    city, roads = rng.choice(CITIES)
    incident_type, severities = rng.choice(INCIDENTS)
    severity = rng.choice(severities)
    speed_drop = rng.randint(10, 65)
    text = (
        f"Дорожній інцидент TI-{idx:04d}: {city}, {roads[0]}. "
        f"Тип події: {incident_type}; характеристика: {severity}. "
        f"Зафіксовано падіння швидкості на {speed_drop} відсотків. "
        f"Оператор дорожнього центру рекомендує контролювати об'їзд та відновлення руху."
    )
    return Document(f"D{idx:04d}", "traffic_incident", f"TI-{idx:04d}", text, city, roads[0],
                    incident_type=incident_type, severity=severity, speed_drop_pct=speed_drop)


def _make_sensor(rng: random.Random, idx: int) -> Document:
    city, roads = rng.choice(CITIES)
    speed = round(rng.uniform(12, 65), 1)
    vehicles = rng.randint(250, 1300)
    hour = rng.randint(0, 23)
    minute = rng.choice([0, 10, 20, 30, 40, 50])
    timestamp = f"2026-05-{rng.randint(1, 28):02d}T{hour:02d}:{minute:02d}:00"
    text = (
        f"Телеметрія сенсора ST-{idx:04d}: {city}, {roads[0]}. "
        f"Час вимірювання {timestamp}. "
        f"Середня швидкість {speed:.1f} км/год, кількість транспортних засобів {vehicles}. "
        f"Дані використовуються для оцінювання інтенсивності потоку та оперативного виявлення заторів."
    )
    return Document(f"D{idx:04d}", "sensor_telemetry", f"ST-{idx:04d}", text, city, roads[0],
                    vehicle_count=vehicles, timestamp=timestamp)


def generate_corpus(num_documents: int = NUM_DOCUMENTS, seed: int = RANDOM_SEED) -> pd.DataFrame:
    """Generate exactly `num_documents` deterministic synthetic documents."""
    if not 500 <= num_documents <= 600:
        raise ValueError("num_documents має бути в межах 500..600.")

    rng = random.Random(seed)
    builders: list[Callable[[random.Random, int], Document]] = [
        _make_road_segment, _make_bus_route, _make_incident, _make_sensor
    ]
    docs = [builders[i % 4](rng, i + 1) for i in range(num_documents)]

    # Deterministic preprocessing + deduplication.
    seen: set[str] = set()
    unique: list[Document] = []
    for doc in docs:
        key = _token_normalize(doc.text)
        if key not in seen:
            seen.add(key)
            unique.append(doc)

    if len(unique) != num_documents:
        raise RuntimeError("Дедуплікація зменшила корпус; перевірте генератор.")

    frame = pd.DataFrame([asdict(d) for d in unique])
    return frame


def generate_queries(corpus: pd.DataFrame) -> list[dict]:
    """Create KQs and explicit binary relevance lists from metadata."""
    docs = [Document(**row) for row in corpus.to_dict(orient="records")]
    result = []
    for spec in QUERY_SPECS:
        relevant = [d.doc_id for d in docs if spec["rule"](d)]
        if len(relevant) < 3:
            raise RuntimeError(
                f"{spec['query_id']} має лише {len(relevant)} релевантних документів; "
                "змініть генератор/правило."
            )
        result.append({
            "query_id": spec["query_id"],
            "query": spec["query"],
            "relevant_doc_ids": relevant,
            "relevant_count": len(relevant),
        })
    return result


def build_dataset(
    corpus_path: Path = CORPUS_PATH,
    queries_path: Path = QUERIES_PATH,
    num_documents: int = NUM_DOCUMENTS,
    seed: int = RANDOM_SEED,
) -> tuple[pd.DataFrame, list[dict]]:
    corpus = generate_corpus(num_documents=num_documents, seed=seed)
    queries = generate_queries(corpus)
    corpus_path.parent.mkdir(parents=True, exist_ok=True)
    queries_path.parent.mkdir(parents=True, exist_ok=True)
    corpus.to_csv(corpus_path, index=False, encoding="utf-8")
    queries_path.write_text(json.dumps(queries, ensure_ascii=False, indent=2), encoding="utf-8")
    return corpus, queries


if __name__ == "__main__":
    corpus, queries = build_dataset()
    print(f"Згенеровано документів: {len(corpus)}")
    print(f"Competency Queries: {len(queries)}")
    print(corpus["doc_type"].value_counts().to_string())
