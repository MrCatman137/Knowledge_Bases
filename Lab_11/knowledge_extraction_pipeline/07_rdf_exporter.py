from pathlib import Path
import pandas as pd
from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF, RDFS, SKOS

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "output" / "triples.csv"
OUTPUT = ROOT / "output" / "knowledge_graph.ttl"

NS = Namespace("http://example.org/kmkg/")

def resource(label):
    return NS[str(label).strip().lower().replace(" ", "_").replace("-", "_").replace("/", "_")]

def main():
    df = pd.read_csv(INPUT)
    g = Graph()
    g.bind("", NS)
    g.bind("skos", SKOS)
    g.bind("rdfs", RDFS)
    g.bind("rdf", RDF)

    for _, row in df.iterrows():
        s = resource(row["subject"])
        p = row["predicate"]
        o_text = str(row["object"])

        if p == "type":
            o = NS[o_text]
            g.add((s, RDF.type, o))
        elif p == "prefLabel":
            g.add((s, SKOS.prefLabel, Literal(o_text, lang="en")))
        elif p == "altLabel":
            g.add((s, SKOS.altLabel, Literal(o_text, lang="en")))
        elif p == "broader":
            g.add((s, SKOS.broader, resource(o_text)))
        elif p == "contains":
            g.add((s, NS.contains, Literal(o_text)))
        else:
            g.add((s, NS[p], resource(o_text)))

    # Add SKOS typing for concepts that have labels.
    for s in set(g.subjects(SKOS.prefLabel, None)):
        g.add((s, RDF.type, SKOS.Concept))

    g.serialize(destination=OUTPUT, format="turtle")
    print(f"[07] Wrote {OUTPUT}")
    print(f"[07] RDF triples: {len(g)}")

if __name__ == "__main__":
    main()
