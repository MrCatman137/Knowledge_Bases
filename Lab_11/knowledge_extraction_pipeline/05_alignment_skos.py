from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
INPUT = DATA / "relations.csv"
OUTPUT = DATA / "alignment.csv"

CONCEPTS = [
    ("Traffic Flow", "traffic flow", "traffic stream", "Traffic Monitoring"),
    ("Traffic Monitoring", "traffic monitoring", "traffic surveillance", "Transport Governance"),
    ("Road Segment", "road segment", "carriageway segment", "Transport Infrastructure"),
    ("Transport Infrastructure", "transport infrastructure", "road network", "Transport Governance"),
    ("Traffic Sensor", "traffic sensor", "embedded sensor", "Transport Infrastructure"),
    ("Average Speed", "average speed", "observed speed", "Performance Metric"),
    ("Vehicle Volume", "vehicle volume", "traffic volume", "Performance Metric"),
    ("Passenger Volume", "passenger volume", "passenger count", "Performance Metric"),
    ("Travel Delay", "travel delay", "delay minutes", "Performance Metric"),
    ("Congestion Index", "congestion index", "delay factor", "Performance Metric"),
    ("Performance Metric", "performance metric", "KPI metric", "Transport Governance"),
    ("Traffic Congestion", "traffic congestion", "traffic jam", "Traffic Flow"),
    ("Traffic Incident", "traffic incident", "road incident", "Traffic Monitoring"),
    ("Accident Clearance", "accident clearance", "crash clearance", "Emergency Management"),
    ("Public Transit Route", "public transit route", "transit line", "Transport Infrastructure"),
    ("Bus Route", "bus route", "bus line", "Public Transit Route"),
    ("Route Schedule", "route schedule", "transit timetable", "Transport Infrastructure"),
    ("Adaptive Traffic Signal", "adaptive traffic signal", "smart traffic light", "Transport Infrastructure"),
    ("Signal Timing", "signal timing", "traffic light phases", "Traffic Regulation"),
    ("Speed Limit", "speed limit", "allowed speed", "Traffic Regulation"),
    ("Safety Regulation", "safety regulation", "traffic safety rule", "Transport Governance"),
    ("Traffic Controller", "traffic controller", "traffic dispatcher", "Transport Governance"),
    ("Transit Operator", "transit operator", "bus operator", "Transport Governance"),
    ("Data Analyst", "data analyst", "traffic analyst", "Transport Governance"),
    ("Emergency Services", "emergency services", "rescue service", "Transport Governance"),
    ("Traffic Management Center", "traffic management center", "TMC", "Transport Governance"),
    ("Municipal Transport Authority", "municipal transport authority", "city traffic authority", "Transport Governance"),
]
def main():
    pd.DataFrame(CONCEPTS, columns=["concept","prefLabel","altLabel","broader"]).to_csv(
        OUTPUT, index=False, encoding="utf-8-sig"
    )
    print(f"[05] Wrote {OUTPUT} with {len(CONCEPTS)} SKOS concepts")

if __name__ == "__main__":
    main()
