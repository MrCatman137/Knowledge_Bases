"""Create a richer transport ontology without modifying the source OWL file."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD


logging.getLogger("rdflib").setLevel(logging.CRITICAL)

ONTOLOGY_URI = "http://example.org/transport-ontology#"
ONT = Namespace(ONTOLOGY_URI)


def add_class(
    graph: Graph, name: str, label: str, parent: URIRef, comment: str
) -> URIRef:
    resource = ONT[name]
    graph.add((resource, RDF.type, OWL.Class))
    graph.add((resource, RDFS.label, Literal(label, lang="uk")))
    graph.add((resource, RDFS.subClassOf, parent))
    graph.add((resource, RDFS.comment, Literal(comment, lang="uk")))
    return resource


def add_property(
    graph: Graph,
    name: str,
    label: str,
    domain: URIRef,
    range_: URIRef,
    property_type: URIRef,
) -> URIRef:
    resource = ONT[name]
    graph.add((resource, RDF.type, property_type))
    graph.add((resource, RDFS.label, Literal(label, lang="uk")))
    graph.add((resource, RDFS.domain, domain))
    graph.add((resource, RDFS.range, range_))
    return resource


def add_cardinality_restriction(
    graph: Graph,
    class_resource: URIRef,
    property_resource: URIRef,
    cardinality_type: URIRef,
    cardinality: int,
    qualified_class: URIRef | None = None,
) -> None:
    restriction = BNode()
    graph.add((class_resource, RDFS.subClassOf, restriction))
    graph.add((restriction, RDF.type, OWL.Restriction))
    graph.add((restriction, OWL.onProperty, property_resource))
    graph.add(
        (
            restriction,
            cardinality_type,
            Literal(cardinality, datatype=XSD.nonNegativeInteger),
        )
    )
    if qualified_class is not None:
        graph.add((restriction, OWL.onClass, qualified_class))


def add_some_values_restriction(
    graph: Graph,
    class_resource: URIRef,
    property_resource: URIRef,
    target_class: URIRef,
) -> None:
    restriction = BNode()
    graph.add((class_resource, RDFS.subClassOf, restriction))
    graph.add((restriction, RDF.type, OWL.Restriction))
    graph.add((restriction, OWL.onProperty, property_resource))
    graph.add((restriction, OWL.someValuesFrom, target_class))


def add_individual(
    graph: Graph,
    name: str,
    class_name: str,
    label: str,
    identifier: str | None = None,
    description: str | None = None,
) -> URIRef:
    resource = ONT[name]
    graph.add((resource, RDF.type, OWL.NamedIndividual))
    graph.add((resource, RDF.type, ONT[class_name]))
    graph.add((resource, RDFS.label, Literal(label, lang="uk")))
    if identifier is not None:
        graph.add((resource, ONT.identifier, Literal(identifier)))
    if description is not None:
        graph.add((resource, ONT.description, Literal(description, lang="uk")))
    return resource


def expand_ontology(input_path: Path, output_path: Path) -> tuple[int, int, int]:
    graph = Graph()
    graph.parse(input_path, format="xml")
    graph.bind("", ONT)
    graph.bind("owl", OWL)
    graph.bind("rdfs", RDFS)
    graph.bind("xsd", XSD)

    # Add specialist classes under the existing transport model hierarchy.
    for name, label, parent, comment in [
        (
            "ElectricBus",
            "Електробус",
            ONT.Bus,
            "Автобус з електричним приводом і тяговою батареєю.",
        ),
        (
            "Tram",
            "Трамвай",
            ONT.Vehicle,
            "Міський рейковий транспортний засіб.",
        ),
        (
            "TransitOperator",
            "Транспортний оператор",
            ONT.TransportObject,
            "Організація, що забезпечує перевезення пасажирів.",
        ),
        (
            "TransitSchedule",
            "Розклад руху",
            ONT.TransportSystemData,
            "Планові часи та інтервали руху за маршрутом.",
        ),
        (
            "ChargingStation",
            "Зарядна станція",
            ONT.TransportInfrastructure,
            "Об'єкт інфраструктури для заряджання електротранспорту.",
        ),
        (
            "WeatherObservation",
            "Спостереження за погодою",
            ONT.TransportSystemData,
            "Зафіксовані погодні умови, що можуть впливати на рух.",
        ),
        (
            "EmergencyService",
            "Екстрена служба",
            ONT.TransportObject,
            "Служба, що реагує на дорожні події та надзвичайні ситуації.",
        ),
        (
            "TrafficCamera",
            "Дорожня камера",
            ONT.TrafficSensor,
            "Камера для моніторингу дорожньої обстановки.",
        ),
    ]:
        add_class(graph, name, label, parent, comment)

    # Define relationships and attributes used by the additional instances.
    for name, label, domain, range_ in [
        ("connectsTo", "сполучається з", ONT.RoadSegment, ONT.RoadSegment),
        ("servesStop", "обслуговує зупинку", ONT.Route, ONT.BusStop),
        ("operatedBy", "обслуговується оператором", ONT.Vehicle, ONT.TransitOperator),
        ("hasSchedule", "має розклад", ONT.Route, ONT.TransitSchedule),
        ("monitors", "моніторить", ONT.TrafficSensor, ONT.RoadSegment),
        ("hasChargingStation", "має зарядну станцію", ONT.RoadNetwork, ONT.ChargingStation),
        ("affectedByWeather", "залежить від погодних умов", ONT.RoadSegment, ONT.WeatherObservation),
        ("respondedBy", "обслуговується службою", ONT.TrafficAccident, ONT.EmergencyService),
    ]:
        add_property(graph, name, label, domain, range_, OWL.ObjectProperty)

    for name, label, domain, range_ in [
        ("operationalStatus", "технічний стан", ONT.Vehicle, XSD.string),
        ("passengerCapacity", "пасажиромісткість", ONT.Vehicle, XSD.integer),
        ("serviceFrequency", "інтервал руху у хвилинах", ONT.TransitSchedule, XSD.integer),
        ("batteryCapacityKWh", "ємність батареї у кВт·год", ONT.ElectricBus, XSD.double),
        ("airTemperatureC", "температура повітря у °C", ONT.WeatherObservation, XSD.double),
    ]:
        add_property(graph, name, label, domain, range_, OWL.DatatypeProperty)

    # OWL property characteristics support inverse and symmetric navigation.
    graph.add((ONT.connectsTo, RDF.type, OWL.SymmetricProperty))
    add_property(
        graph,
        "operatesVehicle",
        "експлуатує транспортний засіб",
        ONT.TransitOperator,
        ONT.Vehicle,
        OWL.ObjectProperty,
    )
    graph.add((ONT.operatedBy, OWL.inverseOf, ONT.operatesVehicle))
    add_property(
        graph,
        "scheduledForRoute",
        "є розкладом маршруту",
        ONT.TransitSchedule,
        ONT.Route,
        OWL.ObjectProperty,
    )
    graph.add((ONT.hasSchedule, OWL.inverseOf, ONT.scheduledForRoute))

    # OWL class restrictions describe required relationships and attributes.
    add_cardinality_restriction(
        graph, ONT.ElectricBus, ONT.batteryCapacityKWh, OWL.minCardinality, 1
    )
    add_cardinality_restriction(
        graph, ONT.ElectricBus, ONT.hasRoute, OWL.minQualifiedCardinality, 1, ONT.Route
    )
    add_cardinality_restriction(
        graph, ONT.TransitSchedule, ONT.serviceFrequency, OWL.minCardinality, 1
    )
    add_cardinality_restriction(
        graph, ONT.Route, ONT.hasSchedule, OWL.minQualifiedCardinality, 1, ONT.TransitSchedule
    )
    add_cardinality_restriction(
        graph,
        ONT.RoadNetwork,
        ONT.hasRoadSegment,
        OWL.minQualifiedCardinality,
        1,
        ONT.RoadSegment,
    )
    add_cardinality_restriction(
        graph, ONT.ChargingStation, ONT.identifier, OWL.minCardinality, 1
    )
    add_some_values_restriction(
        graph, ONT.TrafficCamera, ONT.monitors, ONT.RoadSegment
    )
    graph.add((ONT.Bus, OWL.disjointWith, ONT.Tram))

    # Extend the road network with segments matching the relational layer.
    segments = [
        ("DS002", "DS-002", "вул. Зелена, сегмент 2", 2, 50.0, 720.0),
        ("DS003", "DS-003", "вул. Городоцька, сегмент 3", 3, 50.0, 1100.0),
        ("DS004", "DS-004", "вул. Стрийська, сегмент 4", 3, 60.0, 1250.0),
        ("DS005", "DS-005", "просп. Чорновола, сегмент 5", 2, 50.0, 680.0),
    ]
    segment_resources: list[URIRef] = [ONT.DS001]
    for local_id, identifier, label, lanes, speed_limit, length in segments:
        segment = add_individual(
            graph,
            local_id,
            "RoadSegment",
            label,
            identifier,
            "Доданий сегмент міської дорожньої мережі.",
        )
        graph.add((segment, ONT.laneCount, Literal(lanes, datatype=XSD.integer)))
        graph.add((segment, ONT.allowedSpeed, Literal(speed_limit, datatype=XSD.double)))
        graph.add((segment, ONT.length, Literal(length, datatype=XSD.double)))
        graph.add((segment, ONT.currentSpeed, Literal(speed_limit - 12, datatype=XSD.double)))
        graph.add((ONT.RoadNetwork001, ONT.hasRoadSegment, segment))
        segment_resources.append(segment)

    for first, second in zip(segment_resources, segment_resources[1:]):
        graph.add((first, ONT.connectsTo, second))
        graph.add((second, ONT.connectsTo, first))

    # Add operators, service routes, schedules, stops, and vehicles.
    operators = [
        add_individual(
            graph, "OperatorCityBus", "TransitOperator", "Міське автобусне підприємство",
            "OP-001", "Оператор автобусних маршрутів міста.",
        ),
        add_individual(
            graph, "OperatorElectricTransit", "TransitOperator", "Міський електротранспорт",
            "OP-002", "Оператор електричного громадського транспорту.",
        ),
    ]
    schedule_data = [
        ("Schedule24", "Розклад маршруту №24", "SCH-024", 12),
        ("Schedule35", "Розклад маршруту №35", "SCH-035", 15),
        ("Schedule5", "Розклад маршруту №5", "SCH-005", 10),
    ]
    routes = [ONT.Route24, ONT.Route35, ONT.Route5]
    for index, (schedule_name, schedule_label, schedule_id, frequency) in enumerate(schedule_data, 1):
        schedule = add_individual(
            graph, schedule_name, "TransitSchedule", schedule_label, schedule_id,
            f"Плановий інтервал руху становить {frequency} хвилин.",
        )
        graph.add((schedule, ONT.serviceFrequency, Literal(frequency, datatype=XSD.integer)))
        route = routes[index - 1]
        graph.add((route, ONT.hasSchedule, schedule))
        graph.add((schedule, ONT.scheduledForRoute, route))
        stop = add_individual(
            graph, f"ExpandedBusStop{index:03}", "BusStop",
            f"Зупинка маршруту {index}", f"STOP-X{index:03}",
        )
        graph.add((route, ONT.servesStop, stop))
        graph.add((ONT.RoadNetwork001, ONT.hasBusStop, stop))

    buses = [
        ("Bus24B", "Електробус маршруту №24", "BUS-24B", "ElectricBus", operators[1], routes[0], segment_resources[1], 280.0, 82),
        ("Bus35B", "Автобус маршруту №35", "BUS-35B", "Bus", operators[0], routes[1], segment_resources[2], None, 70),
        ("Bus5B", "Електробус маршруту №5", "BUS-5B", "ElectricBus", operators[1], routes[2], segment_resources[4], 320.0, 86),
    ]
    for name, label, identifier, class_name, operator, route, segment, battery, capacity in buses:
        bus = add_individual(graph, name, class_name, label, identifier)
        graph.add((bus, ONT.hasRoute, route))
        graph.add((bus, ONT.operatedBy, operator))
        graph.add((operator, ONT.operatesVehicle, bus))
        graph.add((bus, ONT.locatedOn, segment))
        graph.add((bus, ONT.operationalStatus, Literal("у русі")))
        graph.add((bus, ONT.passengerCapacity, Literal(capacity, datatype=XSD.integer)))
        if battery is not None:
            graph.add((bus, ONT.batteryCapacityKWh, Literal(battery, datatype=XSD.double)))

    tram = add_individual(
        graph, "Tram1", "Tram", "Трамвай №1", "TRAM-001",
        "Низькопідлоговий трамвай міського маршруту.",
    )
    graph.add((tram, ONT.operatedBy, operators[1]))
    graph.add((tram, ONT.operationalStatus, Literal("у русі")))
    graph.add((tram, ONT.passengerCapacity, Literal(160, datatype=XSD.integer)))

    charging_station = add_individual(
        graph, "ChargingStation001", "ChargingStation", "Зарядна станція депо №1",
        "CHG-001", "Швидкісна зарядна станція автобусного депо.",
    )
    graph.add((ONT.RoadNetwork001, ONT.hasChargingStation, charging_station))

    # Add sensing, traffic conditions, and emergency-response context.
    camera = add_individual(
        graph, "TrafficCamera002", "TrafficCamera", "Камера спостереження №2", "CAM-002",
    )
    graph.add((camera, ONT.monitors, segment_resources[2]))
    weather = add_individual(
        graph, "WeatherObservation001", "WeatherObservation", "Дощ у центральному районі",
        "WX-001", "Помірний дощ, видимість знижена.",
    )
    graph.add((weather, ONT.airTemperatureC, Literal(12.5, datatype=XSD.double)))
    graph.add((weather, ONT.measurementTime, Literal("2026-10-08T08:30:00", datatype=XSD.dateTime)))
    graph.add((segment_resources[2], ONT.affectedByWeather, weather))

    service = add_individual(
        graph, "EmergencyService001", "EmergencyService", "Міська служба екстреного реагування",
        "EMS-001", "Координує реагування на транспортні інциденти.",
    )
    accident = add_individual(
        graph, "Accident002", "TrafficAccident", "ДТП на вул. Городоцькій",
        "ACC-002", "Зіткнення транспортних засобів частково обмежило рух.",
    )
    graph.add((accident, ONT.affects, ONT.TrafficFlow001))
    graph.add((accident, ONT.respondedBy, service))

    graph.serialize(destination=output_path, format="xml", encoding="utf-8")
    classes = set(graph.subjects(RDF.type, OWL.Class))
    individuals = set(graph.subjects(RDF.type, OWL.NamedIndividual))
    return len(graph), len(classes), len(individuals)


def main() -> None:
    lab_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=lab_dir / "update.owl",
        help="source OWL file (default: update.owl)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=lab_dir / "update_expanded.owl",
        help="generated OWL file (default: update_expanded.owl)",
    )
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f"input ontology does not exist: {args.input}")

    triples, classes, individuals = expand_ontology(args.input, args.output)
    print(
        f"Created {args.output}: {triples} triples, "
        f"{classes} classes, {individuals} named individuals."
    )


if __name__ == "__main__":
    main()
