#!/usr/bin/env python3
"""
Скрипт для ін'єкції контрольованих дефектів (дублікатів та логічних протиріч)
в онтологію цифрової моделі транспортної системи для виконання ЛР №12.
"""
from pathlib import Path
from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, OWL, XSD
# Визначаємо папку, в якій лежить цей скрипт (Lab_12)
SCRIPT_DIR = Path(__file__).resolve().parent

INPUT_ONTOLOGY = SCRIPT_DIR / "update.owl"
OUTPUT_DIRTY_OWL = SCRIPT_DIR / "update_dirty.owl"
OUTPUT_DIRTY_TTL = SCRIPT_DIR / "update_dirty.ttl"

def inject_flaws():
    g = Graph()
    print(f"[*] Завантаження онтології з {INPUT_ONTOLOGY}...")
    g.parse(INPUT_ONTOLOGY, format="xml")
    initial_count = len(g)
    print(f"[+] Успішно завантажено. Початкова кількість триплетів: {initial_count}")

    # Простори назв
    TO = Namespace("http://example.org/transport-ontology#")
    g.bind("transport-ontology", TO)
    g.bind("owl", OWL)
    g.bind("rdfs", RDFS)
    g.bind("xsd", XSD)

    print("\n--- [1] Ін'єкція дублікатів (Entity Resolution Candidates) ---")

    # ДУБЛІКАТ 1: Дублікат міського автобуса з зовнішньої системи
    # (Той самий номер маршруту 24 і подібна назва, але інший URI)
    bus_dup = TO["Bus24_FleetExternal"]
    g.add((bus_dup, RDF.type, TO.Bus))
    g.add((bus_dup, RDFS.label, Literal("Автобус №24 (зовнішній оператор)", lang="uk")))
    g.add((bus_dup, TO.routeNumber, Literal("24", datatype=XSD.string)))
    g.add((bus_dup, TO.identifier, Literal("BUS-24-EXT", datatype=XSD.string)))
    g.add((bus_dup, TO.locatedOn, TO.DS001))
    g.add((bus_dup, TO.hasRoute, TO.Route24))
    print(" + Додано дублікат автобуса: :Bus24_FleetExternal (збіг за routeNumber='24')")

    # ДУБЛІКАТ 2: Дублікат зупинки з синонімічною назвою та ідентичним кодом
    stop_dup = TO["BusStop_ArtSchool_Alt"]
    g.add((stop_dup, RDF.type, TO.BusStop))
    g.add((stop_dup, RDFS.label, Literal("Зупинка Художня школа ім. О. Новаківського", lang="uk")))
    g.add((stop_dup, TO.identifier, Literal("BS-001", datatype=XSD.string))) # однаковий бізнес-код BS-001
    print(" + Додано дублікат зупинки: :BusStop_ArtSchool_Alt (збіг за кодом identifier='BS-001')")

    # ДУБЛІКАТ 3: Телеметричний дублікат сенсора GPS (ідентичні координати і час)
    gps_dup = TO["GPS003_Clone"]
    g.add((gps_dup, RDF.type, TO.GPSMeasurement))
    g.add((gps_dup, RDFS.label, Literal("GPS-вимірювання №3 (дублікат)", lang="uk")))
    g.add((gps_dup, TO.measurementTime, Literal("2026-09-19T10:00:00", datatype=XSD.dateTime)))
    g.add((gps_dup, TO.longitude, Literal(24.0297, datatype=XSD.double)))
    g.add((gps_dup, TO.latitude, Literal(49.8397, datatype=XSD.double)))
    g.add((gps_dup, TO.collectsData, TO.SpeedData003))
    print(" + Додано дублікат GPS-вимірювання: :GPS003_Clone (ідентичні час, широта, довгота)")


    print("\n--- [2] Ін'єкція логічних протиріч (Inconsistencies & Violations) ---")

    # ПРОТИРІЧЧЯ 1: Порушення disjointness (AllDisjointClasses: Bus, Car, Truck)
    # Сутність має одночасно несумісні класи -> HermiT / Pellet одразу зареєструють Inconsistency!
    conflict_vehicle = TO["ConflictVehicle001"]
    g.add((conflict_vehicle, RDF.type, TO.Bus))
    g.add((conflict_vehicle, RDF.type, TO.Car))  # КРИТИЧНА ПОМИЛКА ДИЗ'ЮНКЦІЇ
    g.add((conflict_vehicle, RDFS.label, Literal("Гібридний ТЗ (Конфліктний екземпляр)", lang="uk")))
    g.add((conflict_vehicle, TO.identifier, Literal("CONF-VEH-01", datatype=XSD.string)))
    g.add((conflict_vehicle, TO.hasRoute, TO.Route5))
    print(" ! Додано конфлікт диз'юнкції: :ConflictVehicle001 (типи :Bus + :Car одночасно)")

    # ПРОТИРІЧЧЯ 2: Порушення функціональності (Multi-valued Functional Property)
    # Сегмент дороги отримує другу відмінну довжину (length) та дозволену швидкість
    g.add((TO.DS001, TO.length, Literal(1250.0, datatype=XSD.double))) # у первинній онтології 850.0
    g.add((TO.DS001, TO.allowedSpeed, Literal(80.0, datatype=XSD.double))) # у первинній онтології 50.0
    print(" ! Додано порушення функціональності: :DS001 отримав другу довжину 1250.0 та швидкість 80.0")

    # ПРОТИРІЧЧЯ 3: Порушення мінімальної кардинальності (minQualifiedCardinality 1 hasRoute)
    # Автобус без обов'язкового маршруту
    ghost_bus = TO["GhostBus_NoRoute"]
    g.add((ghost_bus, RDF.type, TO.Bus))
    g.add((ghost_bus, RDFS.label, Literal("Автобус-привид без маршруту", lang="uk")))
    g.add((ghost_bus, TO.identifier, Literal("BUS-GHOST", datatype=XSD.string)))
    # НЕ додаємо :hasRoute!
    print(" ! Додано порушення кардинальності: :GhostBus_NoRoute (тип :Bus без обов'язкового :hasRoute)")

    # ПРОТИРІЧЧЯ 4: Неприпустиме значення (Invalid Range / Semantic Outlier)
    # Від'ємна швидкість та некоректна кількість смуг (0)
    broken_car = TO["BrokenCar001"]
    g.add((broken_car, RDF.type, TO.Car))
    g.add((broken_car, RDFS.label, Literal("Автомобіль з помилковими даними", lang="uk")))
    g.add((broken_car, TO.currentSpeed, Literal(-45.0, datatype=XSD.double))) # Швидкість < 0
    print(" ! Додано некоректні дані: :BrokenCar001 (currentSpeed = -45.0)")

    # Збереження результатів
    final_count = len(g)
    print(f"\n[+] Додано нових триплетів: {final_count - initial_count}. Загалом: {final_count}")

    g.serialize(destination=OUTPUT_DIRTY_OWL, format="xml")
    print(f"[✓] Збережено RDF/XML для Protégé: {OUTPUT_DIRTY_OWL}")

    g.serialize(destination=OUTPUT_DIRTY_TTL, format="turtle")
    print(f"[✓] Збережено Turtle для GraphDB: {OUTPUT_DIRTY_TTL}")

if __name__ == "__main__":
    inject_flaws()