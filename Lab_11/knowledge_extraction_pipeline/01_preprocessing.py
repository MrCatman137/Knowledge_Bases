from pathlib import Path
import json
import re

try:
    import spacy
except ImportError:
    spacy = None

ROOT = Path(__file__).resolve().parent
CORPUS_DIR = ROOT / "corpus"
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
OUTPUT = DATA_DIR / "preprocessed.json"

def load_nlp():
    if spacy is None:
        return None
    for model in ("uk_core_news_sm", "xx_ent_wiki_sm"):
        try:
            return spacy.load(model)
        except Exception:
            pass
    return None

def fallback_process(text):
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    stop = {
        "і","й","та","або","для","на","у","в","з","до","що","як","це",
        "a","an","the","and","or","for","on","in","of","to","is","are"
    }
    result = []
    for sentence in sentences:
        tokens = re.findall(r"[A-Za-zА-Яа-яІіЇїЄєҐґ0-9][A-Za-zА-Яа-яІіЇїЄєҐґ0-9_-]*", sentence)
        lemmas = [t.lower() for t in tokens if t.lower() not in stop and len(t) > 2]
        result.append({"text": sentence, "tokens": tokens, "lemmas": lemmas})
    return result

def main():
    nlp = load_nlp()
    documents = []
    for path in sorted(CORPUS_DIR.glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        if nlp:
            doc = nlp(text)
            sentences = []
            for sent in doc.sents:
                tokens = [t.text for t in sent if not t.is_space]
                lemmas = [
                    t.lemma_.lower()
                    for t in sent
                    if not t.is_space and not t.is_punct and not t.is_stop and t.lemma_.strip()
                ]
                sentences.append({"text": sent.text.strip(), "tokens": tokens, "lemmas": lemmas})
        else:
            sentences = fallback_process(text)
        documents.append({"id": path.stem, "source": path.name, "sentences": sentences})
    payload = {"nlp_model": "spaCy" if nlp else "fallback", "documents": documents}
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[01] Wrote {OUTPUT}")

if __name__ == "__main__":
    main()
