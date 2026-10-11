"""
app.py - FastAPI сервер для доступу до чат-бот системи HKB RAG.
Запуск:
    uvicorn app:app --host 127.0.0.1 --port 8000 --reload
"""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from storage import RelationalLayer, SemanticLayer, VectorLayer
from security import SecurityGuard
from pipeline import RAGPipeline

load_dotenv()

app = FastAPI(
    title="HKB Transport Dispatcher RAG API",
    description="API для роботи з гібридним сховищем знань (SQLite + RDF/OWL + ChromaDB)",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ініціалізація компонентів
ONTOLOGY_FILE = Path(os.getenv("ONTOLOGY_PATH", "update_expanded.owl"))
if not ONTOLOGY_FILE.exists():
    raise RuntimeError(f"Файл онтології не знайдено за шляхом: {ONTOLOGY_FILE}")

relational = RelationalLayer()
semantic = SemanticLayer(ONTOLOGY_FILE)
vector = VectorLayer(model_name=os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))
security_guard = SecurityGuard(max_length=int(os.getenv("MAX_QUERY_LENGTH", "500")))
rag_pipeline = RAGPipeline(
    relational=relational,
    semantic=semantic,
    vector=vector,
    similarity_threshold=float(os.getenv("VECTOR_SIMILARITY_THRESHOLD", "0.45")),
)


class AskRequest(BaseModel):
    query: str = Field(..., example="Що робити диспетчеру при аварії на вул. Франка?")


class SourceItem(BaseModel):
    id: str
    type: str
    similarity: float | None = None


class AskResponse(BaseModel):
    query: str
    answer: str
    sources: list[SourceItem]
    confidence: float
    execution_time_ms: float
    guardrail_status: str


@app.get("/health", summary="Перевірка працездатності компонентів сховища")
def health_check():
    stats = semantic.get_stats()
    return {
        "status": "healthy",
        "layers": {
            "relational_sqlite": {"status": "online", "tables": ["dim_road_segment", "fact_traffic_observations"]},
            "semantic_graph": {
                "status": "online",
                "triples_loaded": stats["triples"],
                "classes": stats["classes"],
                "individuals": stats["individuals"],
            },
            "vector_chromadb": {"status": "online", "indexed_documents": len(VectorLayer.DOCUMENTS)},
        },
    }


@app.post("/ask", response_model=AskResponse, summary="Обробка запиту через RAG конвеєр")
def ask_question(payload: AskRequest):
    # 1. Валідація та захист
    is_safe, clean_query, reason = security_guard.validate_and_sanitize(payload.query)
    if not is_safe:
        raise HTTPException(status_code=400, detail=reason)

    # 2. Виконання RAG
    result = rag_pipeline.run(clean_query)
    return result


@app.get("/trace", summary="Отримання детального логу кроків останнього запиту")
def get_trace():
    if not rag_pipeline.last_trace:
        return {"status": "empty", "message": "Жодного запиту ще не було виконано."}
    return rag_pipeline.last_trace


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)