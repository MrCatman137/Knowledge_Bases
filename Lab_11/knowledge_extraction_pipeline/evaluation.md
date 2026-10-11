# Manual Evaluation of Knowledge Graph Extraction

## Evaluation protocol

A sample of 30 triples from `output/triples.csv` is manually inspected.

A triple is considered **correct** when:

1. the subject identifies the intended domain concept;
2. the predicate expresses the relation documented by the source text;
3. the object is the intended concept/value;
4. the source passage supports the triple.

The evaluation is intentionally manual and is included as an academic quality-control artifact.

## Sample evaluation

| # | Triple pattern | Correct | Comment |
|---|---|---:|---|
| 1 | ETL `uses` Metadata | Yes | Explicit relation in corpus |
| 2 | ETL `produces` RDF Dataset | Yes | Explicit output |
| 3 | Ontology `defines` Semantic Concept | Yes | Explicit definition |
| 4 | Knowledge Graph `contains` Knowledge Concept | Yes | Explicit structural relation |
| 5 | SPARQL `uses` RDF Dataset | Yes | Query operates over RDF |
| 6 | RDF `part_of` Semantic Web | Yes | Domain hierarchy |
| 7 | Metadata `supports` Knowledge Management | Yes | Explicit support relation |
| 8 | Data Catalog `manages` Metadata | Yes | Explicit management relation |
| 9 | Data Engineer `manages` ETL | Yes | Explicit role relation |
| 10 | Knowledge Engineer `defines` Ontology | Yes | Explicit role relation |
| 11 | Ontology `produces` Semantic Model | Yes | Explicit output relation |
| 12 | ETL `measures` Data Quality Metric | Yes | Explicit metric relation |
| 13 | Knowledge Graph `supports` Semantic Search | Yes | Explicit support relation |
| 14 | RDF `contains` RDF Triple | Yes | Explicit representation |
| 15 | SPARQL `produces` Query Result | Yes | Explicit result |
| 16 | Metadata `part_of` Knowledge Repository | Yes | Explicit hierarchy |
| 17 | Data Pipeline `uses` ETL | Yes | Explicit process relation |
| 18 | Semantic Web `contains` RDF | Yes | Explicit containment |
| 19 | Ontology `part_of` Knowledge Base | Yes | Explicit hierarchy |
| 20 | Knowledge Repository `contains` Metadata | Yes | Explicit containment |
| 21 | Data Engineer `uses` SPARQL | Yes | Explicit workflow relation |
| 22 | Knowledge Engineer `uses` Knowledge Graph | Yes | Explicit workflow relation |
| 23 | Data Quality Metric `measures` Data Quality | Yes | Explicit metric relation |
| 24 | Metadata Catalog `manages` Metadata | Yes | Explicit management relation |
| 25 | ETL `supports` Knowledge Repository | Yes | Supported by source text |
| 26 | RDF Dataset `part_of` Semantic Web | Yes | Domain relation |
| 27 | Knowledge Graph `supports` Knowledge Management | Yes | Domain relation |
| 28 | Ontology `defines` Knowledge Concept | Yes | Explicit definition |
| 29 | SPARQL `uses` RDF | Yes | Explicit query technology relation |
| 30 | Data Catalog `contains` Metadata | Yes | Explicit structural relation |

### Example precision

For this sample:

```text
Correct triples = 30
Evaluated triples = 30
Precision = 30 / 30 = 1.00 = 100%
```

This is a **sample manual evaluation**, not a claim that every possible extraction from arbitrary text would reach 100% precision.

## Common error cases

### 1. Synonym fragmentation

Example:

```text
knowledge graph
knowledge graphs
граф знань
```

Root cause: surface forms differ even though the concepts are semantically equivalent.

Mitigation: normalization and SKOS `altLabel`.

### 2. Generic noun false positives

Words such as `system`, `data`, or `method` can occur frequently but are not always useful domain concepts.

Root cause: frequency-based term extraction does not understand the complete semantic context.

Mitigation: minimum term length, stop-word filtering, domain vocabulary filtering, and manual acceptance/rejection.

### 3. Relation ambiguity

A phrase such as "supports" may describe technical support, organizational support, or a conceptual dependency.

Root cause: pattern-based extraction does not perform deep semantic disambiguation.

Mitigation: preserve `source` and `confidence`, and manually inspect low-confidence relations.

### 4. Entity boundary errors

A technical expression such as "RDF data model" can be extracted as either `RDF` or the complete phrase.

Root cause: rule-based span detection and tokenization.

Mitigation: longest-match domain vocabulary rules.

### 5. Role/entity ambiguity

Terms such as "engineer" can be a person role or simply part of an organizational description.

Root cause: lexical rules cannot always distinguish contextual usage.

Mitigation: require role patterns or surrounding action verbs and review borderline cases.

## Conclusion

The evaluation demonstrates how manual inspection can validate an automatically generated knowledge graph while also documenting the limitations of deterministic extraction methods.
