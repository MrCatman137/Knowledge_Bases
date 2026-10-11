from pathlib import Path

from src.pipeline import build_graph

ROOT = Path(__file__).resolve().parent
INPUTS = [str(ROOT / "input" / "domain_description.txt")]


def main() -> None:
    app = build_graph(ROOT)
    state = app.invoke({"input_files": INPUTS})
    print("LangGraph execution completed.")
    print(f"Ontology: {state['ontology_path']}")
    print(f"Validation report: {state['validation_path']}")
    print(f"SHACL conforms: {state['validation_conforms']}")
    print("Artifacts: artifacts/01_parsed_text.json ... artifacts/06_validation.json")


if __name__ == "__main__":
    main()
