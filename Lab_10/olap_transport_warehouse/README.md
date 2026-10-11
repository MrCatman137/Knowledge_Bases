# OLAP Cube — Digital Models of Urban Transport Systems

## 1. Project purpose

This repository implements a reproducible university BI/OLAP laboratory project for the domain **Digital Models of Urban Transport Systems**.

The warehouse uses a **star schema**:

```text
                         dim_date
                            |
                            |
dim_road_segment ---- fact_traffic_observations ---- dim_transport_route
                            |
                            |
                    dim_transport_event
```

The four dimensions describe **when**, **where**, **which transport route/mode**, and **what event/rule context** an observation belongs to. The fact table stores additive and semi-additive traffic/transport measurements.

### Metadata card

| Item | Definition |
|---|---|
| Business process | Hourly/periodic urban traffic observation |
| Fact table | `fact_traffic_observations` |
| Fact grain | **One row per DateKey + SegmentKey + RouteKey** |
| Observation count | 5,000 deterministic synthetic rows |
| Time coverage | 2026-01-01 through 2026-09-30 |
| Spatial coverage | 15 road segments, 5 districts |
| Routes/modes | Bus R-05, Bus R-24, Tram R-35, Private Car |
| Event context | Normal Flow, Traffic Accident, Road Works, Lane Closure |
| Volume unit | vehicles/hour |
| Passenger unit | passengers/hour |
| Speed unit | km/h |
| Delay unit | minutes |
| Incident/alert | binary 0/1 flags |
| Warehouse type | Star schema |
| BI platform | Microsoft Power BI Desktop |
| Generator | Python + pandas + numpy |
| Determinism | Seed `20260929` |

## 2. Important schema decision: DateKey and Hour

The assignment requests both:

- `DateKey = YYYYMMDD`, and
- an `Hour` attribute from 0 to 23 in `dim_date`.

A relational dimension cannot use `YYYYMMDD` as a unique key while also storing 24 rows for the same date. That would make the one-side of the Power BI relationship non-unique.

This implementation therefore uses:

- **one row per calendar date** in `dim_date`;
- `DateKey` remains the required `YYYYMMDD` integer;
- `Hour` is the deterministic scheduled observation-cut hour for that date;
- `IsPeakHour` and `TimeOfDay` are derived from that scheduled cut;
- the fact contains `ObservationHour` so the observation time remains explicit.

This preserves the requested five CSVs and a valid 1-to-many star schema.

If a future project requires **multiple observations per day**, use a sixth `dim_time` or a `DateHourKey = YYYYMMDDHH` surrogate key. Do not create a Power BI one-to-many relationship from a non-unique `DateKey`.

## 3. Repository structure

```text
olap_transport_warehouse/
├── generate_warehouse_data.py
├── etl_pipeline.py
├── dax_measures.md
├── README.md
├── requirements.txt
├── .gitignore
├── data/
│   ├── dim_date.csv
│   ├── dim_road_segment.csv
│   ├── dim_transport_route.csv
│   ├── dim_transport_event.csv
│   └── fact_traffic_observations.csv
└── clean_data/
    ├── dim_date.csv
    ├── dim_road_segment.csv
    ├── dim_transport_route.csv
    ├── dim_transport_event.csv
    ├── fact_traffic_observations.csv
    └── etl_validation_report.txt
```

## 4. Ontology/taxonomy mapping

The warehouse is a dimensional analytical projection of the domain ontology.

| Ontology/domain concept | Warehouse representation |
|---|---|
| `RoadSegment` | `dim_road_segment` |
| `Intersection` | Not directly measured at the selected fact grain; can be a future dimension |
| `BusStop` | `OriginStop`, `TerminalStop` in route dimension |
| `Vehicle`, `Car`, `Bus` | `TransportType` and route dimension |
| `Route` | `dim_transport_route` |
| `TrafficFlow` | Fact measures `VehicleCount`, `ObservedSpeed` |
| `TrafficAccident` | Event dimension: `Traffic Accident` |
| `RoadClosure` | Event dimension: `Lane Closure` |
| `RoadWorks` | Event dimension: `Road Works` |
| `CongestionLevel` | `CongestionAlertFlag` and derived measures |
| `DecisionRule` | `DecisionRule` in event dimension |
| `TransportDecision` | `RecommendedAction` |
| `SpeedData` | `ObservedSpeed` |
| `VehicleCountData` | `VehicleCount` |
| `GPSMeasurement` | Conceptual source for observation measurements; not separately modeled at this aggregate grain |

This is deliberate: an OLAP model should not copy every ontology class into a dimension. It should preserve analytical subjects, dimensions, hierarchies, measures, and the required grain.

## 5. Installation and execution

Python 3.10+ is recommended.

```bash
python -m pip install -r requirements.txt
python generate_warehouse_data.py
python etl_pipeline.py
```

The generator creates `data/`. The ETL pipeline validates all five files and creates `clean_data/`.

Expected validation:

```text
ETL VALIDATION PASSED
...
Foreign-key checks: PASS
Null checks: PASS
Type/range checks: PASS
```

The generator is deterministic because it uses NumPy's `default_rng(20260929)`.

## 6. Input data contracts

### `dim_date.csv`

- `DateKey`: integer `YYYYMMDD`
- `FullDate`: ISO date
- `Year`: 2026
- `Quarter`: Q1, Q2, Q3
- `MonthNumber`: 1..9
- `MonthName`
- `Day`: 1..31
- `DayOfWeek`
- `Hour`: 0..23 scheduled observation cut
- `IsPeakHour`: TRUE for 07–09 and 17–19
- `TimeOfDay`: Morning Peak, Midday, Evening Peak, Night

### `dim_road_segment.csv`

15 segments:

- `SegmentKey`
- `SegmentID` such as `DS-001`
- `SegmentName`
- `District`: Central/North/South/West/East
- `RoadType`: Avenue/Street/Highway
- `LanesCount`: 1..4
- `AllowedSpeed`: 50/60/80 km/h
- `LengthMeters`

### `dim_transport_route.csv`

Four modal records:

- R-05 / Bus / route 5
- R-24 / Bus / route 24
- R-35 / Tram / route 35
- Private_Traffic / Private Car

### `dim_transport_event.csv`

The event dimension acts as a small rule/event taxonomy:

| Event | Severity | Rule | Action |
|---|---|---|---|
| Normal Flow | None | None | Maintain |
| Traffic Accident | High | RuleIncidentReroute | Suggest Alternative Route |
| Road Works | Medium | RuleHighCongestion | Adjust Traffic Lights |
| Lane Closure | Low | RuleHighCongestion | Adjust Traffic Lights |

### Fact table

The grain is:

> **One observation for one calendar date, road segment and transport route.**

Foreign keys:

- `DateKey`
- `SegmentKey`
- `RouteKey`
- `EventKey`

Measures:

- `VehicleCount`
- `PassengerCount`
- `ObservedSpeed`
- `DelayMinutes`
- `IncidentFlag`
- `CongestionAlertFlag`

Additional analytical attributes:

- `ObservationHour`
- `IsPeakObservation`

## 7. Power BI import

### Step 1 — Create the report

Open **Power BI Desktop**.

Choose:

**Home → Get data → Text/CSV**

Import the five files from `clean_data/`.

Recommended table names:

- `dim_date`
- `dim_road_segment`
- `dim_transport_route`
- `dim_transport_event`
- `fact_traffic_observations`

### Step 2 — Set data types

In Model/Table view:

`dim_date`

- `DateKey`: Whole number
- `FullDate`: Date
- `Year`: Whole number
- `Quarter`: Text
- `MonthNumber`: Whole number
- `MonthName`: Text
- `Day`: Whole number
- `Hour`: Whole number
- `IsPeakHour`: True/False
- `TimeOfDay`: Text

`fact_traffic_observations`

- keys/hours/counts/flags: Whole number
- `ObservedSpeed`: Decimal number
- `DelayMinutes`: Decimal number

### Step 3 — Create relationships

Use **Model view → Manage relationships → New**.

Create exactly these four relationships:

| One side | Many side | Cardinality | Cross-filter |
|---|---|---|---|
| `dim_date[DateKey]` | `fact_traffic_observations[DateKey]` | 1:* | Single |
| `dim_road_segment[SegmentKey]` | `fact_traffic_observations[SegmentKey]` | 1:* | Single |
| `dim_transport_route[RouteKey]` | `fact_traffic_observations[RouteKey]` | 1:* | Single |
| `dim_transport_event[EventKey]` | `fact_traffic_observations[EventKey]` | 1:* | Single |

Do **not** enable bidirectional filtering for this laboratory model.

The resulting model should visibly look like a star: dimensions around the fact.

## 8. Build hierarchies

### Date Hierarchy

Right-click `dim_date[Year]` → **New hierarchy**.

Add:

1. Year
2. Quarter
3. MonthName
4. Day

Sort `MonthName` by `MonthNumber`:

1. Select `dim_date[MonthName]`.
2. **Column tools → Sort by column → MonthNumber**.

Do not use Power BI's automatically generated hidden date hierarchy for the assessed model; use the explicit hierarchy.

### Geography / Infrastructure Hierarchy

In `dim_road_segment` create:

1. District
2. RoadType
3. SegmentName

This supports roll-up:

**District → RoadType → Segment**

### Transit Hierarchy

In `dim_transport_route` create:

1. TransportType
2. RouteNumber
3. RouteID

For `RouteNumber = "None"` the Private Car row remains visible as non-route traffic.

## 9. DAX measures

All required formulas are in `dax_measures.md`.

Create a dedicated Power BI measure table if desired:

**Home → Enter data → Measures**

or simply create the measures in the fact table.

Core measures:

```DAX
[Total Vehicle Volume]
    = SUM(fact_traffic_observations[VehicleCount])

[Total Passengers]
    = SUM(fact_traffic_observations[PassengerCount])

[Average Observed Speed]
    = AVERAGE(fact_traffic_observations[ObservedSpeed])

[Average Delay (min)]
    = AVERAGE(fact_traffic_observations[DelayMinutes])

[Total Incidents]
    = SUM(fact_traffic_observations[IncidentFlag])
```

## 10. Seven competency questions and Power BI implementation

### KQ1 — Which road segments are slowest/most congested during peak hours?

**OLAP operations:** Slice + TOP-N.

1. Add a clustered bar chart.
2. Y-axis: `dim_road_segment[SegmentName]`.
3. X-axis: `[Average Observed Speed]`.
4. Add page/visual filter:
   - `dim_date[IsPeakHour] = TRUE`.
5. Add Top N filter:
   - SegmentName → Top 5 → by `[Average Observed Speed]`.
6. Sort ascending.

Alternative congestion view:

- Y-axis: SegmentName
- X-axis: `[High Congestion Rule Triggers Count]`

**Report evidence:** visible TRUE peak-hour filter and Top 5 filter.

### KQ2 — How does vehicle intensity change over time?

**OLAP operations:** Roll-up / drill-down.

1. Line chart.
2. X-axis: Date Hierarchy.
3. Values: `[Total Vehicle Volume]`.
4. Enable drill mode.
5. Demonstrate:
   - Year
   - Quarter
   - Month
   - Day

The user should be able to drill from the annual view to a daily view and roll back up.

### KQ3 — How do incidents affect speed and delay?

**OLAP operation:** Dice.

Use:

- X-axis: `dim_transport_event[EventType]`
- Column value: `[Average Observed Speed]`
- Tooltip: `[Average Delay (min)]`
- Slicer 1: SeverityLevel
- Slicer 2: EventType

For a cleaner comparison, use a combo chart with speed as columns and delay as a line because the units differ.

### KQ4 — What is the modal split?

**OLAP operation:** Slice by `TransportType`.

Use a donut or treemap:

- Group: `dim_transport_route[TransportType]`
- Values: `[Volume % of Total]`

This shows each mode's vehicle-volume contribution.

### KQ5 — Which public-transit routes combine passenger volume and delay?

**OLAP operation:** Dice/filter.

Use a scatter chart:

- X: `[Total Passengers]`
- Y: `[Average Delay (min)]`
- Legend: `dim_transport_route[RouteNumber]`
- Details: RouteID
- Filter: TransportType = Bus or Tram

A matrix alternative:

- Rows: RouteNumber
- Values: Total Passengers, Average Delay, Average Observed Speed

### KQ6 — How does incident volume change month over month?

**OLAP operation:** Period comparison.

Use a matrix:

- Rows: Date Hierarchy at Month level
- Values: `[Total Incidents]`, `[Incidents MoM Change]`, `[Incidents MoM %]`

The `MonthNumber` sort is required.

### KQ7 — Where are RuleHighCongestion activations concentrated?

**OLAP operation:** Slice + aggregation.

Use:

- Card: `[High Congestion Rule Triggers Count]`
- Bar chart:
  - Axis: District
  - Values: `[High Congestion Rule Triggers Count]`

Add `dim_transport_event[DecisionRule]` as a visual/page filter when demonstrating the rule explicitly.

## 11. Suggested Power BI report pages

### Page 1 — OLAP Model Overview

Show:

- Star-schema model screenshot
- KPI cards:
  - Total Vehicle Volume
  - Total Passengers
  - Average Observed Speed
  - Total Incidents
- Date coverage

### Page 2 — Temporal OLAP Analysis

Show KQ2 and KQ6.

Evidence:

- Year → Quarter → Month → Day hierarchy
- drill-down button
- monthly incident comparison

### Page 3 — Infrastructure and Congestion

Show KQ1 and KQ7.

Evidence:

- Peak Hour slicer
- Top-N filter
- district aggregation
- congestion-rule measure

### Page 4 — Events and Incidents

Show KQ3.

Evidence:

- EventType
- SeverityLevel slicer
- speed/delay comparison

### Page 5 — Transit / Modal Analysis

Show KQ4 and KQ5.

Evidence:

- TransportType modal split
- route hierarchy
- passenger volume versus delay

## 12. Screenshot checklist for the university report

Capture at least:

1. **Generated data**
   - Explorer showing the five CSV files.
2. **ETL validation**
   - `etl_validation_report.txt` showing PASS.
3. **Power BI model**
   - Four 1:* single-direction relationships.
4. **Date hierarchy**
   - Year → Quarter → Month → Day.
5. **Infrastructure hierarchy**
   - District → RoadType → Segment.
6. **Transit hierarchy**
   - TransportType → RouteNumber → RouteID.
7. **KQ1**
   - Top-5 + Peak Hour filter visible.
8. **KQ2**
   - Drill-down from Year to Month/Day.
9. **KQ3**
   - Event type and severity analysis.
10. **KQ4**
   - Modal split.
11. **KQ5**
   - Passenger volume vs delay by route.
12. **KQ6**
   - Month-over-month incident table.
13. **KQ7**
   - RuleHighCongestion count by district.
14. **DAX**
   - Formula bar visible for at least the advanced measures.

For maximum rubric coverage, screenshots should show not only the chart but also the relevant slicer/filter, hierarchy level, or OLAP operation.

## 13. ETL validation strategy

The ETL layer verifies:

### Structural integrity

- required files exist;
- required columns exist;
- dimension primary keys are unique.

### Null integrity

No null values are allowed in the synthetic warehouse because every fact row must resolve to a valid dimensional context.

### Referential integrity

Every fact:

- `DateKey` exists in `dim_date`;
- `SegmentKey` exists in `dim_road_segment`;
- `RouteKey` exists in `dim_transport_route`;
- `EventKey` exists in `dim_transport_event`.

### Grain integrity

The pipeline checks:

```text
DateKey + SegmentKey + RouteKey
```

for duplicates.

### Domain integrity

The pipeline checks:

- vehicle volume 200..1800;
- passengers 0..2500;
- speed 0..80 km/h;
- delay 0..45 minutes;
- binary flags are 0/1;
- observation hour is 0..23;
- private-car passenger count is zero.

## 14. OLAP terminology used in the project

### Slice

Fix one dimension value or condition.

Example:

```text
IsPeakHour = TRUE
```

### Dice

Select a subcube using multiple dimension restrictions.

Example:

```text
SeverityLevel in {Medium, High}
AND EventType != Normal Flow
```

### Roll-up

Aggregate to a higher hierarchy level.

Example:

```text
Day → Month → Quarter → Year
```

### Drill-down

Move to a more detailed hierarchy level.

Example:

```text
Year → Quarter → Month → Day
```

### Top-N

Return only the N members with the selected measure.

Example:

```text
Top 5 segments by lowest average speed
```

## 15. Architecture limitations

### 15.1 Synthetic data

The dataset is generated rather than collected from operational ITS sensors. Therefore, its purpose is to demonstrate dimensional modeling, OLAP operations, DAX, and BI visualization rather than to establish real-world traffic statistics.

### 15.2 Aggregated observations

The fact grain is deliberately limited to:

```text
Date + Road Segment + Route
```

It is not a raw GPS telemetry warehouse. A production ITS platform would normally retain a finer-grained telemetry fact, potentially at vehicle/event/time resolution.

### 15.3 Event dimension

The event dimension is modeled as a compact analytical taxonomy. In a production system, accidents, road works, closures, decisions, and rule executions would normally have separate event entities and timestamps.

### 15.4 Intersection and bus-stop entities

`Intersection` and individual `BusStop` are present in the source ontology but are not independent dimensions in this four-dimension laboratory star. They can be added in an expanded model if intersection-level or stop-level analysis becomes a requirement.

## 16. Batch versus streaming latency

### Batch ETL

Current architecture:

```text
Synthetic/source files
       ↓
Python ETL
       ↓
Clean CSV
       ↓
Power BI Import
```

Advantages:

- simple;
- reproducible;
- easy to validate;
- suitable for a university OLAP laboratory.

Latency is typically minutes or longer depending on scheduling and refresh.

### Streaming

A production Intelligent Transportation System can instead use:

```text
Sensors/GPS
   ↓
Message broker
   ↓
Stream processing
   ↓
Operational/analytical store
   ↓
Power BI real-time or near-real-time semantic model
```

This reduces latency but increases requirements for:

- event-time handling;
- late-arriving data;
- deduplication;
- watermarking;
- schema evolution;
- fault tolerance;
- exactly-once or effectively-once processing semantics.

For this assignment, batch import is preferable because the objective is dimensional/OLAP modeling rather than stream processing.

## 17. Slowly Changing Dimensions — SCD Type 2

Road-network attributes change.

For example:

```text
DS-001
AllowedSpeed: 50 → 60
LanesCount: 2 → 3
RoadType: Street → Avenue
```

Overwriting the existing dimension row would destroy historical context.

SCD Type 2 solves this by creating a new dimension version:

| SegmentKey | SegmentID | AllowedSpeed | LanesCount | ValidFrom | ValidTo | IsCurrent |
|---:|---|---:|---:|---|---|---|
| 101 | DS-001 | 50 | 2 | 2026-01-01 | 2026-06-30 | 0 |
| 145 | DS-001 | 60 | 3 | 2026-07-01 | 9999-12-31 | 1 |

The fact table then references the **versioned surrogate key**, not only the business identifier `DS-001`.

For a real production warehouse:

1. detect a changed road attribute;
2. close the old dimension version;
3. insert a new surrogate key;
4. assign `ValidFrom`, `ValidTo`, and `IsCurrent`;
5. resolve incoming facts to the version valid at observation time.

This is especially important for historical speed-limit, lane-count, and geometry analysis.

## 18. How the project demonstrates the rubric

| Competency | Evidence |
|---|---|
| Domain taxonomy/ontology used | Explicit ontology-to-dimension mapping |
| Star schema | 1 fact + 4 dimensions |
| Synthetic data | Deterministic Python generator |
| ETL | Validation and clean-data pipeline |
| Data quality | PK/FK/null/grain/domain checks |
| Hierarchies | Date, infrastructure, transit |
| OLAP operations | Slice, dice, roll-up, drill-down, Top-N |
| DAX | Base and advanced measures |
| BI visualization | Seven KQ-specific visual designs |
| Temporal analytics | YoY/MoM and date hierarchy |
| Rule analytics | RuleHighCongestion measure |
| Academic discussion | Limitations, batch/streaming, SCD Type 2 |

## 19. Reproducibility

To regenerate the entire dataset from scratch:

```bash
rm -rf data clean_data
python generate_warehouse_data.py
python etl_pipeline.py
```

On Windows PowerShell:

```powershell
Remove-Item -Recurse -Force data, clean_data
python generate_warehouse_data.py
python etl_pipeline.py
```

The random seed is fixed, so the generated dataset is reproducible.

## 20. Final submission checklist

Before submitting:

- [ ] `generate_warehouse_data.py` executes without errors.
- [ ] Five source CSVs exist.
- [ ] `etl_pipeline.py` executes without errors.
- [ ] Five clean CSVs exist.
- [ ] ETL report says PASS.
- [ ] Power BI has four 1:* single-direction relationships.
- [ ] Date hierarchy is configured.
- [ ] Infrastructure hierarchy is configured.
- [ ] Transit hierarchy is configured.
- [ ] All DAX measures compile.
- [ ] KQ1–KQ7 visuals are present.
- [ ] Top-N and Peak Hour are visible for KQ1.
- [ ] Drill-down is demonstrated for KQ2.
- [ ] Severity/EventType slicing is demonstrated for KQ3.
- [ ] Modal split is demonstrated for KQ4.
- [ ] Route passenger/delay comparison is demonstrated for KQ5.
- [ ] MoM incident analysis is demonstrated for KQ6.
- [ ] RuleHighCongestion analysis is demonstrated for KQ7.
- [ ] Model limitations are discussed in the report.
- [ ] Batch vs streaming is discussed.
- [ ] SCD Type 2 is discussed.
