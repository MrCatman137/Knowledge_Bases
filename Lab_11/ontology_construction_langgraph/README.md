# Ontology Construction using LangGraph

Independent Study 11 — Digital Models of Urban Transportation Systems.

This repository implements a deterministic, reproducible semantic-ontology construction pipeline using an explicit LangGraph `StateGraph`. It does not require an LLM API key. The extraction nodes are intentionally auditable: they combine the generated domain corpus with a controlled domain vocabulary, then compile the result into OWL/Turtle.

## 1. Repository structure

```text
ontology_construction_langgraph/
├── artifacts/
│   ├── 01_parsed_text.json
│   ├── 02_terms_and_classes.json
│   ├── 03_relations.json
│   ├── 04_refined_schema.json
│   ├── 05_owl_generation.json
│   └── 06_validation.json
├── input/
│   └── domain_description.txt
├── output/
│   ├── ontology.ttl
│   └── shapes.shacl.ttl
├── queries/
│   ├── query1.sparql
│   ├── query2.sparql
│   ├── query3.sparql
│   ├── query4.sparql
│   └── query5.sparql
├── reports/
│   └── validation_report.txt
├── src/
│   ├── __init__.py
│   └── pipeline.py
├── GRAPHDB_GUIDE.md
├── README.md
├── requirements.txt
└── run.py
```

The `artifacts/` JSON files are regenerated on every run and are the state-cache/audit trail for the six graph nodes.

## 2. Environment

Recommended Python: 3.11 or 3.12.

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Run the complete pipeline

```bash
python run.py
```

Expected final console lines are similar to:

```text
LangGraph execution completed.
Ontology: .../output/ontology.ttl
Validation report: .../reports/validation_report.txt
SHACL conforms: True
Artifacts: artifacts/01_parsed_text.json ... artifacts/06_validation.json
```

## 4. LangGraph architecture

The graph is linear and explicit:

```text
START
  ↓
TextParser
  ↓
TermExtractor
  ↓
RelationExtractor
  ↓
SchemaRefiner
  ↓
OWLGenerator
  ↓
Validator
  ↓
END
```

`State` is a `TypedDict` containing the raw corpus, chunks, candidate terms, extracted relations, refined schema, generated ontology path, validation path, and validation status.

### Node responsibilities

1. **TextParser** — reads one or more input files and splits them into analytical paragraphs/sentences.
2. **TermExtractor** — identifies domain classes and taxonomy groups from the corpus.
3. **RelationExtractor** — produces object/datatype property candidates with domain/range/datatype metadata.
4. **SchemaRefiner** — adds disjointness, qualified cardinality restrictions, and an interconnected ABox.
5. **OWLGenerator** — serializes TBox and ABox as valid Turtle.
6. **Validator** — invokes `pyshacl.validate()` against the generated ontology and writes a human-readable report.

## 5. Formal ontology coverage

The generated ontology contains:

- 13 OWL classes, exceeding the required 10.
- 12 object properties with `rdfs:domain` and `rdfs:range`.
- 10 datatype properties with explicit XSD datatypes.
- 4 disjoint-class pairs.
- 3 qualified cardinality restrictions.
- English and Ukrainian `rdfs:label` annotations plus `rdfs:comment` annotations.
- 13 interconnected individuals.
- A SHACL shape graph with three node shapes.
- Five competency SPARQL queries.

## 6. Inspect the outputs

After running the pipeline:

```bash
# View ontology
# output/ontology.ttl

# View validation
# reports/validation_report.txt

# Inspect node-level state caches
# artifacts/*.json
```

The ontology can be loaded directly into GraphDB. Follow `GRAPHDB_GUIDE.md` for repository creation, import, query execution, and Visual Graph screenshots.

## 7. Academic reproducibility notes

The domain corpus is synthetic and included in the repository, so the experiment does not depend on an external dataset. The ontology namespace is `https://example.org/urban-transport#`. The pipeline is deterministic: repeated executions with the same input produce the same semantic content.

The extraction nodes deliberately do not claim to be a general-purpose natural-language information-extraction model. For an academic extension, an LLM can be placed behind the same node interfaces, while retaining the cached JSON artifacts as provenance and a validation gate before ontology publication.
