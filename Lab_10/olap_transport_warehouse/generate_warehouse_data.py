"""
Generate a deterministic synthetic OLAP warehouse for an urban transport BI lab.

Run:
    python generate_warehouse_data.py

Outputs:
    data/dim_date.csv
    data/dim_road_segment.csv
    data/dim_transport_route.csv
    data/dim_transport_event.csv
    data/fact_traffic_observations.csv

Design note:
The assignment asks for DateKey=YYYYMMDD and an Hour attribute in dim_date.
A YYYYMMDD key can only identify a date, not 24 separate hourly rows. To keep
the requested 5-file / 4-dimension star schema relationally valid, dim_date
has one row per calendar date and also exposes an Hour field representing the
scheduled observation cut for that date. The fact table stores ObservationHour
as the actual cut hour and uses DateKey as its date FK. Peak-hour analysis is
therefore driven by the fact's ObservationHour-derived IsPeakHour field in
Power BI. The requested dim_date Hour/IsPeakHour columns remain present for
the daily cut schedule. See README for the rationale.
"""
from pathlib import Path
import numpy as np
import pandas as pd

SEED = 20260929
rng = np.random.default_rng(SEED)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ----------------------------
# Dimensions
# ----------------------------
dates = pd.date_range("2026-01-01", "2026-09-30", freq="D")
# A deterministic representative observation cut per calendar date.
scheduled_hours = np.array([7, 8, 9, 12, 13, 17, 18, 19, 21, 23])
date_hours = rng.choice(scheduled_hours, size=len(dates), replace=True)

def quarter_label(month: int) -> str:
    return f"Q{((month - 1) // 3) + 1}"

def time_of_day(hour: int) -> str:
    if hour in (7, 8, 9):
        return "Morning Peak"
    if hour in (17, 18, 19):
        return "Evening Peak"
    if 10 <= hour <= 16:
        return "Midday"
    return "Night"

dim_date = pd.DataFrame({
    "DateKey": dates.strftime("%Y%m%d").astype(int),
    "FullDate": dates,
    "Year": dates.year,
    "Quarter": [quarter_label(m) for m in dates.month],
    "MonthNumber": dates.month,
    "MonthName": dates.strftime("%B"),
    "Day": dates.day,
    "DayOfWeek": dates.strftime("%A"),
    "Hour": date_hours.astype(int),
})
dim_date["IsPeakHour"] = dim_date["Hour"].isin([7, 8, 9, 17, 18, 19])
dim_date["TimeOfDay"] = dim_date["Hour"].map(time_of_day)

districts = ["Central", "North", "South", "West", "East"]
road_types = ["Avenue", "Street", "Highway"]
speed_options = [50, 60, 80]

segment_rows = []
for i in range(1, 16):
    segment_rows.append({
        "SegmentKey": i,
        "SegmentID": f"DS-{i:03d}",
        "SegmentName": f"{districts[(i - 1) % 5]} Transport Segment {i:02d}",
        "District": districts[(i - 1) % 5],
        "RoadType": road_types[(i - 1) % 3],
        "LanesCount": int(rng.integers(1, 5)),
        "AllowedSpeed": int(rng.choice(speed_options)),
        "LengthMeters": int(rng.integers(300, 1501)),
    })
dim_road_segment = pd.DataFrame(segment_rows)

route_rows = [
    (1, "R-05", "5", "Bus", "BS-001", "BS-006"),
    (2, "R-24", "24", "Bus", "BS-002", "BS-009"),
    (3, "R-35", "35", "Tram", "BS-003", "BS-008"),
    (4, "Private_Traffic", "None", "Private Car", "BS-001", "BS-009"),
]
dim_transport_route = pd.DataFrame(
    route_rows,
    columns=["RouteKey", "RouteID", "RouteNumber", "TransportType", "OriginStop", "TerminalStop"],
)

event_rows = [
    (1, "Normal Flow", "None", "None", "Maintain"),
    (2, "Traffic Accident", "High", "RuleIncidentReroute", "Suggest Alternative Route"),
    (3, "Road Works", "Medium", "RuleHighCongestion", "Adjust Traffic Lights"),
    (4, "Lane Closure", "Low", "RuleHighCongestion", "Adjust Traffic Lights"),
]
dim_transport_event = pd.DataFrame(
    event_rows,
    columns=["EventKey", "EventType", "SeverityLevel", "DecisionRule", "RecommendedAction"],
)

# ----------------------------
# Fact table
# Grain: DateKey + SegmentKey + RouteKey
# Exactly one observation per selected date/segment/route combination.
# ----------------------------
target_rows = 5000
all_combinations = pd.MultiIndex.from_product(
    [dim_date["DateKey"], dim_road_segment["SegmentKey"], dim_transport_route["RouteKey"]],
    names=["DateKey", "SegmentKey", "RouteKey"],
).to_frame(index=False)

fact = all_combinations.sample(n=target_rows, random_state=SEED).sort_values(
    ["DateKey", "SegmentKey", "RouteKey"]
).reset_index(drop=True)

date_lookup = dim_date.set_index("DateKey")
segment_lookup = dim_road_segment.set_index("SegmentKey")
route_lookup = dim_transport_route.set_index("RouteKey")

fact["ObservationHour"] = fact["DateKey"].map(date_lookup["Hour"]).astype(int)
fact["IsPeakObservation"] = fact["ObservationHour"].isin([7, 8, 9, 17, 18, 19])
fact["AllowedSpeed"] = fact["SegmentKey"].map(segment_lookup["AllowedSpeed"]).astype(float)
fact["LanesCount"] = fact["SegmentKey"].map(segment_lookup["LanesCount"]).astype(int)
fact["TransportType"] = fact["RouteKey"].map(route_lookup["TransportType"])

# Event probabilities: normal dominates; incidents increase on peak periods.
peak = fact["IsPeakObservation"].to_numpy()
event_keys = np.zeros(len(fact), dtype=int)
u = rng.random(len(fact))
event_keys[u < np.where(peak, 0.07, 0.04)] = 2
remaining = event_keys == 0
u2 = rng.random(len(fact))
event_keys[remaining & (u2 < np.where(peak, 0.08, 0.05))] = 3
remaining = event_keys == 0
u3 = rng.random(len(fact))
event_keys[remaining & (u3 < np.where(peak, 0.05, 0.03))] = 4
event_keys[event_keys == 0] = 1
fact["EventKey"] = event_keys

event_lookup = dim_transport_event.set_index("EventKey")
fact["EventType"] = fact["EventKey"].map(event_lookup["EventType"])
fact["SeverityLevel"] = fact["EventKey"].map(event_lookup["SeverityLevel"])

# Vehicle demand model.
route_factor = fact["RouteKey"].map({
    1: 0.82, 2: 0.95, 3: 0.72, 4: 1.00
}).to_numpy()
peak_factor = np.where(peak, 1.35, 0.82)
road_factor = 0.75 + 0.18 * fact["LanesCount"].to_numpy()
base_volume = 720 * route_factor * peak_factor * road_factor
vehicle_count = base_volume + rng.normal(0, 110, len(fact))
vehicle_count = np.clip(vehicle_count, 200, 1800).round().astype(int)

# Public transit has passengers; private traffic has zero passenger count.
passenger_ratio = np.where(
    fact["TransportType"].isin(["Bus", "Tram"]),
    rng.uniform(1.0, 2.1, len(fact)),
    0.0,
)
passenger_count = np.clip(
    vehicle_count * passenger_ratio + rng.normal(0, 80, len(fact)),
    0,
    2500,
).round().astype(int)
passenger_count[fact["TransportType"].eq("Private Car").to_numpy()] = 0

# Speed degradation: peak congestion, incidents, lane effects, random noise.
congestion_pressure = np.clip(
    (vehicle_count - 650) / 1000,
    0,
    0.55,
)
speed = fact["AllowedSpeed"].to_numpy() * (
    0.88
    - np.where(peak, 0.20, 0.0)
    - congestion_pressure
)
event_penalty = fact["EventKey"].map({1: 0.0, 2: 0.38, 3: 0.18, 4: 0.12}).to_numpy()
speed = speed * (1.0 - event_penalty) + rng.normal(0, 3.5, len(fact))
speed = np.clip(speed, 8, fact["AllowedSpeed"].to_numpy()).round(1)

delay = (
    np.maximum(0, (fact["AllowedSpeed"].to_numpy() - speed) / 8)
    + np.where(peak, 2.0, 0.2)
    + fact["EventKey"].map({1: 0.0, 2: 8.0, 3: 4.0, 4: 3.0}).to_numpy()
    + rng.normal(0, 0.8, len(fact))
)
delay = np.clip(delay, 0, 45).round(1)

incident = (fact["EventKey"].to_numpy() != 1).astype(int)
congestion_alert = (speed < 0.4 * fact["AllowedSpeed"].to_numpy()).astype(int)

fact["VehicleCount"] = vehicle_count
fact["PassengerCount"] = passenger_count
fact["ObservedSpeed"] = speed
fact["DelayMinutes"] = delay
fact["IncidentFlag"] = incident
fact["CongestionAlertFlag"] = congestion_alert

fact = fact[
    [
        "DateKey", "SegmentKey", "RouteKey", "EventKey",
        "ObservationHour", "IsPeakObservation",
        "VehicleCount", "PassengerCount", "ObservedSpeed",
        "DelayMinutes", "IncidentFlag", "CongestionAlertFlag",
    ]
]

# Write CSVs with ISO dates for Power BI compatibility.
dim_date.to_csv(DATA_DIR / "dim_date.csv", index=False, date_format="%Y-%m-%d")
dim_road_segment.to_csv(DATA_DIR / "dim_road_segment.csv", index=False)
dim_transport_route.to_csv(DATA_DIR / "dim_transport_route.csv", index=False)
dim_transport_event.to_csv(DATA_DIR / "dim_transport_event.csv", index=False)
fact.to_csv(DATA_DIR / "fact_traffic_observations.csv", index=False)

print(f"Generated deterministic warehouse in: {DATA_DIR}")
print(f"Dates: {len(dim_date):,}")
print(f"Road segments: {len(dim_road_segment):,}")
print(f"Routes: {len(dim_transport_route):,}")
print(f"Events: {len(dim_transport_event):,}")
print(f"Fact rows: {len(fact):,}")
print("Fact grain: DateKey + SegmentKey + RouteKey")
