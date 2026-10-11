from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent

STAGES = [
    "01_preprocessing.py",
    "02_term_extraction.py",
    "03_ner_extraction.py",
    "04_relation_extraction.py",
    "05_alignment_skos.py",
    "06_build_triples.py",
    "07_rdf_exporter.py",
]

def run(script):
    print(f"\n{'='*70}\nRunning {script}\n{'='*70}")
    result = subprocess.run([sys.executable, str(ROOT / script)], cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(f"Pipeline failed at {script} with exit code {result.returncode}")

def main():
    for script in STAGES:
        run(script)

    triples = ROOT / "output" / "triples.csv"
    ttl = ROOT / "output" / "knowledge_graph.ttl"
    terms = ROOT / "data" / "terms.csv"

    import pandas as pd
    triple_count = len(pd.read_csv(triples))
    term_count = len(pd.read_csv(terms))

    print("\n" + "="*70)
    print("PIPELINE COMPLETED")
    print("="*70)
    print(f"Term candidates : {term_count}")
    print(f"Unique triples  : {triple_count}")
    print(f"Triple CSV      : {triples}")
    print(f"Turtle graph    : {ttl}")

    if term_count < 30:
        raise RuntimeError("Term extraction requirement failed: fewer than 30 candidates.")
    if triple_count < 30:
        raise RuntimeError("Triple requirement failed: fewer than 30 triples.")

if __name__ == "__main__":
    main()
