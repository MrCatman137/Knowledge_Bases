// 03_analytical_queries.cypher
// Knowledge Queries (KQ). Run independently in Neo4j Browser or cypher-shell.
// KQ-01..KQ-14 cover filtering, aggregation, paths, shortest paths and profiling.
//
// For KQ-12/KQ-13 use PROFILE in Neo4j Browser to inspect operator plans.
// Expected indexed operators depend on the exact Neo4j planner/version and cache state.


// KQ-01 — Node property filtering: congested road segments.
MATCH (s:RoadSegment)
WHERE s.congestionIndex >= 0.70 AND s.hourlyFlow >= 1200
RETURN s.id, s.name, s.hourlyFlow, s.congestionIndex
ORDER BY s.congestionIndex DESC, s.hourlyFlow DESC;


// KQ-02 — Relationship property filtering: slow network links.
MATCH (a:RoadSegment)-[r:NETWORK]->(b:RoadSegment)
WHERE r.travelTimeMin >= 1.30
RETURN a.id AS fromSegment, b.id AS toSegment, r.travelTimeMin
ORDER BY r.travelTimeMin DESC;


// KQ-03 — Aggregation by road class.
MATCH (s:RoadSegment)
RETURN s.roadClass AS roadClass,
       count(*) AS segments,
       round(avg(s.lengthM), 1) AS avgLengthM,
       round(avg(s.hourlyFlow), 1) AS avgHourlyFlow,
       round(avg(s.congestionIndex), 3) AS avgCongestion
ORDER BY avgCongestion DESC;


// KQ-04 — Route service summary.
MATCH (r:Route)-[rel:SERVES_STOP]->(s:BusStop)
WITH r, count(s) AS stopCount, max(rel.sequence) AS maxSequence
RETURN r.id, r.routeNumber, r.frequencyMin, stopCount, maxSequence
ORDER BY stopCount DESC, r.routeNumber;


// KQ-05 — Vehicle distribution and average speed.
MATCH (v:Vehicle)
RETURN v.vehicleType AS vehicleType,
       v.status AS status,
       count(*) AS vehicleCount,
       round(avg(v.speedKmh), 1) AS avgSpeedKmh,
       min(v.speedKmh) AS minSpeedKmh,
       max(v.speedKmh) AS maxSpeedKmh
ORDER BY vehicleType, status;


// KQ-06 — Accident statistics by segment severity.
MATCH (a:TrafficAccident)-[:OCCURRED_ON]->(s:RoadSegment)
RETURN s.id, s.name,
       count(a) AS accidentCount,
       sum(a.injuredCount) AS injuredPeople,
       sum(a.estimatedCostUah) AS totalCostUah,
       collect(DISTINCT a.severity) AS severities
ORDER BY accidentCount DESC, totalCostUah DESC;


// KQ-07 — Sensor coverage and data reliability.
MATCH (sensor:TrafficSensor)-[m:MONITORS]->(s:RoadSegment)
RETURN s.id,
       count(sensor) AS sensorCount,
       round(avg(sensor.reliability), 3) AS avgReliability,
       round(avg(m.coverage), 3) AS avgCoverage
ORDER BY sensorCount DESC, avgReliability DESC;


// KQ-08 — Variable-length reachable network from SEG-001.
MATCH p = (start:RoadSegment {id:'SEG-001'})-[:NETWORK*1..4]->(target:RoadSegment)
WHERE start <> target
RETURN target.id AS reachableSegment,
       length(p) AS hops,
       [n IN nodes(p) | n.id] AS path
ORDER BY hops, reachableSegment
LIMIT 30;


// KQ-09 — Detour discovery: alternative paths with no direct one-hop route.
MATCH p = (a:RoadSegment {id:'SEG-001'})-[:NETWORK*2..5]->(b:RoadSegment {id:'SEG-020'})
WHERE NOT (a)-[:NETWORK]->(b)
RETURN length(p) AS hops, [n IN nodes(p) | n.id] AS detour
ORDER BY hops
LIMIT 10;


// KQ-10 — Built-in shortestPath by travel-time relationship.
MATCH p = shortestPath(
  (a:RoadSegment {id:'SEG-001'})-[:NETWORK*..15]->(b:RoadSegment {id:'SEG-020'})
)
RETURN length(p) AS hops,
       reduce(total = 0.0, r IN relationships(p) | total + r.travelTimeMin) AS travelTimeMin,
       [n IN nodes(p) | n.id] AS shortestPath;


// KQ-11 — All shortest paths between two road segments.
MATCH paths = allShortestPaths(
  (a:RoadSegment {id:'SEG-005'})-[:NETWORK*..15]->(b:RoadSegment {id:'SEG-030'})
)
RETURN length(paths) AS hops,
       [n IN nodes(paths) | n.id] AS path
ORDER BY path
LIMIT 20;


// KQ-12 — PROFILE: uniqueness-constrained lookup vs broad scan.
PROFILE
MATCH (s:RoadSegment {id:'SEG-025'})
RETURN s.id, s.name, s.hourlyFlow, s.congestionIndex;


// KQ-13 — PROFILE: range predicate using the hourly-flow range index.
PROFILE
MATCH (s:RoadSegment)
WHERE s.hourlyFlow >= 1600
RETURN s.id, s.name, s.hourlyFlow
ORDER BY s.hourlyFlow DESC;


// KQ-14 — Cross-domain analytical grouping: accidents and transport decisions by route.
MATCH (d:TransportDecision)-[:ADDRESSES]->(a:TrafficAccident)-[:OCCURRED_ON]->(s:RoadSegment)
MATCH (d)-[:AFFECTS_ROUTE]->(r:Route)
RETURN r.routeNumber AS route,
       count(DISTINCT d) AS decisions,
       count(DISTINCT a) AS addressedAccidents,
       round(avg(d.confidence), 3) AS avgDecisionConfidence,
       collect(DISTINCT a.severity) AS accidentSeverities
ORDER BY addressedAccidents DESC, avgDecisionConfidence DESC;


// KQ-15 — Property + topology: routes traversing congested segments.
MATCH (r:Route)-[c:COVERS_SEGMENT]->(s:RoadSegment)
WHERE s.congestionIndex >= 0.75
RETURN r.routeNumber AS route,
       count(s) AS congestedSegments,
       round(avg(s.congestionIndex), 3) AS avgCongestion,
       round(avg(s.hourlyFlow), 1) AS avgFlow
ORDER BY congestedSegments DESC, avgCongestion DESC;
