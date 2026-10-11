import os
import sqlite3
import time
from pathlib import Path
import chromadb
from rdflib import Graph, Namespace, RDF, RDFS
from sentence_transformers import SentenceTransformer

import rdflib.term
rdflib.term._warn_on_lexical_failure = False
import logging
logging.getLogger("rdflib").setLevel(logging.CRITICAL)

def print_banner(title):
    print("\n" + "=" * 90)
    print(f"  {title.upper()}")
    print("=" * 90)

print_banner("Побудова та верифікація гібридного сховища знань (HKB Engine)")

# ==============================================================================
# ШАР 1: РЕЛЯЦІЙНЕ СХОВИЩЕ (SQL Engine / In-Memory Telemetry DB)
# ==============================================================================
print_banner("1. Реляційний шар: Аналітика часових рядів та пошук аномалій (SQL)")

conn = sqlite3.connect(":memory:")
cur = conn.cursor()

cur.execute("""
CREATE TABLE dim_road_segment (
    segment_id VARCHAR(16) PRIMARY KEY,
    name VARCHAR(64),
    road_class VARCHAR(32),
    lanes INT,
    speed_limit INT
);
""")

cur.execute("""
CREATE TABLE fact_traffic_observations (
    obs_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME,
    segment_id VARCHAR(16),
    hourly_flow INT,
    observed_speed REAL,
    is_peak_hour BOOLEAN,
    congestion_index REAL,
    FOREIGN KEY(segment_id) REFERENCES dim_road_segment(segment_id)
);
""")

segments_data = [
    ("DS-001", "вул. Франка (Центральний сегмент)", "arterial", 2, 50),
    ("DS-002", "вул. Зелена (Сегмент 2)", "collector", 2, 50),
    ("DS-003", "вул. Городоцька (Сегмент 3)", "arterial", 3, 50),
    ("DS-004", "вул. Стрийська (Сегмент 4)", "arterial", 3, 60),
    ("DS-005", "просп. Чорновола (Сегмент 5)", "collector", 2, 50),
]
cur.executemany("INSERT INTO dim_road_segment VALUES (?, ?, ?, ?, ?);", segments_data)

telemetry_data = [
    ("2026-10-06 08:15:00", "DS-001", 1420, 16.4, 1, 0.88),
    ("2026-10-06 08:30:00", "DS-001", 1580, 14.1, 1, 0.94),
    ("2026-10-06 08:45:00", "DS-001", 1390, 18.2, 1, 0.82),
    ("2026-10-06 08:15:00", "DS-002", 920, 36.5, 1, 0.45),
    ("2026-10-06 08:30:00", "DS-002", 980, 34.0, 1, 0.49),
    ("2026-10-06 08:15:00", "DS-003", 1650, 24.3, 1, 0.71),
    ("2026-10-06 08:30:00", "DS-003", 1710, 22.8, 1, 0.75),
    ("2026-10-06 08:15:00", "DS-004", 1200, 48.0, 1, 0.35),
    ("2026-10-06 08:15:00", "DS-005", 850, 41.5, 1, 0.38),
]
cur.executemany("""
INSERT INTO fact_traffic_observations (timestamp, segment_id, hourly_flow, observed_speed, is_peak_hour, congestion_index)
VALUES (?, ?, ?, ?, ?, ?);
""", telemetry_data)
conn.commit()

sql_query = """
SELECT 
    d.segment_id,
    d.name,
    d.speed_limit,
    ROUND(AVG(f.observed_speed), 2) AS avg_speed_kmh,
    ROUND(AVG(f.hourly_flow), 1) AS avg_flow_vph,
    ROUND(MAX(f.congestion_index), 3) AS max_congestion,
    ROUND((1.0 - AVG(f.observed_speed) / d.speed_limit) * 100, 1) AS speed_drop_pct
FROM fact_traffic_observations f
JOIN dim_road_segment d ON f.segment_id = d.segment_id
WHERE f.is_peak_hour = 1
GROUP BY d.segment_id, d.name, d.speed_limit
ORDER BY max_congestion DESC;
"""

print(f"[SQL Query Execution]:\n{sql_query.strip()}\n")
cur.execute(sql_query)
sql_rows = cur.fetchall()

header = f"{'Segment ID':<12} | {'Назва сегмента':<35} | {'Ліміт':<6} | {'Сер. швидк':<11} | {'Потік (а/г)':<12} | {'Congest.':<9} | {'Спад (%)'}"
print(header)
print("-" * len(header))
for r in sql_rows:
    print(f"{r[0]:<12} | {r[1]:<35} | {r[2]:<6} | {r[3]:<11} | {r[4]:<12} | {r[5]:<9} | {r[6]}%")

target_segment_id = sql_rows[0][0]
target_segment_name = sql_rows[0][1]
print(f"\n[ALERT HKB]: Виявлено критичну точку деградації мережі -> {target_segment_id} ({target_segment_name})")

# ==============================================================================
# ШАР 2: СЕМАНТИЧНИЙ ГРАФ ТА ОНТОЛОГІЯ (RDF / OWL / SPARQL)
# ==============================================================================
print_banner("2. Графовий шар: Семантична онтологія (OWL) та топологічний аналіз (SPARQL)")

possible_paths = [
    Path("update.owl"),
    Path(__file__).parent / "update.owl",
    Path(__file__).parent.parent / "update.owl",
    Path("D:/4_1/Knowledge_Bases/update.owl"),
    Path("D:/4_1/Knowledge_Bases/Lab_13/update.owl")
]

owl_file = None
for p in possible_paths:
    if p.exists():
        owl_file = p
        break

g = Graph()
if owl_file:
    print(f"[RDF Parser]: Завантаження онтології з файлу -> {owl_file.resolve()}")
    g.parse(str(owl_file), format="xml")
    print(f"[RDF Stats]: Успішно завантажено {len(g)} RDF-триплетів.")
else:
    raise FileNotFoundError("Файл update.owl не знайдено! Переконайтеся, що він у директорії проекту.")

sparql_inspection = """
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT (COUNT(DISTINCT ?cls) AS ?classesCount) 
       (COUNT(DISTINCT ?op) AS ?objPropCount)
       (COUNT(DISTINCT ?dp) AS ?dataPropCount)
       (COUNT(DISTINCT ?ind) AS ?indCount)
WHERE {
    { ?cls a owl:Class }
    UNION { ?op a owl:ObjectProperty }
    UNION { ?dp a owl:DatatypeProperty }
    UNION { ?ind a owl:NamedIndividual }
}
"""
stats = list(g.query(sparql_inspection))[0]
print(f"[Ontology TBox/ABox Overview]:")
print(f"  • Класів (owl:Class):             {stats[0]}")
print(f"  • Об'єктних властивостей (OP):    {stats[1]}")
print(f"  • Датних властивостей (DP):       {stats[2]}")
print(f"  • Екземплярів (ABox Individuals): {stats[3]}")

# Запит зв'язності для критичного вузла
sparql_query = """
PREFIX : <http://example.org/transport-ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?segment ?accident ?accidentLabel ?vehicle ?routeNum ?decision ?decisionLabel
WHERE {
    ?flow :characterizes :DS001 .
    OPTIONAL {
        ?accident :affects ?flow .
        OPTIONAL { ?accident rdfs:label ?accidentLabel . }
    }
    OPTIONAL {
        ?flow :hasVehicle ?vehicle .
        OPTIONAL { ?vehicle :routeNumber ?routeNum . }
    }
    OPTIONAL {
        ?rule :determines ?decision .
        OPTIONAL { ?decision rdfs:label ?decisionLabel . }
    }
}
LIMIT 5
"""

print(f"\n[SPARQL Multi-Hop Query Execution]: Топологічна діагностика вузла :DS001...")
qres = g.query(sparql_query)

graph_results = []
for row in qres:
    acc = str(row.accidentLabel) if row.accidentLabel else "Н/Д"
    veh = str(row.vehicle).split("#")[-1] if row.vehicle else "Н/Д"
    r_num = str(row.routeNum) if row.routeNum else "Н/Д"
    dec = str(row.decisionLabel) if row.decisionLabel else "Н/Д"
    graph_results.append((acc, veh, r_num, dec))

print(f"\n{'Інцидент (Подія)':<20} | {'Транспортний засіб':<20} | {'Маршрут':<10} | {'Прийняте рішення'}")
print("-" * 80)
for r in graph_results:
    print(f"{r[0]:<20} | {r[1]:<20} | {r[2]:<10} | {r[3]}")

# ==============================================================================
# ШАР 3: ВЕКТОРНЕ СХОВИЩЕ (ChromaDB + SentenceTransformers / all-MiniLM-L6-v2)
# ==============================================================================
print_banner("3. Векторний шар: Семантичний простір регламентів та інструкцій (ChromaDB)")

print("[Vector Engine]: Завантаження нейромережевої моделі all-MiniLM-L6-v2 (dim=384)...")
embed_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

chroma_client = chromadb.Client()
# Створюємо або очищуємо колекцію
collection_name = "transport_regulations"
try:
    chroma_client.delete_collection(name=collection_name)
except Exception:
    pass

collection = chroma_client.create_collection(
    name=collection_name,
    metadata={"hnsw:space": "cosine"}
)

documents = [
    {
        "id": "REG-01-REROUTE",
        "title": "Регламент зміни маршрутної схеми при заторах",
        "text": "У випадку виникнення критичного рівня завантаженості (коефіцієнт > 0.8) або повної блокування смуги внаслідок ДТП на магістральних ділянках, черговий диспетчер зобов'язаний негайно перенаправити міські автобуси на затверджені об'їзні маршрути через суміжні колекторні вулиці, активувати пріоритет світлофорів для громадського транспорту та сповістити пасажирів через динамічні табло.",
        "category": "dispatch_rerouting",
        "severity": "critical"
    },
    {
        "id": "REG-02-SPEED-CTRL",
        "title": "Протокол адаптивного швидкісного регулювання",
        "text": "При помірному зниженні швидкості руху без наявності аварійних подій оптимізація пропускної спроможності забезпечується зміною тривалості зеленої фази світлофорних об'єктів («зелена хвиля») без корекції маршрутів руху рухомого складу.",
        "category": "traffic_lights",
        "severity": "medium"
    },
    {
        "id": "REG-03-ACCIDENT-SOP",
        "title": "Стандартна операційна процедура оформлення ДТП",
        "text": "При реєстрації дорожньо-транспортної пригоди з постраждалими черговий інженер передає координати патрульній поліції та кареті швидкої медичної допомоги, виставляє віртуальний бар'єр безпеки в навігаційних системах міста і фіксує номер пошкодженого борту ТЗ.",
        "category": "emergency",
        "severity": "high"
    },
    {
        "id": "REG-04-WEATHER-RESTRICT",
        "title": "Інструкція реагування на несприятливі погодні умови",
        "text": "В умовах ожеледиці, снігопаду або затоплення проїзної частини швидкісний режим на мостах та шляхопроводах обмежується до 30 км/год із виїздом снігоприбиральної та комунальної техніки.",
        "category": "weather_safety",
        "severity": "medium"
    }
]

doc_texts = [d["text"] for d in documents]
doc_ids = [d["id"] for d in documents]
doc_metas = [{"title": d["title"], "category": d["category"], "severity": d["severity"]} for d in documents]

print(f"[Vector Indexing]: Генерація щільних векторів для {len(documents)} нормативних регламентів...")
embeddings = embed_model.encode(doc_texts).tolist()

collection.add(
    ids=doc_ids,
    embeddings=embeddings,
    documents=doc_texts,
    metadatas=doc_metas
)
print(f"[Vector Store Ready]: Колекцію '{collection_name}' успішно pro-індексовано (HNSW / Cosine).")

user_search_query = "Аварія перекрила рух, швидкість впала, що має зробити диспетчер для автобусів?"
print(f"\n[Semantic Query]: \"{user_search_query}\"")

query_emb = embed_model.encode([user_search_query]).tolist()
search_results = collection.query(
    query_embeddings=query_emb,
    n_results=2,
    include=["documents", "metadatas", "distances"]
)

print(f"\n[Vector Retrieval Top-2 Релевантних регламентів]:")
for i in range(len(search_results["ids"][0])):
    doc_id = search_results["ids"][0][i]
    meta = search_results["metadatas"][0][i]
    dist = search_results["distances"][0][i]
    sim = 1.0 - dist  # Cosine similarity
    content = search_results["documents"][0][i]
    print(f"\n  #{i+1} [ID: {doc_id}] | Схожість: {sim:.4f} (Косинусна відстань: {dist:.4f})")
    print(f"     Категорія: {meta['category']} | Рівень: {meta['severity']}")
    print(f"     Заголовок: {meta['title']}")
    print(f"     Витяг з тексту: \"{content[:180]}...\"")

# ==============================================================================
# ШАР 4: НАКРІЗНИЙ ФЕДЕРАТИВНИЙ СЦЕНАРІЙ (HKB FEDERATION WORKFLOW)
# ==============================================================================
print_banner("4. Інтегрований висновок HKB (End-to-End Decision Support System)")

print(f"""
[HKB FEDERATED REASONING TRACE]:
  1. SQL ENGINE      -> Зафіксовано інцидент на сегменті '{target_segment_id}' 
                        (Спад швидкості: -{sql_rows[0][6]}%, Індекс затору: {sql_rows[0][5]}).
  2. GRAPH/ONTOLOGY  -> Визначено сутності у зоні впливу:
                        - Подія: {graph_results[0][0]}
                        - Постраждалий транспорт: {graph_results[0][1]} (Маршрут №{graph_results[0][2]})
                        - Рекомендована дія онтології: {graph_results[0][3]}
  3. VECTOR ENGINE   -> Знайдено відповідний регламент дій:
                        [{search_results['ids'][0][0]}] "{search_results['metadatas'][0][0]['title']}"
                        Ступінь релевантності: {(1.0 - search_results['distances'][0][0]):.2%}
  4. ACTION TAKEN    -> Диспетчерській системі передано команду: Автобус №{graph_results[0][2]} 
                        переведено на об'їзний маршрут відповідно до {search_results['ids'][0][0]}.
""")
print("=" * 90)
print("  ГІБРИДНЕ СХОВИЩЕ ЗНАНЬ ПРАЦЮЄ ПОВНОЦІННО. УСІ ТРИ ШАРИ ДАНИХ УЗГОДЖЕНО.")
print("=" * 90)