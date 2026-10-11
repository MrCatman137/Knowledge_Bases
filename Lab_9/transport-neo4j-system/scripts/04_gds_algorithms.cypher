// 04_gds_algorithms.cypher
// Neo4j Graph Data Science.
// The Docker Compose service installs the official GDS plugin.
// Projection intentionally uses only RoadSegment nodes and NETWORK relationships,
// producing a focused transport-road topology for centrality analysis.
//
// Run this script after 01_schema_constraints.cypher and 02_load_data.cypher.

CALL gds.graph.exists('transportRoadNetwork')
YIELD exists
WITH exists
WHERE exists
CALL gds.graph.drop('transportRoadNetwork', false)
YIELD graphName
RETURN graphName AS droppedGraph;

CALL gds.graph.project(
  'transportRoadNetwork',
  'RoadSegment',
  {
    NETWORK: {
      orientation: 'UNDIRECTED',
      properties: 'travelTimeMin'
    }
  }
)
YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount;


// GDS-01 — Degree Centrality.
// Interpretation: segments with many adjacent road links are highly connected
// transfer points in the road topology.
CALL gds.degree.stream('transportRoadNetwork', {orientation: 'UNDIRECTED'})
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).id AS segmentId,
       gds.util.asNode(nodeId).name AS segmentName,
       score AS degreeCentrality
ORDER BY degreeCentrality DESC, segmentId
LIMIT 15;


// GDS-02 — PageRank.
// Interpretation: high score identifies structurally important segments that
// are connected to other important segments, useful for network prioritization.
CALL gds.pageRank.stream('transportRoadNetwork', {
  dampingFactor: 0.85,
  maxIterations: 100
})
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).id AS segmentId,
       gds.util.asNode(nodeId).name AS segmentName,
       round(score, 6) AS pageRank
ORDER BY pageRank DESC, segmentId
LIMIT 15;


// GDS-03 — Betweenness Centrality.
// Interpretation: high score identifies bridge-like segments that occur on
// many shortest paths; these are candidates for detour planning and disruption monitoring.
CALL gds.betweenness.stream('transportRoadNetwork', {
  concurrency: 2
})
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).id AS segmentId,
       gds.util.asNode(nodeId).name AS segmentName,
       round(score, 6) AS betweenness
ORDER BY betweenness DESC, segmentId
LIMIT 15;


// GDS-04 — Algorithm statistics for reproducible benchmarking.
CALL gds.degree.stats('transportRoadNetwork', {orientation: 'UNDIRECTED'})
YIELD centralityDistribution, preProcessingMillis, computeMillis, postProcessingMillis
RETURN 'Degree Centrality' AS algorithm,
       preProcessingMillis, computeMillis, postProcessingMillis,
       centralityDistribution;


// GDS-05 — PageRank statistics.
CALL gds.pageRank.stats('transportRoadNetwork', {
  dampingFactor: 0.85,
  maxIterations: 100
})
YIELD ranIterations, didConverge, preProcessingMillis, computeMillis, postProcessingMillis
RETURN 'PageRank' AS algorithm,
       ranIterations, didConverge,
       preProcessingMillis, computeMillis, postProcessingMillis;


// GDS-06 — Betweenness statistics with deterministic sampling seed.
CALL gds.betweenness.stats('transportRoadNetwork', {
  concurrency: 2,
  samplingSize: 50,
  samplingSeed: 42
})
YIELD centralityDistribution, preProcessingMillis, computeMillis, postProcessingMillis
RETURN 'Betweenness Centrality' AS algorithm,
       preProcessingMillis, computeMillis, postProcessingMillis,
       centralityDistribution;
