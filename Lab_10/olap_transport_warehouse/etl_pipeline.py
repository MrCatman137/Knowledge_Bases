"""
ETL validation and cleansing pipeline.

Run:
    python etl_pipeline.py

Input:
    data/*.csv

Output:
    clean_data/*.csv
    clean_data/etl_validation_report.txt
"""
from pathlib import Path
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CLEAN_DIR = BASE_DIR / "clean_data"
CLEAN_DIR.mkdir(parents=True, exist_ok=True)

FILES = {
    "date": DATA_DIR / "dim_date.csv",
    "segment": DATA_DIR / "dim_road_segment.csv",
    "route": DATA_DIR / "dim_transport_route.csv",
    "event": DATA_DIR / "dim_transport_event.csv",
    "fact": DATA_DIR / "fact_traffic_observations.csv",
}

REQUIRED = {
    "date": ["DateKey", "FullDate", "Year", "Quarter", "MonthNumber", "MonthName",
             "Day", "DayOfWeek", "Hour", "IsPeakHour", "TimeOfDay"],
    "segment": ["SegmentKey", "SegmentID", "SegmentName", "District", "RoadType",
                "LanesCount", "AllowedSpeed", "LengthMeters"],
    "route": ["RouteKey", "RouteID", "RouteNumber", "TransportType", "OriginStop", "TerminalStop"],
    "event": ["EventKey", "EventType", "SeverityLevel", "DecisionRule", "RecommendedAction"],
    "fact": ["DateKey", "SegmentKey", "RouteKey", "EventKey", "ObservationHour",
             "IsPeakObservation", "VehicleCount", "PassengerCount", "ObservedSpeed",
             "DelayMinutes", "IncidentFlag", "CongestionAlertFlag"],
}

def fail(message: str, errors: list[str]) -> None:
    errors.append(message)

def main() -> None:
    errors: list[str] = []
    frames: dict[str, pd.DataFrame] = {}

    for name, path in FILES.items():
        if not path.exists():
            fail(f"Missing input file: {path}", errors)
            continue
        frames[name] = pd.read_csv(path, keep_default_na=False)

    for name, required_cols in REQUIRED.items():
        if name not in frames:
            continue
        missing = [c for c in required_cols if c not in frames[name].columns]
        if missing:
            fail(f"{name}: missing columns: {missing}", errors)

    if errors:
        raise SystemExit("\n".join(errors))

    date = frames["date"].copy()
    segment = frames["segment"].copy()
    route = frames["route"].copy()
    event = frames["event"].copy()
    fact = frames["fact"].copy()

    # Type normalization.
    date["DateKey"] = pd.to_numeric(date["DateKey"], errors="coerce").astype("Int64")
    date["FullDate"] = pd.to_datetime(date["FullDate"], errors="coerce")
    date["Year"] = pd.to_numeric(date["Year"], errors="coerce").astype("Int64")
    date["MonthNumber"] = pd.to_numeric(date["MonthNumber"], errors="coerce").astype("Int64")
    date["Day"] = pd.to_numeric(date["Day"], errors="coerce").astype("Int64")
    date["Hour"] = pd.to_numeric(date["Hour"], errors="coerce").astype("Int64")

    for df, key in [(segment, "SegmentKey"), (route, "RouteKey"), (event, "EventKey")]:
        df[key] = pd.to_numeric(df[key], errors="coerce").astype("Int64")

    for key in ["DateKey", "SegmentKey", "RouteKey", "EventKey"]:
        fact[key] = pd.to_numeric(fact[key], errors="coerce").astype("Int64")

    integer_fact_cols = [
        "ObservationHour", "VehicleCount", "PassengerCount",
        "IncidentFlag", "CongestionAlertFlag"
    ]
    for col in integer_fact_cols:
        fact[col] = pd.to_numeric(fact[col], errors="coerce").astype("Int64")
    fact["ObservedSpeed"] = pd.to_numeric(fact["ObservedSpeed"], errors="coerce")
    fact["DelayMinutes"] = pd.to_numeric(fact["DelayMinutes"], errors="coerce")

    # Null validation.
    for name, df in frames.items():
        if df.isna().any().any():
            bad_cols = df.columns[df.isna().any()].tolist()
            fail(f"{name}: null values found in {bad_cols}", errors)

    # Dimension PK uniqueness.
    for name, df, key in [
        ("date", date, "DateKey"),
        ("segment", segment, "SegmentKey"),
        ("route", route, "RouteKey"),
        ("event", event, "EventKey"),
    ]:
        if df[key].duplicated().any():
            fail(f"{name}: duplicate primary keys in {key}", errors)

    # Fact grain required by the assignment.
    grain = ["DateKey", "SegmentKey", "RouteKey"]
    duplicate_grain = fact[fact.duplicated(grain, keep=False)]
    if not duplicate_grain.empty:
        fail(
            f"fact: duplicate grain rows for {grain}; duplicates={len(duplicate_grain)}",
            errors,
        )

    # Foreign keys.
    checks = [
        ("DateKey", date["DateKey"], "date"),
        ("SegmentKey", segment["SegmentKey"], "segment"),
        ("RouteKey", route["RouteKey"], "route"),
        ("EventKey", event["EventKey"], "event"),
    ]
    for fk, valid_values, dim_name in checks:
        invalid = fact.loc[~fact[fk].isin(valid_values), fk].dropna().unique()
        if len(invalid):
            fail(f"fact: invalid {fk} values against {dim_name}: {invalid.tolist()}", errors)

    # Domain/range checks.
    if not fact["VehicleCount"].between(200, 1800).all():
        fail("fact: VehicleCount outside 200..1800", errors)
    if not fact["PassengerCount"].between(0, 2500).all():
        fail("fact: PassengerCount outside 0..2500", errors)
    if not fact["ObservedSpeed"].between(0, 80).all():
        fail("fact: ObservedSpeed outside 0..80", errors)
    if not fact["DelayMinutes"].between(0, 45).all():
        fail("fact: DelayMinutes outside 0..45", errors)
    if not fact["IncidentFlag"].isin([0, 1]).all():
        fail("fact: IncidentFlag must be 0/1", errors)
    if not fact["CongestionAlertFlag"].isin([0, 1]).all():
        fail("fact: CongestionAlertFlag must be 0/1", errors)
    if not fact["ObservationHour"].between(0, 23).all():
        fail("fact: ObservationHour outside 0..23", errors)

    # Referential semantic checks.
    route_map = route.set_index("RouteKey")["TransportType"]
    private = fact["RouteKey"].map(route_map).eq("Private Car")
    if not fact.loc[private, "PassengerCount"].eq(0).all():
        fail("fact: private-car observations must have PassengerCount=0", errors)

    if errors:
        report = "ETL VALIDATION FAILED\n\n" + "\n".join(f"- {e}" for e in errors)
        (CLEAN_DIR / "etl_validation_report.txt").write_text(report, encoding="utf-8")
        raise SystemExit(report)

    # Clean output: stable ordering, explicit integer/boolean representations.
    date["DateKey"] = date["DateKey"].astype(int)
    date["FullDate"] = date["FullDate"].dt.strftime("%Y-%m-%d")
    for col in ["Year", "MonthNumber", "Day", "Hour"]:
        date[col] = date[col].astype(int)

    for df, key in [(segment, "SegmentKey"), (route, "RouteKey"), (event, "EventKey")]:
        df[key] = df[key].astype(int)

    for col in ["DateKey", "SegmentKey", "RouteKey", "EventKey",
                "ObservationHour", "VehicleCount", "PassengerCount",
                "IncidentFlag", "CongestionAlertFlag"]:
        fact[col] = fact[col].astype(int)

    for col in ["ObservedSpeed", "DelayMinutes"]:
        fact[col] = fact[col].round(1)

    outputs = {
        "dim_date.csv": date,
        "dim_road_segment.csv": segment,
        "dim_transport_route.csv": route,
        "dim_transport_event.csv": event,
        "fact_traffic_observations.csv": fact,
    }
    for filename, df in outputs.items():
        df.to_csv(CLEAN_DIR / filename, index=False)

    report = f"""ETL VALIDATION PASSED
Generated: {pd.Timestamp.now().isoformat(timespec="seconds")}
Dates: {len(date):,}
Road segments: {len(segment):,}
Routes: {len(route):,}
Events: {len(event):,}
Fact rows: {len(fact):,}
Fact grain: DateKey + SegmentKey + RouteKey
Foreign-key checks: PASS
Null checks: PASS
Type/range checks: PASS
"""
    (CLEAN_DIR / "etl_validation_report.txt").write_text(report, encoding="utf-8")
    print(report)

if __name__ == "__main__":
    main()
