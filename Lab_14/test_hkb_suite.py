"""
Прототип автоматизованих тестів для гібридного сховища знань (HKB)
Самостійна работа №14
Предметна область: "Цифрова модель транспортних систем"

Запуск:
    pytest test_hkb_suite.py -v
або:
    python test_hkb_suite.py
"""

import math
import sqlite3
import time
from pathlib import Path
import pytest

from rdflib import Graph, Namespace
from rdflib.namespace import RDF, RDFS

from run_lab14_queries import (
    RelationalLayer,
    SemanticLayer,
    VectorLayer,
    HybridMediator,
    resolve_ontology_path,
    ONTOLOGY_URI
)

ONT = Namespace(ONTOLOGY_URI)

# =============================================================================
# ФІКСТУРИ PYTEST (Еталонний набір даних / Golden Set)
# =============================================================================

@pytest.fixture(scope="module")
def hkb_environment():
    """Ініціалізація та надання ізольованих екземплярів всіх шарів HKB."""
    owl_file = resolve_ontology_path()
    relational = RelationalLayer()
    semantic = SemanticLayer(owl_file)
    vector = VectorLayer()
    mediator = HybridMediator(relational, semantic, vector)
    
    yield {
        "relational": relational,
        "semantic": semantic,
        "vector": vector,
        "mediator": mediator
    }
    
    relational.close()


# =============================================================================
# 1. ТЕСТИ РЕЛЯЦІЙНОГО ШАРУ (SQL & Schema Integrity)
# # =============================================================================

def test_sql_schema_integrity(hkb_environment):
    """Перевірка цілісності схеми: обмеження унікальності PRIMARY KEY."""
    relational = hkb_environment["relational"]
    
    # Спроба вставки дубліката первинного ключа
    with pytest.raises(sqlite3.IntegrityError):
        relational.conn.execute(
            "INSERT INTO dim_road_segment VALUES ('DS-001', 'Дублікат', 'arterial', 2, 50);"
        )


def test_sql_kq1_anomaly_detection(hkb_environment):
    """Перевірка точності аналітичного запиту виявлення заторів KQ-1."""
    relational = hkb_environment["relational"]
    start_time = time.perf_counter()
    anomalies = relational.kq1_critical_segments()
    duration_ms = (time.perf_counter() - start_time) * 1000.0
    
    assert len(anomalies) >= 1, "Має бути знайдено як мінімум 1 аномальний сегмент"
    target = anomalies[0]
    assert target.segment_id == "DS-001"
    assert target.avg_speed_kmh < 20.0
    assert target.max_congestion >= 0.90
    assert target.speed_drop_pct > 60.0
    assert duration_ms < 50.0, f"Затримка SQL перевищує поріг NFR: {duration_ms:.2f} ms"


# =============================================================================
# 2. ТЕСТИ СЕМАНТИЧНОГО ШАРУ (OWL / RDF / SPARQL)
# =============================================================================

def test_ontology_structure_metrics(hkb_environment):
    """Перевірка завантаження та метрик TBox/ABox онтології."""
    semantic = hkb_environment["semantic"]
    stats = semantic.ontology_stats()
    
    assert stats["classes"] >= 10, "Онтологія повинна містити щонайменше 10 класів"
    assert stats["individuals"] >= 15, "Онтологія повинна містити щонайменше 15 екземплярів ABox"
    assert len(semantic.graph) > 500, "Кількість RDF-триплетів повинна перевищувати 500"


def test_sparql_kq2_topology(hkb_environment):
    """Перевірка топологічного відповідності та прив'язки рухомого складу (KQ-2)."""
    semantic = hkb_environment["semantic"]
    segment, vehicles = semantic.kq2_segment_and_vehicles("DS001")
    
    assert segment is not None, "Сегмент DS001 обов'язково має бути присутнім у графі"
    assert segment.identifier == "DS-001"
    assert segment.lane_count == 2
    assert segment.allowed_speed == 50.0
    assert len(vehicles) >= 1, "На сегменті має бути зафіксований рухомий склад"
    assert vehicles[0].route_number == "24", "Автобус має обслуговувати маршрут №24"
    assert vehicles[0].vehicle_identifier == "BUS-24"


def test_sparql_kq3_incident_chain(hkb_environment):
    """Перевірка логічної ланцюга: Подія -> Потік -> Правило -> Рішення (KQ-3)."""
    semantic = hkb_environment["semantic"]
    incidents = semantic.kq3_incidents_and_decisions("DS001")
    
    assert len(incidents) >= 1, "Для DS001 має бути знайдений сценарій ДТП"
    inc = incidents[0]
    assert inc.incident_identifier == "ACC-001"
    assert inc.decision_type in ["TransportDecision", "RouteChange"]
    assert inc.changed_route_number == "24"


# =============================================================================
# 3. ТЕСТИ ВЕКТОРНОГО ШАРУ (Dense Retrieval Quality)
# =============================================================================

def test_vector_kq4_accuracy(hkb_environment):
    """Перевірка коректності пошуку за ембеддингами (KQ-4)."""
    vector = hkb_environment["vector"]
    hits = vector.search("Аварія заблокувала рух на магістралі, критичний затор, що робити диспетчеру для автобусів?", top_k=2)
    
    assert len(hits) == 2, "Має повертатися точно 2 найближчих документа"
    for hit in hits:
        assert 0.0 <= hit.similarity <= 1.0, "Схожість має бути нормалізована в діапазоні [0, 1]"
        assert hit.distance >= 0.0, "Косинусна відстань не може бути від'ємною"

def test_vector_similarity_boundedness(hkb_environment):
    """Property-based тест стабильності векторного пошуку на випадкових та пустих запитах."""
    vector = hkb_environment["vector"]
    noise_queries = [
        "12345 !@#$%^ &*()",
        "абсолютно незв'язний текст про кулінарію та космічні станції",
        " " * 50
    ]
    for q in noise_queries:
        hits = vector.search(q, top_k=1)
        assert len(hits) == 1
        assert not math.isnan(hits[0].similarity)
        assert 0.0 <= hits[0].similarity <= 1.0


# =============================================================================
# 4. ТЕСТИ КРОС-ШАРОВОЇ ІНТЕГРАЦІЇ (Cross-Layer Alignment & Federation)
# =============================================================================

def test_cross_layer_entity_alignment(hkb_environment):
    """
    Перевірка узгодженості сутностей між SQL та RDF/OWL:
    1. Критичний сегмент DS-001 обов'язково синхронізований з OWL (Primary Anchor).
    2. Індивіди RoadSegment, наявні в онтології, зареєстровані в реляційній базі.
    """
    relational = hkb_environment["relational"]
    semantic = hkb_environment["semantic"]
    mediator = hkb_environment["mediator"]

    # 1. Перевірка опорного сегмента DS-001
    anchor_id = "DS-001"
    norm_anchor = mediator.normalize_segment_id(anchor_id)
    anchor_uri = ONT[norm_anchor]
    triples_anchor = len(list(semantic.graph.triples((anchor_uri, None, None))))
    assert triples_anchor > 0, f"Опорний сегмент {anchor_id} ({anchor_uri}) відсутній в онтології!"

    # 2. Отримуємо всі зареєстровані ідентифікатори з SQL
    sql_rows = relational.execute("SELECT segment_id FROM dim_road_segment;")
    sql_segment_ids = {row["segment_id"] for row in sql_rows}

    # 3. Перевіряємо зворотну відповідність: кожен RoadSegment з OWL є в SQL
    sparql_query = """
        PREFIX : <http://example.org/transport-ontology#>
        SELECT ?segment ?identifier
        WHERE {
            ?segment a :RoadSegment .
            OPTIONAL { ?segment :identifier ?identifier . }
        }
    """
    owl_segments = semantic.graph.query(sparql_query)
    assert len(owl_segments) > 0, "В онтології повинен бути хоча б один індивід RoadSegment"

    for row in owl_segments:
        owl_id = str(row.identifier) if row.identifier else str(row.segment).split("#")[-1]
        # Перевіряємо присутність у SQL (у форматі DS-001)
        # Якщо в онтології ідентифікатор без дефісу (DS001), нормалізуємо для зіставлення
        matching = any(mediator.normalize_segment_id(s) == mediator.normalize_segment_id(owl_id) for s in sql_segment_ids)
        assert matching, f"Сегмент онтології {owl_id} відсутній у реляційній базі SQL"


def test_federated_pipeline_flow(hkb_environment):
    """Наскрізний інтеграційний тест федеративного конвеєра (KQ-5)."""
    mediator = hkb_environment["mediator"]
    
    anomalies = mediator.relational.kq1_critical_segments()
    assert len(anomalies) > 0, "SQL має повернути хоча б одну аномалію"
    target_id = mediator.normalize_segment_id(anomalies[0].segment_id)
    
    _, vehicles = mediator.semantic.kq2_segment_and_vehicles(target_id)
    incidents = mediator.semantic.kq3_incidents_and_decisions(target_id)
    
    hits = mediator.run_kq5(anomalies, incidents, vehicles)
    
    assert len(hits) > 0, "Конвейер має повертати регламенти дій"
    best_hit = hits[0]
    assert best_hit.document_id == "REG-01-REROUTE", "Має бути обраний регламент перенаправлення маршрутів"
    assert best_hit.similarity >= 0.75, "Релевантність після обагщення онтологічним контекстом має бути >= 0.75"


def test_negative_nonexistent_segment(hkb_environment):
    """Негативний тест: безпечна обробка звернення до неіснуючого сегменту."""
    semantic = hkb_environment["semantic"]
    segment, vehicles = semantic.kq2_segment_and_vehicles("DS999")
    incidents = semantic.kq3_incidents_and_decisions("DS999")
    
    assert segment is None, "Неіснуючий сегмент не повинен повертатися"
    assert len(vehicles) == 0, "Список транспорта повинен бути порожнім"
    assert len(incidents) == 0, "Список інцидентів повинен бути порожнім"


# =============================================================================
# Запуск через прямой вызов интерпретатора
# =============================================================================

if __name__ == "__main__":
    pytest.main(["-v", "-s", __file__])