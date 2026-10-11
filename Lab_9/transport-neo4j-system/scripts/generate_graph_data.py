#!/usr/bin/env python3
"""Deterministic generator for the Neo4j Urban Digital Transport System dataset.

The generated CSV files are intentionally stable across runs. Seed: 42.
"""
from pathlib import Path
import csv, random

ROOT = Path(__file__).resolve().parents[1]
IMPORT = ROOT / "import"
IMPORT.mkdir(parents=True, exist_ok=True)
SEED = 42

def write_csv(name, headers, rows):
    path = IMPORT / name
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    return len(rows)

def main():
    random.seed(SEED)

    intersections = []
    for i in range(1, 21):
        intersections.append([
            f"I-{i:03d}", f"Intersection {i}", "Lviv",
            round(49.80 + (i % 5) * 0.003 + (i // 10) * 0.001, 6),
            round(24.00 + (i % 4) * 0.004 + (i // 5) * 0.001, 6),
            "signalized" if i % 3 else "priority"
        ])

    segment_pairs = []
    for i in range(1, 21):
        segment_pairs.append((i, i + 1 if i < 20 else 1))
    for i in range(1, 16):
        segment_pairs.append((i, i + 5))
    for i in range(1, 11):
        segment_pairs.append((i, i + 10))
    for i in range(1, 6):
        segment_pairs.append((i, i + 15))
    segment_pairs.extend([(1, 11), (2, 12), (3, 13), (4, 14), (5, 15)])

    segments = []
    for sid, (a, b) in enumerate(segment_pairs[:50], 1):
        length = 420 + ((a * 73 + b * 41) % 1250)
        lanes = 2 if (a + b) % 4 else 3
        speed = 40 + ((a + b) % 3) * 10
        flow = 500 + ((a * 113 + b * 67) % 1450)
        segments.append([
            f"SEG-{sid:03d}", f"Road Segment {sid}", f"I-{a:03d}", f"I-{b:03d}",
            length, lanes, speed, flow,
            round(min(0.95, 0.20 + flow / 3000), 3),
            "arterial" if lanes == 3 else "collector"
        ])

    stops = []
    for i in range(1, 26):
        stops.append([
            f"STOP-{i:03d}", f"Bus Stop {i}", f"Stop {i}", "Lviv",
            f"SEG-{((i * 2 - 1) % 50) + 1:03d}",
            100 + (i * 37) % 900, 1 if i % 4 else 2
        ])

    routes = []
    for r in range(1, 11):
        routes.append([f"R-{r:02d}", f"Route {r}", str(10+r), 18+r*3, 20+r, "active"])

    vehicles = []
    types = ["Bus", "Car", "Truck"]
    for i in range(1, 61):
        vtype = types[(i-1) % 3]
        vehicles.append([
            f"V-{i:03d}", f"Vehicle {i}", vtype, f"AA{i:04d}BB",
            f"SEG-{((i*7-1) % 50)+1:03d}", 35+(i % 6)*5,
            "active" if i % 17 else "maintenance"
        ])

    accidents = []
    severity = ["minor", "moderate", "major"]
    for i in range(1, 16):
        accidents.append([
            f"A-{i:03d}", f"Traffic Accident {i}",
            f"2026-09-{(i % 20)+1:02d}T{8+(i % 10):02d}:{(i*7)%60:02d}:00",
            severity[(i-1)%3], 1+(i%4), 1000+i*250,
            f"SEG-{((i*3-1)%50)+1:03d}"
        ])

    decisions = []
    for i in range(1, 11):
        decisions.append([
            f"D-{i:03d}", f"Transport Decision {i}",
            ["reroute","signal_timing","dispatch","road_restriction"][i % 4],
            f"2026-09-{(i % 20)+1:02d}T{10+(i%8):02d}:00:00",
            0.70+(i%5)*0.05, "approved" if i%4 else "pending"
        ])

    sensors = []
    for i in range(1, 21):
        sensors.append([
            f"S-{i:03d}", f"Traffic Sensor {i}",
            ["loop","camera","radar","gps"][i % 4],
            f"2026-09-28T{8+i%10:02d}:{(i*3)%60:02d}:00",
            f"SEG-{((i*5-1)%50)+1:03d}", 0.92+(i%7)/100
        ])

    network = []
    for i in range(1, 51):
        a1, b1 = segment_pairs[i-1]
        for j in range(i+1, 51):
            a2, b2 = segment_pairs[j-1]
            if {a1, b1} & {a2, b2}:
                network.append([
                    f"SEG-{i:03d}", f"SEG-{j:03d}",
                    round(0.8+(((i*11+j*7)%90)/100), 2)
                ])
    network.sort(key=lambda r: (r[0], r[1]))

    has_stop = [[s[0], s[4], 0.5+(int(s[0][-3:])%8)*0.1] for s in stops]
    route_stops = [[f"R-{r:02d}", f"STOP-{((r*2+k*3)%25)+1:03d}", k+1]
                   for r in range(1,11) for k in range(10)]
    route_segments = [[f"R-{r:02d}", f"SEG-{((r*3+k*4)%50)+1:03d}", k+1]
                      for r in range(1,11) for k in range(10)]
    located_on = [[v[0], v[4], 20+(int(v[0][-3:])%60)] for v in vehicles]
    assigned_route = [[v[0], f"R-{((int(v[0][-3:])-1)%10)+1:02d}"]
                      for v in vehicles if v[2] == "Bus"]
    accidents_segment = [[a[0], a[6]] for a in accidents]
    decisions_accident = [[d[0], f"A-{((int(d[0][-3:])-1)%15)+1:03d}"] for d in decisions]
    decisions_route = [[d[0], f"R-{((int(d[0][-3:])-1)%10)+1:02d}"] for d in decisions]
    sensor_monitors = [[s[0], s[4], 0.85+(int(s[0][-3:])%10)/100] for s in sensors]

    counts = {}
    counts["nodes_intersections.csv"] = write_csv("nodes_intersections.csv",
        ["intersection_id","name","city","latitude","longitude","control_type"], intersections)
    counts["nodes_segments.csv"] = write_csv("nodes_segments.csv",
        ["segment_id","name","from_intersection_id","to_intersection_id","length_m","lanes",
         "speed_limit_kmh","hourly_flow","congestion_index","road_class"], segments)
    counts["nodes_bus_stops.csv"] = write_csv("nodes_bus_stops.csv",
        ["stop_id","name","stop_code","city","segment_id","daily_boardings","shelters"], stops)
    counts["nodes_routes.csv"] = write_csv("nodes_routes.csv",
        ["route_id","name","route_number","frequency_min","length_km","status"], routes)
    counts["nodes_vehicles.csv"] = write_csv("nodes_vehicles.csv",
        ["vehicle_id","name","vehicle_type","license_plate","segment_id","speed_kmh","status"], vehicles)
    counts["nodes_accidents.csv"] = write_csv("nodes_accidents.csv",
        ["accident_id","name","occurred_at","severity","injured_count","estimated_cost_uah","segment_id"], accidents)
    counts["nodes_decisions.csv"] = write_csv("nodes_decisions.csv",
        ["decision_id","name","decision_type","decided_at","confidence","status"], decisions)
    counts["nodes_sensors.csv"] = write_csv("nodes_sensors.csv",
        ["sensor_id","name","sensor_type","observed_at","segment_id","reliability"], sensors)
    counts["edges_network.csv"] = write_csv("edges_network.csv",
        ["from_segment_id","to_segment_id","travel_time_min"], network)
    counts["edges_has_stop.csv"] = write_csv("edges_has_stop.csv",
        ["stop_id","segment_id","offset_m"], has_stop)
    counts["edges_route_stops.csv"] = write_csv("edges_route_stops.csv",
        ["route_id","stop_id","sequence"], route_stops)
    counts["edges_route_segments.csv"] = write_csv("edges_route_segments.csv",
        ["route_id","segment_id","sequence"], route_segments)
    counts["edges_located_on.csv"] = write_csv("edges_located_on.csv",
        ["vehicle_id","segment_id","speed_kmh"], located_on)
    counts["edges_assigned_route.csv"] = write_csv("edges_assigned_route.csv",
        ["vehicle_id","route_id"], assigned_route)
    counts["edges_accidents_segment.csv"] = write_csv("edges_accidents_segment.csv",
        ["accident_id","segment_id"], accidents_segment)
    counts["edges_decisions_accident.csv"] = write_csv("edges_decisions_accident.csv",
        ["decision_id","accident_id"], decisions_accident)
    counts["edges_decisions_route.csv"] = write_csv("edges_decisions_route.csv",
        ["decision_id","route_id"], decisions_route)
    counts["edges_sensor_monitors.csv"] = write_csv("edges_sensor_monitors.csv",
        ["sensor_id","segment_id","coverage"], sensor_monitors)

    node_count = sum(counts[k] for k in counts if k.startswith("nodes_"))
    relationship_count = sum(counts[k] for k in counts if k.startswith("edges_"))
    assert node_count >= 150
    assert relationship_count >= 300
    print(f"Generated {node_count} nodes and {relationship_count} relationship rows.")
    print("Seed:", SEED)
    for name, count in counts.items():
        print(f"{name}: {count}")

if __name__ == "__main__":
    main()
