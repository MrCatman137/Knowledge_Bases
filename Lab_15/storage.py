"""
storage.py - Трикомпонентне гібридне сховище знань (HKB):
1. RelationalLayer (SQLite)
2. SemanticLayer (RDF/OWL Graph)
3. VectorLayer (ChromaDB + SentenceTransformers)
"""

from __future__ import annotations

import sqlite3
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

import rdflib.term
rdflib.term._warn_on_lexical_failure = False
import logging
logging.getLogger("rdflib").setLevel(logging.CRITICAL)

import chromadb
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS
from sentence_transformers import SentenceTransformer

ONTOLOGY_URI = "http://example.org/transport-ontology#"
ONT = Namespace(ONTOLOGY_URI)
VECTOR_COLLECTION = "transport_regulations"


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


class RelationalLayer:
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
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
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
                FOREIGN KEY(segment_id) REFERENCES dim_road_segment(segment_id)
            );
            """
        )

    def _seed_data(self) -> None:
        self.conn.executemany(
            "INSERT INTO dim_road_segment VALUES (?, ?, ?, ?, ?)", self.SEGMENTS
        )
        self.conn.executemany(
            """
            INSERT INTO fact_traffic_observations
            (timestamp, segment_id, hourly_flow, observed_speed, is_peak_hour, congestion_index)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            self.OBSERVATIONS,
        )
        self.conn.commit()

    def get_all_segments(self) -> list[dict]:
        cur = self.conn.execute("SELECT * FROM dim_road_segment ORDER BY segment_id")
        return [dict(r) for r in cur.fetchall()]

    def find_anomalies(self) -> list[SQLAnomaly]:
        query = """
            SELECT
                d.segment_id, d.name, d.speed_limit,
                AVG(f.observed_speed) AS avg_speed_kmh,
                AVG(f.hourly_flow) AS avg_flow_vph,
                MAX(f.congestion_index) AS max_congestion,
                (1.0 - AVG(f.observed_speed) / d.speed_limit) * 100.0 AS speed_drop_pct
            FROM fact_traffic_observations AS f
            JOIN dim_road_segment AS d ON d.segment_id = f.segment_id
            WHERE f.is_peak_hour = 1 AND d.speed_limit = 50
            GROUP BY d.segment_id, d.name, d.speed_limit
            HAVING AVG(f.observed_speed) < 20
            ORDER BY max_congestion DESC;
        """
        rows = list(self.conn.execute(query))
        return [
            SQLAnomaly(
                segment_id=r["segment_id"],
                name=r["name"],
                speed_limit=float(r["speed_limit"]),
                avg_speed_kmh=round(float(r["avg_speed_kmh"]), 2),
                avg_flow_vph=round(float(r["avg_flow_vph"]), 1),
                max_congestion=round(float(r["max_congestion"]), 3),
                speed_drop_pct=round(float(r["speed_drop_pct"]), 1),
            )
            for r in rows
        ]

    def get_segment_status(self, segment_id: str) -> Optional[dict]:
        cur = self.conn.execute(
            """
            SELECT d.segment_id, d.name, d.speed_limit, d.lanes,
                   AVG(f.observed_speed) as avg_speed, MAX(f.congestion_index) as max_cong
            FROM dim_road_segment d
            LEFT JOIN fact_traffic_observations f ON d.segment_id = f.segment_id
            WHERE d.segment_id = ?
            GROUP BY d.segment_id
            """,
            (segment_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


class SemanticLayer:
    QUERY_CLASS_ALIASES = {
        "електробус": "ElectricBus",
        "електричн": "ElectricBus",
        "electric bus": "ElectricBus",
        "трамва": "Tram",
        "tram": "Tram",
        "оператор": "TransitOperator",
        "перевізник": "TransitOperator",
        "operator": "TransitOperator",
        "розклад": "TransitSchedule",
        "schedule": "TransitSchedule",
        "інтервал руху": "TransitSchedule",
        "частота руху": "TransitSchedule",
        "заряд": "ChargingStation",
        "charging station": "ChargingStation",
        "погод": "WeatherObservation",
        "дощ": "WeatherObservation",
        "weather": "WeatherObservation",
        "екстрен": "EmergencyService",
        "служб реаг": "EmergencyService",
        "emergency service": "EmergencyService",
        "камер": "TrafficCamera",
        "camera": "TrafficCamera",
        "зупин": "BusStop",
        "bus stop": "BusStop",
        "сегмент": "RoadSegment",
        "segment": "RoadSegment",
        "дорожн мереж": "RoadNetwork",
        "road network": "RoadNetwork",
        "маршрут": "Route",
        "route": "Route",
        "транспортн засоб": "Vehicle",
        "vehicle": "Vehicle",
        "автобус": "Bus",
        "bus": "Bus",
    }
    RESTRICTION_TERMS = ("обмеж", "restriction", "кардиналь", "аксіом", "axiom")
    COUNT_TERMS = ("скільки", "кількість", "count", "статистик")
    QUERY_STOP_WORDS = {
        "які", "який", "яка", "яке", "є", "має", "мають", "про", "для",
        "що", "чи", "в", "на", "і", "та", "the", "what", "which", "are",
        "has", "have", "of", "for", "show", "list", "tell", "me",
    }
    LOCATION_PREPOSITIONS = {"на", "у", "в", "біля", "поблизу", "in", "on", "at", "near"}
    LOCATION_DESCRIPTORS = {
        "вулиця", "вулиці", "вулицю", "вул", "проспект", "проспекту", "просп",
        "місто", "місті", "міста", "район", "районі", "району",
        "сегмент", "сегменті", "ділянка", "ділянці", "дорога", "дорозі",
        "мережа", "мережі", "система", "системі", "місяці",
    }

    def __init__(self, owl_path: Path) -> None:
        self.owl_path = owl_path
        self.graph = Graph()
        self.graph.parse(str(self.owl_path), format="xml")

    def _label(self, resource: URIRef) -> str:
        label = self.graph.value(resource, RDFS.label)
        return str(label) if label is not None else str(resource).rsplit("#", 1)[-1]

    def _class_descendants(self, class_uri: URIRef) -> set[URIRef]:
        descendants = {class_uri}
        pending = [class_uri]
        while pending:
            parent = pending.pop()
            for child in self.graph.subjects(RDFS.subClassOf, parent):
                if isinstance(child, URIRef) and child not in descendants:
                    descendants.add(child)
                    pending.append(child)
        return descendants

    def _class_individuals(self, class_uri: URIRef) -> list[URIRef]:
        class_tree = self._class_descendants(class_uri)
        individuals = {
            subject
            for class_item in class_tree
            for subject in self.graph.subjects(RDF.type, class_item)
            if isinstance(subject, URIRef)
            and (subject, RDF.type, OWL.NamedIndividual) in self.graph
        }
        return sorted(individuals, key=lambda item: self._label(item).casefold())

    def _has_unknown_location_scope(self, query: str) -> bool:
        raw_tokens = re.findall(r"[\w-]+", query)
        tokens = [token.casefold() for token in raw_tokens]
        graph_terms = " ".join(
            [str(subject).rsplit("#", 1)[-1] for subject in self.graph.subjects()]
            + [str(value) for value in self.graph.objects()]
        ).casefold()
        normalized_graph = re.sub(r"[- ]", "", graph_terms)
        for index, token in enumerate(tokens[:-1]):
            if token not in self.LOCATION_PREPOSITIONS:
                continue
            location_index = index + 1
            while (
                location_index < len(tokens)
                and tokens[location_index] in self.LOCATION_DESCRIPTORS
            ):
                location_index += 1
            if location_index >= len(tokens):
                continue
            raw_location = raw_tokens[location_index]
            location = tokens[location_index]
            is_identifier = bool(
                re.fullmatch(
                    r"(?:DS|BUS|R|SCH|STOP|CAM|WX|ACC|CHG|OP|TRAM)[- ]?\d+[A-Z]?",
                    raw_location,
                    re.IGNORECASE,
                )
            )
            if not raw_location[0].isupper() and not is_identifier:
                continue
            normalized_location = re.sub(r"[- ]", "", location)
            location_forms = {normalized_location}
            for suffix in ("ові", "еві", "ами", "ями", "ах", "ях", "і", "ї", "а", "я", "у", "ю", "е", "є"):
                if len(normalized_location) - len(suffix) >= 4 and normalized_location.endswith(suffix):
                    location_forms.add(normalized_location[:-len(suffix)])
            if not any(form in normalized_graph for form in location_forms):
                return True
        return False

    def _individual_facts(self, individual: URIRef) -> list[str]:
        facts: list[str] = []
        ignored_predicates = {
            RDF.type, RDFS.label, RDFS.comment, ONT.identifier, ONT.description,
        }
        for predicate, value in sorted(
            self.graph.predicate_objects(individual), key=lambda pair: str(pair[0])
        ):
            if predicate in ignored_predicates:
                continue
            if isinstance(value, URIRef):
                value_text = self._label(value)
                identifier = self.graph.value(value, ONT.identifier)
                if identifier is not None:
                    value_text += f" (ID: {identifier})"
            else:
                value_text = str(value)
            facts.append(f"{self._label(predicate)}: {value_text}")
        for subject, predicate in sorted(
            self.graph.subject_predicates(individual),
            key=lambda pair: (str(pair[0]), str(pair[1])),
        ):
            if predicate in ignored_predicates or not isinstance(subject, URIRef):
                continue
            subject_label = self._label(subject)
            identifier = self.graph.value(subject, ONT.identifier)
            if identifier is not None:
                subject_label += f" (ID: {identifier})"
            facts.append(f"{self._label(predicate)} з боку «{subject_label}»")
        return facts

    def _individual_search_text(self, individual: URIRef) -> str:
        terms = [
            str(individual).rsplit("#", 1)[-1],
            self._label(individual),
            *(
                str(value)
                for predicate in (ONT.identifier, ONT.description)
                for value in self.graph.objects(individual, predicate)
            ),
        ]
        related_resources = [
            value
            for _, value in self.graph.predicate_objects(individual)
            if isinstance(value, URIRef)
        ]
        related_resources.extend(
            subject
            for subject, _ in self.graph.subject_predicates(individual)
            if isinstance(subject, URIRef)
        )
        for resource in related_resources:
            terms.extend(
                (
                    str(resource).rsplit("#", 1)[-1],
                    self._label(resource),
                    *(str(value) for value in self.graph.objects(resource, ONT.identifier)),
                )
            )
        return " ".join(terms).casefold()

    def _render_restrictions(self) -> list[str]:
        descriptions = []
        restriction_predicates = (
            (OWL.minCardinality, "щонайменше"),
            (OWL.maxCardinality, "не більше"),
            (OWL.cardinality, "рівно"),
            (OWL.minQualifiedCardinality, "щонайменше"),
            (OWL.maxQualifiedCardinality, "не більше"),
            (OWL.qualifiedCardinality, "рівно"),
        )
        for class_uri in sorted(self.graph.subjects(RDF.type, OWL.Class), key=str):
            for restriction in self.graph.objects(class_uri, RDFS.subClassOf):
                if (restriction, RDF.type, OWL.Restriction) not in self.graph:
                    continue
                prop = self.graph.value(restriction, OWL.onProperty)
                if prop is None:
                    continue
                target_class = self.graph.value(restriction, OWL.onClass)
                target = (
                    f" об'єктів класу «{self._label(target_class)}»"
                    if isinstance(target_class, URIRef) else ""
                )
                rendered = None
                for predicate, phrase in restriction_predicates:
                    amount = self.graph.value(restriction, predicate)
                    if amount is not None:
                        rendered = f"{phrase} {amount}{target}"
                        break
                some_values = self.graph.value(restriction, OWL.someValuesFrom)
                if rendered is None and isinstance(some_values, URIRef):
                    rendered = f"має бути пов'язаний з «{self._label(some_values)}»"
                if rendered:
                    descriptions.append(
                        f"• {self._label(class_uri)} — {self._label(prop)}: {rendered}."
                    )
        return descriptions

    def answer_ontology_query(self, query: str) -> Optional[dict[str, Any]]:
        normalized_query = query.casefold()
        if self._has_unknown_location_scope(query):
            return None

        if any(term in normalized_query for term in self.COUNT_TERMS):
            stats = self.get_stats()
            if any(term in normalized_query for term in ("клас", "class")):
                answer = f"В онтології {stats['classes']} класів."
            elif any(term in normalized_query for term in ("індив", "individual", "сутност")):
                answer = f"В онтології {stats['individuals']} іменованих індивідів."
            else:
                answer = (
                    f"В онтології {stats['classes']} класів, "
                    f"{stats['individuals']} іменованих індивідів та {stats['triples']} триплетів."
                )
            return {"answer": answer, "source": ":Ontology"}

        if any(term in normalized_query for term in self.RESTRICTION_TERMS):
            restrictions = self._render_restrictions()
            if not restrictions:
                return None
            return {
                "answer": (
                    "В онтології описано OWL-обмеження зв'язків (це логічні аксіоми для "
                    "виведення, а не автоматичні перевірки введення даних):\n"
                    + "\n".join(restrictions)
                ),
                "source": ":OntologyRestrictions",
            }

        matched_classes: list[URIRef] = []
        for alias, class_name in self.QUERY_CLASS_ALIASES.items():
            if alias in normalized_query:
                class_uri = ONT[class_name]
                if class_uri not in matched_classes:
                    matched_classes.append(class_uri)
        matched_classes = [
            class_uri
            for class_uri in matched_classes
            if not any(
                class_uri != other_class
                and other_class in self._class_descendants(class_uri)
                for other_class in matched_classes
            )
        ]

        entity_ids = re.findall(
            r"\b(?:DS|BUS|R|SCH|STOP|CAM|WX|ACC|CHG|OP|TRAM)[- ]?\d+[A-Z]?\b",
            query,
            re.IGNORECASE,
        )
        selected: list[tuple[URIRef, URIRef]] = []
        for class_uri in matched_classes:
            for individual in self._class_individuals(class_uri):
                searchable = self._individual_search_text(individual)
                if entity_ids and not any(
                    re.sub(r"[- ]", "", value).casefold()
                    in re.sub(r"[- ]", "", searchable)
                    for value in entity_ids
                ):
                    continue
                selected.append((class_uri, individual))

        if not matched_classes:
            tokens = [
                token
                for token in re.findall(r"[\w-]+", normalized_query)
                if len(token) >= 3 and token not in self.QUERY_STOP_WORDS
            ]
            matches = []
            for individual in self.graph.subjects(RDF.type, OWL.NamedIndividual):
                if not isinstance(individual, URIRef):
                    continue
                searchable = self._individual_search_text(individual)
                score = sum(token in searchable for token in tokens)
                if score:
                    matches.append((score, individual))
            matches.sort(key=lambda item: (-item[0], self._label(item[1]).casefold()))
            selected = [
                (
                    next(iter(self.graph.objects(individual, RDF.type)), ONT.TransportObject),
                    individual,
                )
                for _, individual in matches[:5]
            ]

        if not selected:
            return None

        lines = []
        source_ids = []
        for class_uri, individual in selected[:12]:
            line = f"• {self._label(individual)}"
            identifier = self.graph.value(individual, ONT.identifier)
            if identifier is not None:
                line += f" (ID: {identifier})"
            facts = self._individual_facts(individual)
            if facts:
                line += " — " + "; ".join(facts[:6])
            lines.append(line)
            source_ids.append(f":{str(individual).rsplit('#', 1)[-1]}")

        type_labels = list(dict.fromkeys(self._label(item) for item in matched_classes))
        heading = (
            "Онтологія містить такі дані: " + ", ".join(type_labels) + "."
            if type_labels else "Знайдені відповідні сутності онтології:"
        )
        return {
            "answer": heading + "\n" + "\n".join(lines),
            "source": ", ".join(dict.fromkeys(source_ids)),
        }

    def get_stats(self) -> dict[str, int]:
        q = """
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            SELECT (COUNT(DISTINCT ?cls) AS ?c) (COUNT(DISTINCT ?ind) AS ?i)
            WHERE {
                { ?cls a owl:Class } UNION { ?ind a owl:NamedIndividual }
            }
        """
        row = next(iter(self.graph.query(q)))
        return {"triples": len(self.graph), "classes": int(row[0]), "individuals": int(row[1])}

    def get_all_buses(self) -> list[dict]:
        """
        Вилучає всі автобуси з онтології з їхніми номерами маршрутів.
        Підтримує як прямий предикат :routeNumber, так і обхід через :hasRoute.
        """
        query = f"""
            PREFIX : <{ONTOLOGY_URI}>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

            SELECT DISTINCT ?bus ?id ?label ?routeNum WHERE {{
                ?bus a ?busClass .
                ?busClass rdfs:subClassOf* :Bus .
                OPTIONAL {{ ?bus :identifier ?id }}
                OPTIONAL {{ ?bus rdfs:label ?label }}
                OPTIONAL {{
                    {{ ?bus :routeNumber ?routeNum }}
                    UNION
                    {{
                        ?bus :hasRoute ?route .
                        ?route :routeNumber ?routeNum .
                    }}
                }}
            }}
        """
        rows = self.graph.query(query)
        res = []
        seen = set()
        for r in rows:
            bus_uri = str(r.bus).rsplit("#", 1)[-1]
            bus_id = str(r.id) if r.id else bus_uri
            if bus_id not in seen:
                seen.add(bus_id)
                res.append({
                    "uri": bus_uri,
                    "identifier": bus_id,
                    "label": str(r.label) if r.label else bus_uri,
                    "routeNumber": str(r.routeNum) if r.routeNum else "не вказано"
                })
        return res

    def get_segment_and_vehicles(self, segment_local_id: str):
        seg_query = f"""
            PREFIX : <{ONTOLOGY_URI}>
            SELECT ?identifier ?label ?allowedSpeed ?laneCount ?length
            WHERE {{
                VALUES ?segment {{ :{segment_local_id} }}
                ?segment :identifier ?identifier ;
                         rdfs:label ?label ;
                         :allowedSpeed ?allowedSpeed ;
                         :laneCount ?laneCount ;
                         :length ?length .
            }}
        """
        seg_rows = list(self.graph.query(seg_query))
        seg = None
        if seg_rows:
            r = seg_rows[0]
            seg = SegmentDetails(
                segment_uri=f"{ONTOLOGY_URI}{segment_local_id}",
                identifier=str(r.identifier),
                label=str(r.label),
                allowed_speed=float(r.allowedSpeed),
                lane_count=int(r.laneCount),
                length=float(r.length),
            )

        v_query = f"""
            PREFIX : <{ONTOLOGY_URI}>
            SELECT DISTINCT ?vehicle ?vehicleIdentifier ?vehicleLabel ?vehicleType
                            ?route ?routeIdentifier ?routeNumber ?routeLabel
            WHERE {{
                ?flow :characterizes :{segment_local_id} ;
                      :hasVehicle ?vehicle .
                ?vehicle :identifier ?vehicleIdentifier ;
                         rdfs:label ?vehicleLabel ;
                         a ?vehicleType ;
                         :hasRoute ?route .
                ?route :identifier ?routeIdentifier ;
                       :routeNumber ?routeNumber ;
                       rdfs:label ?routeLabel .
            }}
        """
        v_rows = self.graph.query(v_query)
        vehicles = [
            VehicleRoute(
                vehicle_uri=str(r.vehicle).rsplit("#", 1)[-1],
                vehicle_identifier=str(r.vehicleIdentifier),
                vehicle_label=str(r.vehicleLabel),
                vehicle_type=str(r.vehicleType).rsplit("#", 1)[-1],
                route_uri=str(r.route).rsplit("#", 1)[-1],
                route_identifier=str(r.routeIdentifier),
                route_number=str(r.routeNumber),
                route_label=str(r.routeLabel),
            )
            for r in v_rows
        ]
        return seg, vehicles

    def get_incidents_and_rules(self, segment_local_id: str) -> list[IncidentDecision]:
        query = f"""
            PREFIX : <{ONTOLOGY_URI}>
            SELECT DISTINCT ?accident ?accidentIdentifier ?accidentLabel ?accidentDescription
                            ?flow ?rule ?ruleLabel ?ruleDescription
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
            }}
        """
        rows = self.graph.query(query)
        return [
            IncidentDecision(
                incident_uri=str(r.accident).rsplit("#", 1)[-1],
                incident_identifier=str(r.accidentIdentifier),
                incident_label=str(r.accidentLabel),
                incident_description=" ".join(str(r.accidentDescription).split()),
                flow_uri=str(r.flow).rsplit("#", 1)[-1],
                rule_uri=str(r.rule).rsplit("#", 1)[-1],
                rule_label=str(r.ruleLabel),
                rule_description=" ".join(str(r.ruleDescription).split()),
                decision_uri=str(r.decision).rsplit("#", 1)[-1],
                decision_type=str(r.decisionType).rsplit("#", 1)[-1],
                decision_label=str(r.decisionLabel),
                decision_description=" ".join(str(r.decisionDescription).split()),
                changed_route_uri=str(r.changedRoute).rsplit("#", 1)[-1],
                changed_route_number=str(r.changedRouteNumber),
            )
            for r in rows
        ]


class VectorLayer:
    DOCUMENTS = [
        {
            "id": "REG-01-REROUTE",
            "title": "Регламент зміни маршрутної схеми при заторах",
            "category": "dispatch_rerouting",
            "severity": "critical",
            "text": (
                "У випадку виникнення критичного рівня завантаженості (коефіцієнт > 0.8) "
                "або повного блокування смуги внаслідок ДТП на магістральних ділянках, "
                "черговий диспетчер зобов'язаний негайно перенаправити міські автобуси "
                "на затверджені об'їзні маршрути через суміжні колекторні вулиці, "
                "активувати пріоритет світлофорів для громадського транспорту та "
                "сповістити пасажирів через динамічні табло."
            ),
        },
        {
            "id": "REG-02-SPEED-CTRL",
            "title": "Протокол адаптивного швидкісного регулювання",
            "category": "traffic_lights",
            "severity": "medium",
            "text": (
                "При помірному зниженні швидкості руху без наявності аварійних подій "
                "оптимізація пропускної спроможності забезпечується зміною тривалості "
                "зеленої фази світлофорних об'єктів («зелена хвиля») без корекції маршрутів."
            ),
        },
        {
            "id": "REG-03-ACCIDENT-SOP",
            "title": "Стандартна операційна процедура оформлення ДТП",
            "category": "emergency",
            "severity": "high",
            "text": (
                "При реєстрації дорожньо-транспортної пригоди з постраждалими черговий "
                "інженер передає координати патрульній поліції та швидкій допомозі, "
                "виставляє віртуальний бар'єр безпеки в навігаційних системах міста."
            ),
        },
        {
            "id": "REG-04-WEATHER-RESTRICT",
            "title": "Інструкція реагування на несприятливі погодні умови",
            "category": "weather_safety",
            "severity": "medium",
            "text": (
                "В умовах ожеледиці, снігопаду або затоплення проїзної частини швидкісний "
                "режим на мостах обмежується до 30 км/год із виїздом снігоприбиральної техніки."
            ),
        },
    ]

    def __init__(self, model_name: str) -> None:
        self.model = SentenceTransformer(model_name)
        self.client = chromadb.Client()
        try:
            self.client.delete_collection(VECTOR_COLLECTION)
        except Exception:
            pass
        self.collection = self.client.create_collection(
            name=VECTOR_COLLECTION, metadata={"hnsw:space": "cosine"}
        )
        self._seed()

    def _seed(self) -> None:
        texts = [d["text"] for d in self.DOCUMENTS]
        ids = [d["id"] for d in self.DOCUMENTS]
        metadatas = [
            {"title": d["title"], "category": d["category"], "severity": d["severity"]}
            for d in self.DOCUMENTS
        ]
        embeddings = self.model.encode(texts, normalize_embeddings=True).tolist()
        self.collection.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)

    def search(self, query: str, top_k: int = 2) -> list[VectorHit]:
        q_emb = self.model.encode([query], normalize_embeddings=True).tolist()
        res = self.collection.query(
            query_embeddings=q_emb, n_results=top_k, include=["documents", "metadatas", "distances"]
        )
        ids = res.get("ids", [[]])[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]

        hits: list[VectorHit] = []
        for i, doc_id in enumerate(ids):
            dist = float(dists[i])
            sim = max(0.0, min(1.0, 1.0 - dist))
            hits.append(
                VectorHit(
                    rank=i + 1,
                    document_id=doc_id,
                    category=metas[i].get("category", ""),
                    severity=metas[i].get("severity", ""),
                    title=metas[i].get("title", ""),
                    similarity=round(sim, 4),
                    distance=round(dist, 4),
                    text=str(docs[i]),
                )
            )
        return hits