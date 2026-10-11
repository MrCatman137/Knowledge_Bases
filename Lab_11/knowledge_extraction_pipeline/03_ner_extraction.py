from pathlib import Path
import json
import re
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
INPUT = DATA / "preprocessed.json"
OUTPUT = DATA / "entities.csv"

VOCAB = {
    "Process": ["traffic monitoring", "accident clearance", "signal regulation", "transport governance", "route optimization"],
    "Role": ["traffic controller", "transit operator", "urban planner", "data analyst"],
    "Artifact": ["road segment", "traffic sensor", "bus route", "adaptive traffic signal", "traffic incident", "speed limit"],
    "Organization": ["traffic management center", "emergency services", "municipal transport authority"],
    "Metric": ["average speed", "vehicle volume", "travel delay", "passenger volume", "congestion index"]
}

def norm(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")

def main():
    payload = json.loads(INPUT.read_text(encoding="utf-8"))
    rows = []
    for doc in payload["documents"]:
        for sent in doc["sentences"]:
            text = sent["text"]
            lower = text.lower()
            for entity_type, terms in VOCAB.items():
                for term in terms:
                    for m in re.finditer(r"(?<!\w)" + re.escape(term.lower()) + r"(?!\w)", lower):
                        surface = text[m.start():m.end()]
                        rows.append({
                            "text": surface,
                            "normalized": norm(term),
                            "entity_type": entity_type,
                            "source": doc["source"],
                            "confidence": 0.96 if " " in term else 0.93
                        })
    df = pd.DataFrame(rows).drop_duplicates(["text","normalized","entity_type","source"])
    df.to_csv(OUTPUT, index=False, encoding="utf-8-sig")
    print(f"[03] Extracted {len(df)} entity mentions")
    print(f"[03] Wrote {OUTPUT}")

if __name__ == "__main__":
    main()
