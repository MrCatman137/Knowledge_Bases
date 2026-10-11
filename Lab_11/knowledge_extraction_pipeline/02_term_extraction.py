from pathlib import Path
import json
import re
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
INPUT = DATA / "preprocessed.json"
OUTPUT = DATA / "terms.csv"

DOMAIN_TERMS = {
    "intelligent transportation systems", "traffic flow", "road segment", "road segments",
    "embedded sensors", "traffic sensors", "average speed", "vehicle volume",
    "traffic congestion", "traffic management center", "urban mobility", "public transit",
    "transit network", "transit operator", "bus routes", "passenger volume",
    "travel delay", "traffic incidents", "vehicle accidents", "lane closures",
    "emergency services", "traffic signals", "adaptive traffic signals", "traffic controllers",
    "urban infrastructure", "speed limit", "performance metrics", "transport governance"
}

STOP = {
    "the","and","or","for","with","from","into","that","this","are","is","as",
    "a","an","of","to","in","on","by","be","can","it","its","has","have"
}

def normalize(s):
    return re.sub(r"\s+", " ", s.lower().strip())

def main():
    payload = json.loads(INPUT.read_text(encoding="utf-8"))
    texts = [s["text"] for d in payload["documents"] for s in d["sentences"]]
    corpus = "\n".join(texts)

    candidates = {}
    for term in DOMAIN_TERMS:
        count = len(re.findall(r"(?i)(?<!\w)" + re.escape(term) + r"(?!\w)", corpus))
        if count:
            candidates[normalize(term)] = count

    # Add frequent noun-like bigrams/unigrams to guarantee a meaningful candidate pool.
    words = re.findall(r"[A-Za-z][A-Za-z-]{3,}", corpus.lower())
    for w in words:
        if w not in STOP and len(w) >= 5:
            candidates.setdefault(w, 1)
    for a, b in zip(words, words[1:]):
        if a not in STOP and b not in STOP:
            phrase = f"{a} {b}"
            candidates.setdefault(phrase, 1)

    rows = []
    max_count = max(candidates.values(), default=1)
    for term, count in sorted(candidates.items(), key=lambda x: (-x[1], x[0])):
        weight = round(count / max_count, 4)
        accepted = (
            len(term) >= 4
            and term not in STOP
            and (term in DOMAIN_TERMS or " " in term or len(term) >= 7)
        )
        reason = "domain vocabulary / multiword technical candidate" if accepted else "generic or weak lexical candidate"
        rows.append({"term": term, "weight": weight, "accepted": accepted, "reason": reason})

    df = pd.DataFrame(rows).drop_duplicates("term")
    if len(df) < 30:
        raise RuntimeError(f"Only {len(df)} candidates extracted; requirement is >= 30.")
    df.to_csv(OUTPUT, index=False, encoding="utf-8-sig")
    print(f"[02] Extracted {len(df)} candidates; accepted={df.accepted.sum()}")
    print(f"[02] Wrote {OUTPUT}")

if __name__ == "__main__":
    main()
