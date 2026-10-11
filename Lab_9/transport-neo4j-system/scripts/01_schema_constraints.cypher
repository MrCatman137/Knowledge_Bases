// 01_schema_constraints.cypher
// Neo4j 2026.x / Cypher 25-compatible schema.
// Idempotent DDL: IF NOT EXISTS is intentional for repeatable deployment.

CREATE CONSTRAINT intersection_id_unique IF NOT EXISTS
FOR (n:Intersection) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT segment_id_unique IF NOT EXISTS
FOR (n:RoadSegment) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT stop_id_unique IF NOT EXISTS
FOR (n:BusStop) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT route_id_unique IF NOT EXISTS
FOR (n:Route) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT vehicle_id_unique IF NOT EXISTS
FOR (n:Vehicle) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT accident_id_unique IF NOT EXISTS
FOR (n:TrafficAccident) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT decision_id_unique IF NOT EXISTS
FOR (n:TransportDecision) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT sensor_id_unique IF NOT EXISTS
FOR (n:TrafficSensor) REQUIRE n.id IS UNIQUE;

// Range indexes: numerical predicates and ordering on common operational metrics.
CREATE INDEX segment_flow_range IF NOT EXISTS
FOR (n:RoadSegment) ON (n.hourlyFlow);

CREATE INDEX segment_congestion_range IF NOT EXISTS
FOR (n:RoadSegment) ON (n.congestionIndex);

CREATE INDEX vehicle_speed_range IF NOT EXISTS
FOR (n:Vehicle) ON (n.speedKmh);

CREATE INDEX accident_cost_range IF NOT EXISTS
FOR (n:TrafficAccident) ON (n.estimatedCostUah);

// Composite index: route operational lookup by status + frequency.
CREATE INDEX route_status_frequency IF NOT EXISTS
FOR (n:Route) ON (n.status, n.frequencyMin);

// Text indexes: substring/prefix lookup for human-facing identifiers/names.
CREATE TEXT INDEX segment_name_text IF NOT EXISTS
FOR (n:RoadSegment) ON (n.name);

CREATE TEXT INDEX stop_name_text IF NOT EXISTS
FOR (n:BusStop) ON (n.name);
