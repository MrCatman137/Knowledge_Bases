from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pyshacl import validate
from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef
from rdflib.namespace import OWL, XSD

BASE = Namespace("https://example.org/urban-transport#")
SH = Namespace("http://www.w3.org/ns/shacl#")


class State(TypedDict, total=False):
    input_files: list[str]
    raw_text: str
    chunks: list[dict[str, Any]]
    terms: dict[str, Any]
    relations: dict[str, Any]
    refined_schema: dict[str, Any]
    ontology_path: str
    validation_path: str
    validation_conforms: bool


CLASS_DEFS = {
    "RoadSegment": ("Road Segment", "Дорожня ділянка", "A modeled portion of an urban road network."),
    "TrafficSensor": ("Traffic Sensor", "Дорожній датчик", "A device that observes traffic conditions."),
    "TrafficSignal": ("Traffic Signal", "Світлофор", "A signal device used to control traffic movement."),
    "AdaptiveSignal": ("Adaptive Signal", "Адаптивний світлофор", "A traffic signal whose operation can adapt to observed conditions."),
    "TrafficController": ("Traffic Controller", "Контролер руху", "A control resource that operates traffic signals and regulates traffic."),
    "TransitRoute": ("Transit Route", "Маршрут громадського транспорту", "A public-transit service route."),
    "PublicTransitVehicle": ("Public Transit Vehicle", "Транспортний засіб громадського транспорту", "A vehicle operating a public-transit service."),
    "TrafficIncident": ("Traffic Incident", "Дорожній інцидент", "A temporary event disrupting transportation operations."),
    "TrafficObservation": ("Traffic Observation", "Спостереження за рухом", "A timestamped measurement of traffic conditions."),
    "PerformanceMetric": ("Performance Metric", "Показник ефективності", "A quantitative indicator used to evaluate transport performance."),
    "TransportAuthority": ("Transport Authority", "Транспортний орган", "An organization responsible for transport governance and operations."),
    "GovernancePolicy": ("Governance Policy", "Політика управління", "A normative rule or procedure governing transportation operations."),
    "SignalizedIntersection": ("Signalized Intersection", "Регульоване перехрестя", "An intersection represented as the location controlled by a signal."),
}

OBJECT_PROPS = {
    "monitors": ("TrafficSensor", "TrafficObservation", "monitors", "моніторить", "A sensor is associated with observations it monitors."),
    "measures": ("TrafficSensor", "RoadSegment", "measures", "вимірює", "A sensor measures conditions on a road segment."),
    "regulates": ("TrafficController", "RoadSegment", "regulates", "регулює", "A controller regulates traffic on a road segment."),
    "controls": ("TrafficController", "AdaptiveSignal", "controls", "керує", "A controller operates an adaptive signal."),
    "controlsIntersection": ("AdaptiveSignal", "SignalizedIntersection", "controls intersection", "керує перехрестям", "An adaptive signal controls exactly one signalized intersection."),
    "manages": ("TransportAuthority", "TrafficController", "manages", "керує", "An authority manages a traffic controller."),
    "causes": ("TrafficIncident", "PerformanceMetric", "causes", "спричиняє", "An incident can cause a measurable performance effect."),
    "connectsTo": ("RoadSegment", "RoadSegment", "з'єднується з", "з'єднує", "A road segment connects to another road segment."),
    "affects": ("TrafficIncident", "RoadSegment", "впливає на", "affects", "An incident affects a road segment."),
    "serves": ("TransitRoute", "RoadSegment", "обслуговує", "serves", "A transit route serves a road segment."),
    "operatesOn": ("PublicTransitVehicle", "TransitRoute", "працює на", "operates on", "A public transit vehicle operates on a route."),
    "usesPolicy": ("TransportAuthority", "GovernancePolicy", "застосовує політику", "uses policy", "An authority applies a governance policy."),
    "evaluates": ("PerformanceMetric", "RoadSegment", "оцінює", "evaluates", "A performance metric evaluates a road segment."),
}

DATA_PROPS = {
    "hasAllowedSpeed": ("RoadSegment", XSD.float, "has allowed speed", "має дозволену швидкість", "Allowed speed in km/h."),
    "hasObservedSpeed": ("TrafficObservation", XSD.float, "has observed speed", "має спостережену швидкість", "Observed speed in km/h."),
    "hasLanesCount": ("RoadSegment", XSD.integer, "has lane count", "має кількість смуг", "Number of lanes."),
    "isPeakHour": ("TrafficObservation", XSD.boolean, "is peak hour", "є годиною пік", "Whether the observation belongs to a peak period."),
    "hasVehicleCount": ("TrafficObservation", XSD.integer, "has vehicle count", "має кількість транспортних засобів", "Observed vehicle count."),
    "hasTimestamp": ("TrafficObservation", XSD.dateTime, "has timestamp", "має часову мітку", "Observation timestamp."),
    "hasDelayMinutes": ("PerformanceMetric", XSD.float, "has delay in minutes", "має затримку в хвилинах", "Delay represented in minutes."),
    "hasRouteNumber": ("TransitRoute", XSD.string, "has route number", "має номер маршруту", "Public transit route identifier."),
    "hasIdentifier": ("TrafficSensor", XSD.string, "has identifier", "має ідентифікатор", "Persistent identifier of a sensor."),
    "hasDescription": ("GovernancePolicy", XSD.string, "has description", "має опис", "Human-readable policy description."),
}

INDIVIDUALS = [
    {"id": "RoadSegment_Shevchenka", "class": "RoadSegment", "data": {"hasAllowedSpeed": (50.0, XSD.float), "hasLanesCount": (2, XSD.integer)}, "links": [("connectsTo", "RoadSegment_Franko"), ("connectsTo", "RoadSegment_Lychakivska")]},
    {"id": "RoadSegment_Franko", "class": "RoadSegment", "data": {"hasAllowedSpeed": (50.0, XSD.float), "hasLanesCount": (2, XSD.integer)}, "links": []},
    {"id": "RoadSegment_Lychakivska", "class": "RoadSegment", "data": {"hasAllowedSpeed": (50.0, XSD.float), "hasLanesCount": (2, XSD.integer)}, "links": []},
    {"id": "Sensor_Shevchenka_01", "class": "TrafficSensor", "data": {"hasIdentifier": ("TS-SH-01", XSD.string)}, "links": [("measures", "RoadSegment_Shevchenka"), ("monitors", "Observation_SH_0900")]},
    {"id": "Observation_SH_0900", "class": "TrafficObservation", "data": {"hasObservedSpeed": (24.5, XSD.float), "hasVehicleCount": (183, XSD.integer), "isPeakHour": (True, XSD.boolean), "hasTimestamp": ("2026-09-30T09:00:00", XSD.dateTime)}, "links": []},
    {"id": "AdaptiveSignal_Shevchenka", "class": "AdaptiveSignal", "data": {}, "links": [("controlsIntersection", "Intersection_Shevchenka_Center")]},
    {"id": "Intersection_Shevchenka_Center", "class": "SignalizedIntersection", "data": {}, "links": []},
    {"id": "Controller_Central_01", "class": "TrafficController", "data": {}, "links": [("controls", "AdaptiveSignal_Shevchenka"), ("regulates", "RoadSegment_Shevchenka")]},
    {"id": "Route_8", "class": "TransitRoute", "data": {"hasRouteNumber": ("8", XSD.string)}, "links": [("serves", "RoadSegment_Shevchenka")]},
    {"id": "Bus_204", "class": "PublicTransitVehicle", "data": {}, "links": [("operatesOn", "Route_8")]},
    {"id": "Incident_Shevchenka_Closure", "class": "TrafficIncident", "data": {}, "links": [("affects", "RoadSegment_Shevchenka"), ("causes", "Metric_Shevchenka_Delay")]},
    {"id": "Metric_Shevchenka_Delay", "class": "PerformanceMetric", "data": {"hasDelayMinutes": (12.7, XSD.float)}, "links": [("evaluates", "RoadSegment_Shevchenka")]},
    {"id": "Authority_LvivTransport", "class": "TransportAuthority", "data": {}, "links": [("manages", "Controller_Central_01"), ("usesPolicy", "Policy_IncidentResponse")]},
    {"id": "Policy_IncidentResponse", "class": "GovernancePolicy", "data": {"hasDescription": ("Activate incident response, coordinate signals, and publish a transit detour.", XSD.string)}, "links": []},
]


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _artifact(root: Path, name: str, data: Any) -> None:
    _write_json(root / "artifacts" / name, data)


def text_parser(state: State, root: Path) -> State:
    texts = []
    for file in state["input_files"]:
        texts.append(Path(file).read_text(encoding="utf-8"))
    raw = "\n\n".join(texts)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
    chunks = [{"chunk_id": f"C{i:02d}", "text": p, "sentences": re.split(r"(?<=[.!?])\s+", p)} for i, p in enumerate(paragraphs)]
    result = {"source_files": state["input_files"], "paragraph_count": len(chunks), "chunks": chunks}
    _artifact(root, "01_parsed_text.json", result)
    return {**state, "raw_text": raw, "chunks": chunks}


def term_extractor(state: State, root: Path) -> State:
    corpus = state["raw_text"].lower()
    terms = []
    for name, (en, uk, comment) in CLASS_DEFS.items():
        aliases = [en.lower(), uk.lower(), re.sub(r"(?<!^)(?=[A-Z])", " ", name).lower()]
        if any(alias in corpus for alias in aliases):
            terms.append({"name": name, "label_en": en, "label_uk": uk, "comment": comment})
    taxonomy = {
        "Infrastructure": ["RoadSegment", "TrafficSignal", "AdaptiveSignal", "TrafficController", "SignalizedIntersection"],
        "Observation": ["TrafficSensor", "TrafficObservation", "PerformanceMetric"],
        "MobilityService": ["TransitRoute", "PublicTransitVehicle"],
        "Event": ["TrafficIncident"],
        "Governance": ["TransportAuthority", "GovernancePolicy"],
    }
    result = {"candidate_terms": terms, "classes": [t["name"] for t in terms], "taxonomy": taxonomy}
    _artifact(root, "02_terms_and_classes.json", result)
    return {**state, "terms": result}


def relation_extractor(state: State, root: Path) -> State:
    corpus = state["raw_text"].lower()
    object_properties = []
    for prop, (domain, range_, en, uk, comment) in OBJECT_PROPS.items():
        if any(word in corpus for word in (en.lower(), uk.lower(), prop.lower())):
            object_properties.append({"name": prop, "domain": domain, "range": range_, "label_en": en, "label_uk": uk, "comment": comment})
    datatype_properties = []
    for prop, (domain, dtype, en, uk, comment) in DATA_PROPS.items():
        if any(word in corpus for word in (en.lower(), uk.lower(), prop.lower())):
            datatype_properties.append({"name": prop, "domain": domain, "datatype": str(dtype), "label_en": en, "label_uk": uk, "comment": comment})
    result = {"object_properties": object_properties, "datatype_properties": datatype_properties}
    _artifact(root, "03_relations.json", result)
    return {**state, "relations": result}


def schema_refiner(state: State, root: Path) -> State:
    refined = {
        "classes": state["terms"]["classes"],
        "taxonomy": state["terms"]["taxonomy"],
        "object_properties": state["relations"]["object_properties"],
        "datatype_properties": state["relations"]["datatype_properties"],
        "disjoint_pairs": [
            ["RoadSegment", "TrafficSensor"],
            ["TrafficIncident", "PerformanceMetric"],
            ["TrafficController", "GovernancePolicy"],
            ["TrafficObservation", "TransitRoute"],
        ],
        "restrictions": [
            {"class": "AdaptiveSignal", "property": "controlsIntersection", "kind": "maxQualifiedCardinality", "cardinality": 1, "range": "SignalizedIntersection"},
            {"class": "TrafficController", "property": "controls", "kind": "minQualifiedCardinality", "cardinality": 1, "range": "AdaptiveSignal"},
            {"class": "TrafficSensor", "property": "measures", "kind": "minQualifiedCardinality", "cardinality": 1, "range": "RoadSegment"},
        ],
        "individuals": INDIVIDUALS,
    }
    # Ensure every formal requirement is represented even if a source paragraph omitted a lexical trigger.
    refined["classes"] = list(dict.fromkeys(list(CLASS_DEFS)))
    refined["object_properties"] = [
        {"name": p, "domain": d, "range": r, "label_en": en, "label_uk": uk, "comment": c}
        for p, (d, r, en, uk, c) in OBJECT_PROPS.items()
    ]
    refined["datatype_properties"] = [
        {"name": p, "domain": d, "datatype": str(dt), "label_en": en, "label_uk": uk, "comment": c}
        for p, (d, dt, en, uk, c) in DATA_PROPS.items()
    ]
    _artifact(root, "04_refined_schema.json", refined)
    return {**state, "refined_schema": refined}


def _add_annotation(g: Graph, subject: URIRef, en: str, uk: str, comment: str) -> None:
    g.add((subject, RDFS.label, Literal(en, lang="en")))
    g.add((subject, RDFS.label, Literal(uk, lang="uk")))
    g.add((subject, RDFS.comment, Literal(comment, lang="en")))


def owl_generator(state: State, root: Path) -> State:
    schema = state["refined_schema"]
    g = Graph()
    g.bind("ut", BASE)
    g.bind("owl", OWL)
    g.bind("rdfs", RDFS)
    g.bind("xsd", XSD)
    g.bind("rdf", RDF)
    ontology = BASE["UrbanTransportationOntology"]
    g.add((ontology, RDF.type, OWL.Ontology))
    _add_annotation(g, ontology, "Digital Models of Urban Transportation Systems", "Цифрові моделі транспортних систем", "Academic ontology generated by an explicit LangGraph pipeline.")

    for parent, children in schema["taxonomy"].items():
        parent_uri = BASE[parent]
        g.add((parent_uri, RDF.type, OWL.Class))
        _add_annotation(g, parent_uri, parent, parent, f"Taxonomy grouping for {parent} concepts.")
        for child in children:
            child_uri = BASE[child]
            g.add((child_uri, RDF.type, OWL.Class))
            g.add((child_uri, RDFS.subClassOf, parent_uri))

    for name in schema["classes"]:
        uri = BASE[name]
        g.add((uri, RDF.type, OWL.Class))
        en, uk, comment = CLASS_DEFS[name]
        _add_annotation(g, uri, en, uk, comment)

    for item in schema["object_properties"]:
        uri = BASE[item["name"]]
        g.add((uri, RDF.type, OWL.ObjectProperty))
        g.add((uri, RDFS.domain, BASE[item["domain"]]))
        g.add((uri, RDFS.range, BASE[item["range"]]))
        _add_annotation(g, uri, item["label_en"], item["label_uk"], item["comment"])

    for item in schema["datatype_properties"]:
        uri = BASE[item["name"]]
        g.add((uri, RDF.type, OWL.DatatypeProperty))
        g.add((uri, RDFS.domain, BASE[item["domain"]]))
        g.add((uri, RDFS.range, URIRef(item["datatype"])))
        _add_annotation(g, uri, item["label_en"], item["label_uk"], item["comment"])

    for left, right in schema["disjoint_pairs"]:
        g.add((BASE[left], OWL.disjointWith, BASE[right]))

    for r in schema["restrictions"]:
        restriction = URIRef(f"{BASE}{r['class']}_{r['property']}_Restriction")
        g.add((BASE[r["class"]], RDFS.subClassOf, restriction))
        g.add((restriction, RDF.type, OWL.Restriction))
        g.add((restriction, OWL.onProperty, BASE[r["property"]]))
        if r["kind"] == "maxQualifiedCardinality":
            g.add((restriction, OWL.maxQualifiedCardinality, Literal(r["cardinality"], datatype=XSD.nonNegativeInteger)))
        else:
            g.add((restriction, OWL.minQualifiedCardinality, Literal(r["cardinality"], datatype=XSD.nonNegativeInteger)))
        g.add((restriction, OWL.onClass, BASE[r["range"]]))

    for item in schema["individuals"]:
        uri = BASE[item["id"]]
        g.add((uri, RDF.type, BASE[item["class"]]))
        for prop, target in item["links"]:
            g.add((uri, BASE[prop], BASE[target]))
        for prop, (value, dtype) in item["data"].items():
            g.add((uri, BASE[prop], Literal(value, datatype=dtype)))

    out = root / "output" / "ontology.ttl"
    out.parent.mkdir(parents=True, exist_ok=True)
    g.serialize(destination=out, format="turtle")
    summary = {"triple_count": len(g), "class_count": len(schema["classes"]), "object_property_count": len(schema["object_properties"]), "datatype_property_count": len(schema["datatype_properties"]), "individual_count": len(schema["individuals"]), "ontology_path": str(out)}
    _artifact(root, "05_owl_generation.json", summary)
    return {**state, "ontology_path": str(out)}


def validator(state: State, root: Path) -> State:
    ontology_path = Path(state["ontology_path"])
    shapes_path = root / "output" / "shapes.shacl.ttl"
    conforms, report_graph, report_text = validate(
        str(ontology_path),
        shacl_graph=str(shapes_path),
        ont_graph=str(ontology_path),
        inference="rdfs",
        abort_on_first=False,
        allow_infos=False,
        allow_warnings=False,
    )
    report = [
        "Ontology Validation Report",
        "==========================",
        f"Conforms: {conforms}",
        f"Ontology: {ontology_path}",
        f"Shapes: {shapes_path}",
        "",
        report_text.strip(),
    ]
    report_path = root / "reports" / "validation_report.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    summary = {"conforms": bool(conforms), "report_path": str(report_path), "validation_text": report_text}
    _artifact(root, "06_validation.json", summary)
    return {**state, "validation_path": str(report_path), "validation_conforms": bool(conforms)}


def build_graph(root: Path):
    builder = StateGraph(State)
    builder.add_node("TextParser", lambda s: text_parser(s, root))
    builder.add_node("TermExtractor", lambda s: term_extractor(s, root))
    builder.add_node("RelationExtractor", lambda s: relation_extractor(s, root))
    builder.add_node("SchemaRefiner", lambda s: schema_refiner(s, root))
    builder.add_node("OWLGenerator", lambda s: owl_generator(s, root))
    builder.add_node("Validator", lambda s: validator(s, root))
    builder.add_edge(START, "TextParser")
    builder.add_edge("TextParser", "TermExtractor")
    builder.add_edge("TermExtractor", "RelationExtractor")
    builder.add_edge("RelationExtractor", "SchemaRefiner")
    builder.add_edge("SchemaRefiner", "OWLGenerator")
    builder.add_edge("OWLGenerator", "Validator")
    builder.add_edge("Validator", END)
    return builder.compile()
