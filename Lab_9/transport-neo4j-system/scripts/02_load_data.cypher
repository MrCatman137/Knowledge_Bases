// 02_load_data.cypher
// Pure Cypher LOAD CSV. No APOC/n10s dependency.
// All MERGE keys are backed by uniqueness constraints.
//
// Run after 01_schema_constraints.cypher.
//
// Node labels are the LPG mapping of ontology classes:
// Intersection, RoadSegment, BusStop, Route, Vehicle, TrafficAccident,
// TransportDecision, TrafficSensor.
//
// Vehicle subtypes are represented by additional labels (Bus/Car/Truck).

LOAD CSV WITH HEADERS FROM 'file:///nodes_intersections.csv' AS row
MERGE (n:Intersection {id: row.intersection_id})
SET n.name = row.name,
    n.city = row.city,
    n.latitude = toFloat(row.latitude),
    n.longitude = toFloat(row.longitude),
    n.location = point({latitude: toFloat(row.latitude), longitude: toFloat(row.longitude)}),
    n.controlType = row.control_type;

LOAD CSV WITH HEADERS FROM 'file:///nodes_segments.csv' AS row
MERGE (n:RoadSegment {id: row.segment_id})
SET n.name = row.name,
    n.lengthM = toInteger(row.length_m),
    n.lanes = toInteger(row.lanes),
    n.speedLimitKmh = toInteger(row.speed_limit_kmh),
    n.hourlyFlow = toInteger(row.hourly_flow),
    n.congestionIndex = toFloat(row.congestion_index),
    n.roadClass = row.road_class,
    n.fromIntersectionId = row.from_intersection_id,
    n.toIntersectionId = row.to_intersection_id;

LOAD CSV WITH HEADERS FROM 'file:///nodes_bus_stops.csv' AS row
MERGE (n:BusStop {id: row.stop_id})
SET n.name = row.name,
    n.stopCode = row.stop_code,
    n.city = row.city,
    n.dailyBoardings = toInteger(row.daily_boardings),
    n.shelters = toInteger(row.shelters);

LOAD CSV WITH HEADERS FROM 'file:///nodes_routes.csv' AS row
MERGE (n:Route {id: row.route_id})
SET n.name = row.name,
    n.routeNumber = toInteger(row.route_number),
    n.frequencyMin = toInteger(row.frequency_min),
    n.lengthKm = toInteger(row.length_km),
    n.status = row.status;

LOAD CSV WITH HEADERS FROM 'nodes_vehicles.csv' AS row
MERGE (n:Vehicle {id: row.vehicle_id})
SET n.name = row.name,
    n.vehicleType = row.vehicle_type,
    n.licensePlate = row.license_plate,
    n.speedKmh = toInteger(row.speed_kmh),
    n.status = row.status
WITH n, row
CALL {
    WITH n, row
    WITH n, row WHERE row.vehicle_type = 'Bus'
    SET n:Bus
    RETURN count(*) AS busCount
}
CALL {
    WITH n, row
    WITH n, row WHERE row.vehicle_type = 'Car'
    SET n:Car
    RETURN count(*) AS carCount
}
CALL {
    WITH n, row
    WITH n, row WHERE row.vehicle_type = 'Truck'
    SET n:Truck
    RETURN count(*) AS truckCount
}
RETURN count(*) AS vehicles_loaded;

LOAD CSV WITH HEADERS FROM 'file:///nodes_accidents.csv' AS row
MERGE (n:TrafficAccident {id: row.accident_id})
SET n.name = row.name,
    n.occurredAt = datetime(row.occurred_at),
    n.severity = row.severity,
    n.injuredCount = toInteger(row.injured_count),
    n.estimatedCostUah = toInteger(row.estimated_cost_uah);

LOAD CSV WITH HEADERS FROM 'nodes_decisions.csv' AS row
MERGE (n:TransportDecision {id: row.decision_id})
SET n.name = row.name,
    n.decisionType = row.decision_type,
    n.decidedAt = datetime(row.decided_at),
    n.confidence = toFloat(row.confidence),
    n.status = row.status;

LOAD CSV WITH HEADERS FROM 'nodes_sensors.csv' AS row
MERGE (n:TrafficSensor {id: row.sensor_id})
SET n.name = row.name,
    n.sensorType = row.sensor_type,
    n.observedAt = datetime(row.observed_at),
    n.reliability = toFloat(row.reliability);

LOAD CSV WITH HEADERS FROM 'edges_network.csv' AS row
MATCH (a:RoadSegment {id: row.from_segment_id})
MATCH (b:RoadSegment {id: row.to_segment_id})
MERGE (a)-[r:NETWORK]->(b)
SET r.travelTimeMin = toFloat(row.travel_time_min);

LOAD CSV WITH HEADERS FROM 'edges_has_stop.csv' AS row
MATCH (s:BusStop {id: row.stop_id})
MATCH (seg:RoadSegment {id: row.segment_id})
MERGE (s)-[r:LOCATED_ON]->(seg)
SET r.offsetM = toFloat(row.offset_m);

LOAD CSV WITH HEADERS FROM 'edges_route_stops.csv' AS row
MATCH (r:Route {id: row.route_id})
MATCH (s:BusStop {id: row.stop_id})
MERGE (r)-[rel:SERVES_STOP]->(s)
SET rel.sequence = toInteger(row.sequence);

LOAD CSV WITH HEADERS FROM 'edges_route_segments.csv' AS row
MATCH (r:Route {id: row.route_id})
MATCH (s:RoadSegment {id: row.segment_id})
MERGE (r)-[rel:COVERS_SEGMENT]->(s)
SET rel.sequence = toInteger(row.sequence);

LOAD CSV WITH HEADERS FROM 'edges_located_on.csv' AS row
MATCH (v:Vehicle {id: row.vehicle_id})
MATCH (s:RoadSegment {id: row.segment_id})
MERGE (v)-[r:LOCATED_ON]->(s)
SET r.speedKmh = toInteger(row.speed_kmh);

LOAD CSV WITH HEADERS FROM 'edges_assigned_route.csv' AS row
MATCH (v:Vehicle {id: row.vehicle_id})
MATCH (r:Route {id: row.route_id})
MERGE (v)-[:ASSIGNED_TO]->(r);

LOAD CSV WITH HEADERS FROM 'edges_accidents_segment.csv' AS row
MATCH (a:TrafficAccident {id: row.accident_id})
MATCH (s:RoadSegment {id: row.segment_id})
MERGE (a)-[:OCCURRED_ON]->(s);

LOAD CSV WITH HEADERS FROM 'edges_decisions_accident.csv' AS row
MATCH (d:TransportDecision {id: row.decision_id})
MATCH (a:TrafficAccident {id: row.accident_id})
MERGE (d)-[:ADDRESSES]->(a);

LOAD CSV WITH HEADERS FROM 'edges_decisions_route.csv' AS row
MATCH (d:TransportDecision {id: row.decision_id})
MATCH (r:Route {id: row.route_id})
MERGE (d)-[:AFFECTS_ROUTE]->(r);

LOAD CSV WITH HEADERS FROM 'edges_sensor_monitors.csv' AS row
MATCH (s:TrafficSensor {id: row.sensor_id})
MATCH (seg:RoadSegment {id: row.segment_id})
MERGE (s)-[r:MONITORS]->(seg)
SET r.coverage = toFloat(row.coverage);

RETURN 'LOAD COMPLETE' AS status;
