"""
Лабораторна робота №14
"Проєктування запитів до гібридного сховища знань"

HKB architecture:
    1) RelationalLayer  -> SQLite / SQL
    2) SemanticLayer    -> RDF/OWL / SPARQL
    3) VectorLayer      -> ChromaDB / SentenceTransformers
    4) HybridMediator   -> Federated Mediation Pipeline

Запуск:
    python run_lab14_queries.py

Файл update.owl має лежати в тій самій директорії, що і цей скрипт.

Необхідні пакети:
    pip install rdflib chromadb sentence-transformers

Примітка:
    SentenceTransformer використовується для явного dense-embedding пошуку
    з моделлю sentence-transformers/all-MiniLM-L6-v2.
"""

from __future__ import annotations

import math
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

import rdflib.term
rdflib.term._warn_on_lexical_failure = False
import logging
logging.getLogger("rdflib").setLevel(logging.CRITICAL)

try:
    import chromadb
except ImportError as exc:
    raise SystemExit(
        "Не встановлено chromadb. Виконайте: pip install chromadb"
    ) from exc

try:
    from rdflib import Graph, Literal, Namespace
    from rdflib.namespace import RDF, RDFS
except ImportError as exc:
    raise SystemExit(
        "Не встановлено rdflib. Виконайте: pip install rdflib"
    ) from exc

try:
    from sentence_transformers import SentenceTransformer
except ImportError as exc:
    raise SystemExit(
        "Не встановлено sentence-transformers. Виконайте: "
        "pip install sentence-transformers"
    ) from exc


# =============================================================================
# Конфігурація
# =============================================================================

ONTOLOGY_URI = "http://example.org/transport-ontology#"
ONT = Namespace(ONTOLOGY_URI)

VECTOR_COLLECTION = "transport_regulations"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

KQ4_QUERY = (
    "Аварія заблокувала рух на магістралі, критичний затор, "
    "що робити диспетчеру для автобусів?"
)


# =============================================================================
# Console helpers
# =============================================================================

def print_banner(title: str) -> None:
    line = "=" * 110
    print(f"\n{line}")
    print(f"  {title}")
    print(line)


def print_status(message: str, status: str = "OK") -> None:
    print(f"[{status:^8}] {message}")


def fmt(value: Any, default: str = "Н/Д") -> str:
    if value is None or value == "":
        return default
    return str(value)


def short_uri(value: Any) -> str:
    text = fmt(value)
    return text.rsplit("#", 1)[-1]


def clamp_similarity(distance: float) -> float:
    """Convert Chroma cosine distance to a safe [0, 1] similarity."""
    return max(0.0, min(1.0, 1.0 - float(distance)))


def truncate(text: str, width: int = 190) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 3] + "..."


# =============================================================================
# Data classes
# =============================================================================

@dataclass(frozen=True)
class SQLAnomaly:
    segment_id: str
    name: str
    speed_limit: float
    avg_speed_kmh: float
    avg_flow_vph: float
    max_congestion: float
    speed_drop_pct: float


@dataclass(frozen=True)
class SegmentDetails:
    segment_uri: str
    identifier: str
    label: str
    allowed_speed: float
    lane_count: int
    length: float


@dataclass(frozen=True)
class VehicleRoute:
    vehicle_uri: str
    vehicle_identifier: str
    vehicle_label: str
    vehicle_type: str
    route_uri: str
    route_identifier: str
    route_number: str
    route_label: str


@dataclass(frozen=True)
class IncidentDecision:
    incident_uri: str
    incident_identifier: str
    incident_label: str
    incident_description: str
    flow_uri: str
    rule_uri: str
    rule_label: str
    rule_description: str
    decision_uri: str
    decision_type: str
    decision_label: str
    decision_description: str
    changed_route_uri: str
    changed_route_number: str


@dataclass(frozen=True)
class VectorHit:
    rank: int
    document_id: str
    category: str
    severity: str
    title: str
    similarity: float
    distance: float
    text: str


@dataclass(frozen=True)
class MappingRow:
    ontology_term: str
    source_field: str
    normalization_rule: str


# =============================================================================
# Layer 1: Relational
# =============================================================================

class RelationalLayer:
    """Operational SQL layer implemented with in-memory SQLite."""

    SEGMENTS = [
        ("DS-001", "вул. Франка (Центральний сегмент)", "arterial", 2, 50),
        ("DS-002", "вул. Зелена (Сегмент 2)", "collector", 2, 50),
        ("DS-003", "вул. Городоцька (Сегмент 3)", "arterial", 3, 50),
        ("DS-004", "вул. Стрийська (Сегмент 4)", "arterial", 3, 60),
        ("DS-005", "просп. Чорновола (Сегмент 5)", "collector", 2, 50),
    ]

    OBSERVATIONS = [
        ("2026-10-06 08:15:00", "DS-001", 1420, 16.4, 1, 0.88),
        ("2026-10-06 08:30:00", "DS-001", 1580, 14.1, 1, 0.94),
        ("2026-10-06 08:45:00", "DS-001", 1390, 18.2, 1, 0.82),
        ("2026-10-06 08:15:00", "DS-002", 920, 36.5, 1, 0.45),
        ("2026-10-06 08:30:00", "DS-002", 980, 34.0, 1, 0.49),
        ("2026-10-06 08:15:00", "DS-003", 1650, 24.3, 1, 0.71),
        ("2026-10-06 08:30:00", "DS-003", 1710, 22.8, 1, 0.75),
        ("2026-10-06 08:15:00", "DS-004", 1200, 48.0, 1, 0.35),
        ("2026-10-06 08:15:00", "DS-005", 850, 41.5, 1, 0.38),
    ]

    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self._create_schema()
        self._seed_data()

    def _create_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE dim_road_segment (
                segment_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                road_class TEXT NOT NULL,
                lanes INTEGER NOT NULL,
                speed_limit REAL NOT NULL
            );

            CREATE TABLE fact_traffic_observations (
                obs_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                segment_id TEXT NOT NULL,
                hourly_flow INTEGER NOT NULL,
                observed_speed REAL NOT NULL,
                is_peak_hour INTEGER NOT NULL,
                congestion_index REAL NOT NULL,
                FOREIGN KEY(segment_id)
                    REFERENCES dim_road_segment(segment_id)
            );
            """
        )

    def _seed_data(self) -> None:
        self.conn.executemany(
            """
            INSERT INTO dim_road_segment
                (segment_id, name, road_class, lanes, speed_limit)
            VALUES (?, ?, ?, ?, ?)
            """,
            self.SEGMENTS,
        )
        self.conn.executemany(
            """
            INSERT INTO fact_traffic_observations
                (timestamp, segment_id, hourly_flow, observed_speed,
                 is_peak_hour, congestion_index)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            self.OBSERVATIONS,
        )
        self.conn.commit()

    def execute(self, query: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        try:
            return list(self.conn.execute(query, params))
        except sqlite3.Error as exc:
            raise RuntimeError(f"SQL-помилка: {exc}") from exc

    def kq1_critical_segments(self) -> list[SQLAnomaly]:
        """
        KQ-1:
        Пікові години, середня швидкість < 20 км/год і дозволена швидкість 50.
        Результати сортуються за максимальним congestion_index.
        """
        query = """
            SELECT
                d.segment_id,
                d.name,
                d.speed_limit,
                AVG(f.observed_speed) AS avg_speed_kmh,
                AVG(f.hourly_flow) AS avg_flow_vph,
                MAX(f.congestion_index) AS max_congestion,
                (1.0 - AVG(f.observed_speed) / d.speed_limit) * 100.0
                    AS speed_drop_pct
            FROM fact_traffic_observations AS f
            JOIN dim_road_segment AS d
                ON d.segment_id = f.segment_id
            WHERE f.is_peak_hour = 1
              AND d.speed_limit = 50
            GROUP BY d.segment_id, d.name, d.speed_limit
            HAVING AVG(f.observed_speed) < 20
            ORDER BY max_congestion DESC;
        """
        rows = self.execute(query)
        return [
            SQLAnomaly(
                segment_id=row["segment_id"],
                name=row["name"],
                speed_limit=float(row["speed_limit"]),
                avg_speed_kmh=round(float(row["avg_speed_kmh"]), 2),
                avg_flow_vph=round(float(row["avg_flow_vph"]), 1),
                max_congestion=round(float(row["max_congestion"]), 3),
                speed_drop_pct=round(float(row["speed_drop_pct"]), 1),
            )
            for row in rows
        ]

    def close(self) -> None:
        self.conn.close()


# =============================================================================
# Layer 2: Semantic RDF/OWL
# =============================================================================

class SemanticLayer:
    """Semantic layer: OWL/RDF graph and SPARQL queries."""

    def __init__(self, owl_path: Path) -> None:
        self.owl_path = owl_path
        self.graph = Graph()
        self._load_ontology()

    def _load_ontology(self) -> None:
        if not self.owl_path.exists():
            raise FileNotFoundError(
                f"Файл онтології не знайдено: {self.owl_path}"
            )

        try:
            # strict=False prevents malformed xsd:dateTime lexical values
            # in the source ontology from aborting parsing.
            self.graph.parse(str(self.owl_path), format="xml")
        except Exception as exc:
            raise RuntimeError(
                f"Не вдалося завантажити OWL/RDF: {exc}"
            ) from exc

    def ontology_stats(self) -> dict[str, int]:
        query = """
            PREFIX owl: <http://www.w3.org/2002/07/owl#>

            SELECT
                (COUNT(DISTINCT ?cls) AS ?classes)
                (COUNT(DISTINCT ?op) AS ?object_properties)
                (COUNT(DISTINCT ?dp) AS ?data_properties)
                (COUNT(DISTINCT ?ind) AS ?individuals)
            WHERE {
                {
                    ?cls a owl:Class .
                }
                UNION {
                    ?op a owl:ObjectProperty .
                }
                UNION {
                    ?dp a owl:DatatypeProperty .
                }
                UNION {
                    ?ind a owl:NamedIndividual .
                }
            }
        """
        try:
            row = next(iter(self.graph.query(query)))
        except Exception as exc:
            raise RuntimeError(f"SPARQL-помилка статистики: {exc}") from exc

        return {
            "classes": int(row[0]),
            "object_properties": int(row[1]),
            "data_properties": int(row[2]),
            "individuals": int(row[3]),
        }

    def kq2_segment_and_vehicles(
        self, segment_local_id: str
    ) -> tuple[Optional[SegmentDetails], list[VehicleRoute]]:
        """
        KQ-2:
        Параметри RoadSegment + транспортні засоби потоку сегмента +
        маршрути цих транспортних засобів.
        """
        segment_uri = ONT[segment_local_id]

        segment_query = """
            PREFIX : <http://example.org/transport-ontology#>

            SELECT ?identifier ?label ?allowedSpeed ?laneCount ?length
            WHERE {
                VALUES ?segment { :DS001 }
                ?segment :identifier ?identifier ;
                         rdfs:label ?label ;
                         :allowedSpeed ?allowedSpeed ;
                         :laneCount ?laneCount ;
                         :length ?length .
            }
        """

        # The VALUES target is replaced only by a validated local identifier.
        if segment_local_id != "DS001":
            segment_query = segment_query.replace(
                "VALUES ?segment { :DS001 }",
                f"VALUES ?segment {{ :{segment_local_id} }}",
            )

        try:
            segment_rows = list(self.graph.query(segment_query))
        except Exception as exc:
            raise RuntimeError(f"SPARQL KQ-2 (segment): {exc}") from exc

        segment = None
        if segment_rows:
            row = segment_rows[0]
            segment = SegmentDetails(
                segment_uri=str(segment_uri),
                identifier=fmt(row.identifier),
                label=fmt(row.label),
                allowed_speed=float(row.allowedSpeed),
                lane_count=int(row.laneCount),
                length=float(row.length),
            )

        vehicle_query = """
            PREFIX : <http://example.org/transport-ontology#>

            SELECT DISTINCT
                ?vehicle ?vehicleIdentifier ?vehicleLabel
                ?vehicleType
                ?route ?routeIdentifier ?routeNumber ?routeLabel
            WHERE {
                ?flow :characterizes :DS001 ;
                      :hasVehicle ?vehicle .

                ?vehicle :identifier ?vehicleIdentifier ;
                         rdfs:label ?vehicleLabel ;
                         a ?vehicleType ;
                         :hasRoute ?route .

                ?route a :Route ;
                       :identifier ?routeIdentifier ;
                       :routeNumber ?routeNumber ;
                       rdfs:label ?routeLabel .

                FILTER(?vehicleType IN (:Vehicle, :Bus))
            }
        """

        if segment_local_id != "DS001":
            vehicle_query = vehicle_query.replace(
                ":DS001", f":{segment_local_id}"
            )

        try:
            rows = self.graph.query(vehicle_query)
        except Exception as exc:
            raise RuntimeError(f"SPARQL KQ-2 (vehicles): {exc}") from exc

        vehicles = [
            VehicleRoute(
                vehicle_uri=short_uri(row.vehicle),
                vehicle_identifier=fmt(row.vehicleIdentifier),
                vehicle_label=fmt(row.vehicleLabel),
                vehicle_type=short_uri(row.vehicleType),
                route_uri=short_uri(row.route),
                route_identifier=fmt(row.routeIdentifier),
                route_number=fmt(row.routeNumber),
                route_label=fmt(row.routeLabel),
            )
            for row in rows
        ]
        return segment, vehicles

    def kq3_incidents_and_decisions(
        self, segment_local_id: str
    ) -> list[IncidentDecision]:
        """
        KQ-3:
        Accident -> affects -> TrafficFlow -> characterizes -> RoadSegment,
        а також DecisionRule -> determines -> TransportDecision/RouteChange.

        У наданій OWL-моделі немає прямого предиката
        Accident -> DecisionRule. Тому правило та рішення вибираються
        з семантичного шару за зв'язком determines і типом RouteChange.
        """
        query = f"""
            PREFIX : <{ONTOLOGY_URI}>

            SELECT DISTINCT
                ?accident ?accidentIdentifier ?accidentLabel ?accidentDescription
                ?flow
                ?rule ?ruleLabel ?ruleDescription
                ?decision ?decisionType ?decisionLabel ?decisionDescription
                ?changedRoute ?changedRouteNumber
            WHERE {{
                ?flow :characterizes :{segment_local_id} .

                ?accident a :TrafficAccident ;
                          :affects ?flow ;
                          :identifier ?accidentIdentifier ;
                          rdfs:label ?accidentLabel ;
                          :description ?accidentDescription .

                ?rule a :DecisionRule ;
                      :determines ?decision ;
                      rdfs:label ?ruleLabel ;
                      :description ?ruleDescription .

                ?decision a ?decisionType ;
                          rdfs:label ?decisionLabel ;
                          :description ?decisionDescription ;
                          :changes ?changedRoute .

                ?changedRoute :routeNumber ?changedRouteNumber .

                FILTER(?decisionType IN (:TransportDecision, :RouteChange))
            }}
        """

        try:
            rows = self.graph.query(query)
        except Exception as exc:
            raise RuntimeError(f"SPARQL KQ-3: {exc}") from exc

        return [
            IncidentDecision(
                incident_uri=short_uri(row.accident),
                incident_identifier=fmt(row.accidentIdentifier),
                incident_label=fmt(row.accidentLabel),
                incident_description=truncate(fmt(row.accidentDescription)),
                flow_uri=short_uri(row.flow),
                rule_uri=short_uri(row.rule),
                rule_label=fmt(row.ruleLabel),
                rule_description=truncate(fmt(row.ruleDescription)),
                decision_uri=short_uri(row.decision),
                decision_type=short_uri(row.decisionType),
                decision_label=fmt(row.decisionLabel),
                decision_description=truncate(fmt(row.decisionDescription)),
                changed_route_uri=short_uri(row.changedRoute),
                changed_route_number=fmt(row.changedRouteNumber),
            )
            for row in rows
        ]

    def describe_event_for_vector_query(
        self, incidents: list[IncidentDecision], vehicles: list[VehicleRoute]
    ) -> str:
        parts = [
            "критичний транспортний інцидент",
            "ДТП",
            "блокування руху",
            "високий затор",
            "автобуси",
            "перенаправлення на альтернативний маршрут",
        ]

        if incidents:
            parts.append(incidents[0].incident_description)
            parts.append(incidents[0].rule_description)
            parts.append(incidents[0].decision_description)

        if vehicles:
            route_numbers = ", ".join(sorted({v.route_number for v in vehicles}))
            parts.append(f"маршрути автобусів {route_numbers}")

        return ". ".join(parts)


# =============================================================================
# Layer 3: Vector store
# =============================================================================

class VectorLayer:
    """ChromaDB vector layer with SentenceTransformer embeddings."""

    DOCUMENTS = [
        {
            "id": "REG-01-REROUTE",
            "title": "Регламент зміни маршрутної схеми при заторах",
            "category": "dispatch_rerouting",
            "severity": "critical",
            "text": (
                "У випадку виникнення критичного рівня завантаженості "
                "(коефіцієнт > 0.8) або повного блокування смуги внаслідок ДТП "
                "на магістральних ділянках, черговий диспетчер зобов'язаний "
                "негайно перенаправити міські автобуси на затверджені об'їзні "
                "маршрути через суміжні колекторні вулиці, активувати пріоритет "
                "світлофорів для громадського транспорту та сповістити пасажирів "
                "через динамічні табло."
            ),
        },
        {
            "id": "REG-02-SPEED-CTRL",
            "title": "Протокол адаптивного швидкісного регулювання",
            "category": "traffic_lights",
            "severity": "medium",
            "text": (
                "При помірному зниженні швидкості руху без наявності аварійних "
                "подій оптимізація пропускної спроможності забезпечується зміною "
                "тривалості зеленої фази світлофорних об'єктів («зелена хвиля») "
                "без корекції маршрутів руху рухомого складу."
            ),
        },
        {
            "id": "REG-03-ACCIDENT-SOP",
            "title": "Стандартна операційна процедура оформлення ДТП",
            "category": "emergency",
            "severity": "high",
            "text": (
                "При реєстрації дорожньо-транспортної пригоди з постраждалими "
                "черговий інженер передає координати патрульній поліції та "
                "кареті швидкої медичної допомоги, виставляє віртуальний бар'єр "
                "безпеки в навігаційних системах міста і фіксує номер "
                "пошкодженого борту ТЗ."
            ),
        },
        {
            "id": "REG-04-WEATHER-RESTRICT",
            "title": "Інструкція реагування на несприятливі погодні умови",
            "category": "weather_safety",
            "severity": "medium",
            "text": (
                "В умовах ожеледиці, снігопаду або затоплення проїзної частини "
                "швидкісний режим на мостах та шляхопроводах обмежується до "
                "30 км/год із виїздом снігоприбиральної та комунальної техніки."
            ),
        },
    ]

    def __init__(self, model_name: str = EMBEDDING_MODEL) -> None:
        self.model_name = model_name
        try:
            self.model = SentenceTransformer(model_name)
        except Exception as exc:
            raise RuntimeError(
                f"Не вдалося завантажити embedding-модель '{model_name}'. "
                "Перевірте доступ до Hugging Face та встановлення "
                "sentence-transformers."
            ) from exc

        try:
            self.client = chromadb.Client()
            try:
                self.client.delete_collection(VECTOR_COLLECTION)
            except Exception:
                pass

            self.collection = self.client.create_collection(
                name=VECTOR_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
            self._index_documents()
        except Exception as exc:
            raise RuntimeError(f"Помилка ініціалізації ChromaDB: {exc}") from exc

    def _index_documents(self) -> None:
        texts = [doc["text"] for doc in self.DOCUMENTS]
        ids = [doc["id"] for doc in self.DOCUMENTS]
        metadatas = [
            {
                "title": doc["title"],
                "category": doc["category"],
                "severity": doc["severity"],
            }
            for doc in self.DOCUMENTS
        ]

        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()

        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

    def search(self, query: str, top_k: int = 2) -> list[VectorHit]:
        try:
            query_embedding = self.model.encode(
                [query],
                normalize_embeddings=True,
                show_progress_bar=False,
            ).tolist()

            result = self.collection.query(
                query_embeddings=query_embedding,
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            raise RuntimeError(f"Помилка векторного пошуку: {exc}") from exc

        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        hits: list[VectorHit] = []
        for index, doc_id in enumerate(ids):
            metadata = metadatas[index] or {}
            distance = float(distances[index])
            hits.append(
                VectorHit(
                    rank=index + 1,
                    document_id=doc_id,
                    category=str(metadata.get("category", "Н/Д")),
                    severity=str(metadata.get("severity", "Н/Д")),
                    title=str(metadata.get("title", "Н/Д")),
                    similarity=clamp_similarity(distance),
                    distance=distance,
                    text=str(documents[index]),
                )
            )
        return hits


# =============================================================================
# Layer 4: Hybrid federation
# =============================================================================

class HybridMediator:
    """Federated mediation pipeline between SQL, RDF/OWL and vector layers."""

    def __init__(
        self,
        relational: RelationalLayer,
        semantic: SemanticLayer,
        vector: VectorLayer,
    ) -> None:
        self.relational = relational
        self.semantic = semantic
        self.vector = vector

    @staticmethod
    def normalize_segment_id(sql_id: str) -> str:
        """
        DS-001 -> DS001.
        The ontology individual uses the normalized URI :DS001.
        """
        normalized = sql_id.strip().upper().replace("-", "")
        if not normalized.startswith("DS") or not normalized[2:].isdigit():
            raise ValueError(f"Непідтримуваний ID дорожнього сегмента: {sql_id}")
        return normalized

    @staticmethod
    def build_mapping_table() -> list[MappingRow]:
        return [
            MappingRow(
                ":DS001",
                "SQLite.dim_road_segment.segment_id",
                "DS-001 -> прибрати дефіс -> DS001 -> ONT:DS001",
            ),
            MappingRow(
                ":allowedSpeed",
                "dim_road_segment.speed_limit",
                "числове поле km/h без зміни одиниць",
            ),
            MappingRow(
                ":laneCount",
                "dim_road_segment.lanes",
                "ціле число смуг",
            ),
            MappingRow(
                ":length",
                "OWL RoadSegment.length",
                "float; метри",
            ),
            MappingRow(
                ":hasVehicle / :Bus",
                "OWL TrafficFlow.hasVehicle",
                "URI індивіда -> локальний URI; фільтр Vehicle/Bus",
            ),
            MappingRow(
                ":routeNumber",
                "OWL Route.routeNumber",
                "значення приводиться до рядкового номера маршруту",
            ),
            MappingRow(
                ":TrafficAccident",
                "OWL individual + :affects",
                "подія пов'язується з потоком, який :characterizes сегмент",
            ),
            MappingRow(
                ":DecisionRule -> :determines",
                "OWL DecisionRule",
                "семантичне правило -> TransportDecision/RouteChange",
            ),
            MappingRow(
                "Vector document ID",
                "ChromaDB document metadata",
                "REG-* зберігається без трансформації",
            ),
        ]

    def print_mapping_table(self) -> None:
        print_banner("MAPPING TABLE: SQL <-> OWL/RDF <-> VECTOR")

        header = (
            f"{'Термін онтології':<28} | "
            f"{'Джерело / поле':<38} | "
            f"{'Правило нормалізації'}"
        )
        print(header)
        print("-" * len(header))
        for row in self.build_mapping_table():
            print(
                f"{row.ontology_term:<28} | "
                f"{row.source_field:<38} | "
                f"{row.normalization_rule}"
            )

    def run_kq1(self) -> list[SQLAnomaly]:
        print_banner("KQ-1 — Операційний SQL шар")

        rows = self.relational.kq1_critical_segments()

        header = (
            f"{'Segment':<10} | {'Назва':<35} | {'Ліміт':>7} | "
            f"{'Сер. швидк.':>12} | {'Потік':>9} | "
            f"{'Max Cong.':>10} | {'Спад':>9}"
        )
        print(header)
        print("-" * len(header))

        for row in rows:
            print(
                f"{row.segment_id:<10} | "
                f"{row.name:<35} | "
                f"{row.speed_limit:>7.0f} | "
                f"{row.avg_speed_kmh:>12.2f} | "
                f"{row.avg_flow_vph:>9.1f} | "
                f"{row.max_congestion:>10.3f} | "
                f"{row.speed_drop_pct:>8.1f}%"
            )

        if rows:
            print_status(
                f"Критичних сегментів: {len(rows)}; "
                f"найбільш аномальний: {rows[0].segment_id}"
            )
        else:
            print_status("Критичних сегментів не знайдено", "WARN")

        return rows

    def run_kq2(self, segment_local_id: str) -> tuple[
        Optional[SegmentDetails], list[VehicleRoute]
    ]:
        print_banner("KQ-2 — Семантичний шар: топологія та рухомий склад")

        segment, vehicles = self.semantic.kq2_segment_and_vehicles(
            segment_local_id
        )

        if segment:
            print(
                f"Сегмент: {segment.identifier} | {segment.label}\n"
                f"  URI:              {segment.segment_uri}\n"
                f"  Дозволена швидкість: {segment.allowed_speed:.1f} км/год\n"
                f"  Кількість смуг:      {segment.lane_count}\n"
                f"  Довжина:             {segment.length:.1f} м"
            )
        else:
            print_status("Сегмент не знайдено в OWL", "WARN")

        print("\nЗакріплений транспорт:")
        header = (
            f"{'Vehicle':<14} | {'Тип':<8} | {'Ідентифікатор':<14} | "
            f"{'Route':<10} | {'№ маршруту':<12}"
        )
        print(header)
        print("-" * len(header))

        for vehicle in vehicles:
            print(
                f"{vehicle.vehicle_uri:<14} | "
                f"{vehicle.vehicle_type:<8} | "
                f"{vehicle.vehicle_identifier:<14} | "
                f"{vehicle.route_uri:<10} | "
                f"{vehicle.route_number:<12}"
            )

        print_status(f"Знайдено транспортних засобів: {len(vehicles)}")
        return segment, vehicles

    def run_kq3(
        self, segment_local_id: str
    ) -> list[IncidentDecision]:
        print_banner("KQ-3 — Семантичний шар: інциденти, правила та рішення")

        rows = self.semantic.kq3_incidents_and_decisions(segment_local_id)

        if not rows:
            print_status("Подій та рішень для сегмента не знайдено", "WARN")
            return rows

        for index, row in enumerate(rows, start=1):
            print(f"\n#{index} Подія: {row.incident_label}")
            print(f"  ID:          {row.incident_identifier}")
            print(f"  Опис:        {row.incident_description}")
            print(f"  Потік:       {row.flow_uri}")
            print(f"  Правило:     {row.rule_uri} — {row.rule_label}")
            print(f"  Опис правила:{row.rule_description}")
            print(
                f"  Рішення:     {row.decision_uri} — "
                f"{row.decision_label}"
            )
            print(f"  Опис рішення:{row.decision_description}")
            print(
                f"  Змінюваний маршрут: {row.changed_route_uri}, "
                f"№ {row.changed_route_number}"
            )

        print_status(f"Знайдено семантичних сценаріїв: {len(rows)}")
        return rows

    def run_kq4(self, query: str = KQ4_QUERY) -> list[VectorHit]:
        print_banner("KQ-4 — Векторний шар: семантичний пошук")
        print(f'Запит: "{query}"')

        hits = self.vector.search(query, top_k=2)

        print("\nTop-2 результатів:")
        for hit in hits:
            print(
                f"\n#{hit.rank} [{hit.document_id}] "
                f"similarity={hit.similarity:.4f} "
                f"(cosine distance={hit.distance:.4f})"
            )
            print(f"  Категорія: {hit.category}")
            print(f"  Рівень:    {hit.severity}")
            print(f"  Заголовок: {hit.title}")
            print(f"  Фрагмент:  {truncate(hit.text)}")

        print_status(f"Отримано векторних результатів: {len(hits)}")
        return hits

    def run_kq5(
        self,
        anomalies: list[SQLAnomaly],
        incidents: list[IncidentDecision],
        vehicles: list[VehicleRoute],
    ) -> list[VectorHit]:
        print_banner("KQ-5 — Federated Mediation Pipeline")

        if not anomalies:
            print_status(
                "SQL не виявив аномального сегмента; федеративний pipeline "
                "не може продовжитися.",
                "WARN",
            )
            return []

        # Step A: SQL result.
        target = anomalies[0]
        print(
            f"[A] SQL -> {target.segment_id}; "
            f"speed={target.avg_speed_kmh:.2f} км/год; "
            f"congestion={target.max_congestion:.3f}"
        )

        # Step B: Data normalization / mapping.
        semantic_id = self.normalize_segment_id(target.segment_id)
        print(
            f"[B] Mapping -> {target.segment_id} "
            f"=> :{semantic_id}"
        )

        # Step C: semantic enrichment.
        print(
            f"[C] SPARQL -> {len(vehicles)} транспортний засіб/засоби, "
            f"{len(incidents)} сценарій/сценарії"
        )

        # Step D: construct a targeted semantic vector query.
        semantic_context = self.semantic.describe_event_for_vector_query(
            incidents, vehicles
        )
        vector_query = (
            f"Сегмент :{semantic_id}. "
            f"Середня швидкість {target.avg_speed_kmh:.1f} км/год "
            f"при дозволених {target.speed_limit:.0f} км/год. "
            f"Індекс затору {target.max_congestion:.2f}. "
            f"{semantic_context}. "
            f"Що робити диспетчеру для автобусів?"
        )
        print(f"[D] Vector query -> {vector_query}")

        hits = self.vector.search(vector_query, top_k=2)
        best = hits[0] if hits else None

        # Step E: decision-support report.
        print_banner("DECISION SUPPORT SUMMARY")

        print(f"1. Проблемний сегмент: {target.segment_id} — {target.name}")
        print(
            f"   Середня швидкість: {target.avg_speed_kmh:.2f} км/год; "
            f"спад: {target.speed_drop_pct:.1f}%; "
            f"congestion: {target.max_congestion:.3f}"
        )

        print(f"2. Нормалізований OWL URI: :{semantic_id}")

        if vehicles:
            route_numbers = sorted({v.route_number for v in vehicles})
            vehicle_ids = sorted({v.vehicle_identifier for v in vehicles})
            print(f"3. Постраждалий транспорт: {', '.join(vehicle_ids)}")
            print(f"   Маршрути: {', '.join(route_numbers)}")
        else:
            print("3. Постраждалий транспорт: Н/Д")

        if incidents:
            incident = incidents[0]
            print(
                f"4. Подія: {incident.incident_identifier} — "
                f"{incident.incident_label}"
            )
            print(
                f"   Правило: {incident.rule_label}; "
                f"рішення: {incident.decision_label}"
            )
        else:
            print("4. Подія: Н/Д")

        if best:
            print(
                f"5. Найрелевантніший регламент: {best.document_id}\n"
                f"   {best.title}\n"
                f"   Similarity: {best.similarity:.4f}\n"
                f"   Інструкція: {truncate(best.text, 280)}"
            )

        print(
            "\n6. Результат mediation: "
            "SQL виявляє аномалію -> URI нормалізується -> "
            "OWL додає контекст події/транспорту -> "
            "ChromaDB знаходить нормативну інструкцію."
        )

        return hits


# =============================================================================
# Main
# =============================================================================

def resolve_ontology_path() -> Path:
    """
    Шукає update.owl:
      1) поруч зі скриптом;
      2) у поточній робочій директорії.
    """
    candidates = [
        Path(__file__).resolve().parent / "update.owl",
        Path.cwd() / "update.owl",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    searched = "\n".join(f"  - {path}" for path in candidates)
    raise FileNotFoundError(
        "update.owl не знайдено. Очікувані місця:\n" + searched
    )


def main() -> int:
    print_banner(
        "Лабораторна робота №14 — Проєктування запитів "
        "до гібридного сховища знань"
    )

    print(
        "Архітектура: SQLite -> RDF/OWL/SPARQL -> ChromaDB -> "
        "Federated Mediation\n"
    )

    relational: Optional[RelationalLayer] = None

    try:
        owl_path = resolve_ontology_path()
        print_status(f"OWL-файл: {owl_path}")

        # Initialize layers.
        relational = RelationalLayer()
        semantic = SemanticLayer(owl_path)

        stats = semantic.ontology_stats()
        print_status(
            "OWL завантажено: "
            f"{len(semantic.graph)} RDF-триплетів; "
            f"classes={stats['classes']}, "
            f"objectProperties={stats['object_properties']}, "
            f"dataProperties={stats['data_properties']}, "
            f"individuals={stats['individuals']}"
        )

        vector = VectorLayer()

        mediator = HybridMediator(
            relational=relational,
            semantic=semantic,
            vector=vector,
        )

        mediator.print_mapping_table()

        # KQ-1.
        anomalies = mediator.run_kq1()
        if not anomalies:
            raise RuntimeError(
                "KQ-1 не повернув критичного сегмента. "
                "Перевірте тестові SQL-дані."
            )

        target_sql_id = anomalies[0].segment_id
        target_semantic_id = mediator.normalize_segment_id(target_sql_id)

        # KQ-2.
        _, vehicles = mediator.run_kq2(target_semantic_id)

        # KQ-3.
        incidents = mediator.run_kq3(target_semantic_id)

        # KQ-4.
        mediator.run_kq4(KQ4_QUERY)

        # KQ-5.
        mediator.run_kq5(anomalies, incidents, vehicles)

        print_banner("ЛАБОРАТОРНА РОБОТА №14 ЗАВЕРШЕНА")
        print_status(
            "Усі 5 компетентнісних запитів виконано: "
            "SQL + SPARQL + Vector Search + Federation.",
        )
        return 0

    except KeyboardInterrupt:
        print_status("Виконання перервано користувачем.", "WARN")
        return 130
    except Exception as exc:
        print_status(f"Критична помилка: {exc}", "ERROR")
        return 1
    finally:
        if relational is not None:
            relational.close()


if __name__ == "__main__":
    sys.exit(main())
