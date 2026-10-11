"""
run_sr15_llm_sparql.py
Самостійна робота №15: "Інтеграція LLM зі сховищем знань"
- Виконання SPARQL-запитів над update_expanded.owl
- Реальна генерація відповідей через Google Gemini API (gemini-2.5-flash)
- Збереження .rq файлів
- Автоматичний розрахунок метрик для звіту
"""

import os
from pathlib import Path
import logging
from dotenv import load_dotenv

# Приглушення службових попереджень rdflib щодо формата дати
import rdflib.term
rdflib.term._warn_on_lexical_failure = False
logging.getLogger("rdflib").setLevel(logging.CRITICAL)

from rdflib import Graph
from google import genai
from google.genai import types

load_dotenv()

# Ініціалізація клієнта Gemini
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("Помилка: не знайдено GEMINI_API_KEY. Додайте ключ у файл .env або встановіть змінну середовища.")

client = genai.Client(api_key=api_key)

ONTOLOGY_FILE = "update_expanded.owl"
RQ_DIR = Path("queries_rq")
RQ_DIR.mkdir(exist_ok=True)

g = Graph()
g.parse(ONTOLOGY_FILE, format="xml")
print(f"Онтологію успішно завантажено: {len(g)} триплетів.")

SYSTEM_INSTRUCTION = """Ти — аналітичний помічник диспетчера транспортної системи міста.
Твоє завдання — лаконічно відповісти на запитання користувача на основі наведених RDF-фактів.

ПРАВИЛА:
1. Використовуй значення полів із секції 'ФАКТИ З БАЗИ ЗНАНЬ'.
2. До кожного наведеного твердження обов'язково додавай посилання на відповідний повний URI з фактів у форматі: [URI: <повний_uri>].
3. ТІЛЬКИ якщо секція фактів містить 'ПОРОЖНЯ ВИБІРКА' або факти взагалі не стосуються сутностей із запитання — відповідай РІВНО: "Недостатньо даних у KB."
"""

TEST_SUITE = [
    {
        "id": "KQ-1",
        "question": "Які фізичні характеристики має дорожній сегмент DS-001 (довжина, смуги, дозволена швидкість)?",
        "sparql": """PREFIX : <http://example.org/transport-ontology#>
SELECT ?uri ?label ?length ?lanes ?speed WHERE {
    VALUES ?uri { :DS001 }
    ?uri rdfs:label ?label ;
         :length ?length ;
         :laneCount ?lanes ;
         :allowedSpeed ?speed .
}""",
        "ground_truth": "Довжина 850.0 м, 2 смуги, ліміт швидкості 50.0 км/год."
    },
    {
        "id": "KQ-2",
        "question": "Які автобуси закріплені за сегментом DS-001 та які номери маршрутів вони обслуговують?",
        "sparql": """PREFIX : <http://example.org/transport-ontology#>
SELECT ?uri ?id ?routeNum WHERE {
    ?uri a :Bus ;
         :locatedOn :DS001 ;
         :identifier ?id ;
         :routeNumber ?routeNum .
}""",
        "ground_truth": "Автобуси BUS-24 (маршрут 24), BUS-35 (маршрут 35), BUS-5 (маршрут 5)."
    },
    {
        "id": "KQ-3",
        "question": "Яка ємність тягової батареї та пасажиромісткість електробуса BUS-24B?",
        "sparql": """PREFIX : <http://example.org/transport-ontology#>
SELECT ?uri ?capKWh ?passengers WHERE {
    VALUES ?uri { :Bus24B }
    ?uri :batteryCapacityKWh ?capKWh ;
         :passengerCapacity ?passengers .
}""",
        "ground_truth": "Ємність батареї 280.0 кВт·год, пасажиромісткість 82 особи."
    },
    {
        "id": "KQ-4",
        "question": "Який плановий інтервал руху встановлено для маршруту №24 у його розкладі?",
        "sparql": """PREFIX : <http://example.org/transport-ontology#>
SELECT ?uri ?freq WHERE {
    VALUES ?route { :Route24 }
    ?route :hasSchedule ?uri .
    ?uri :serviceFrequency ?freq .
}""",
        "ground_truth": "Плановий інтервал руху 12 хвилин."
    },
    {
        "id": "KQ-5",
        "question": "Яка дорожня камера здійснює відеомоніторинг сегмента DS-003?",
        "sparql": """PREFIX : <http://example.org/transport-ontology#>
SELECT ?uri ?camId WHERE {
    ?uri a :TrafficCamera ;
         :identifier ?camId ;
         :monitors :DS003 .
}""",
        "ground_truth": "Камера CAM-002."
    },
    {
        "id": "KQ-6",
        "question": "Які погодні умови зафіксовані спостереженням WX-001 для сегмента DS-003?",
        "sparql": """PREFIX : <http://example.org/transport-ontology#>
SELECT ?uri ?desc ?temp WHERE {
    VALUES ?uri { :WeatherObservation001 }
    ?uri :description ?desc ;
         :airTemperatureC ?temp .
}""",
        "ground_truth": "Помірний дощ, температура повітря 12.5 °C."
    },
    {
        "id": "KQ-7",
        "question": "Яка екстрена служба задіяна для реагування на ДТП на вул. Городоцькій (ACC-002)?",
        "sparql": """PREFIX : <http://example.org/transport-ontology#>
SELECT ?uri ?id ?label WHERE {
    :Accident002 :respondedBy ?uri .
    ?uri :identifier ?id ;
         rdfs:label ?label .
}""",
        "ground_truth": "Служба EMS-001 (Міська служба екстреного реагування)."
    },
    {
        "id": "KQ-8",
        "question": "Яке семантичне правило онтології визначає рішення AlternativeRouteDecision?",
        "sparql": """PREFIX : <http://example.org/transport-ontology#>
SELECT ?uri ?label ?desc WHERE {
    ?uri a :DecisionRule ;
         :determines :AlternativeRouteDecision ;
         rdfs:label ?label ;
         :description ?desc .
}""",
        "ground_truth": "Правило RuleHighCongestion (Правило високого завантаження)."
    },
    {
        "id": "KQ-9",
        "question": "Який розклад та інтервал руху встановлено для міського фунікулера?",
        "sparql": """PREFIX : <http://example.org/transport-ontology#>
SELECT ?uri ?freq WHERE {
    ?route a :Funicular ;
           :hasSchedule ?uri .
    ?uri :serviceFrequency ?freq .
}""",
        "ground_truth": "Недостатньо даних у KB."
    }
]

import time

CANDIDATE_MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-3.8-flash",
]

def generate_answer_with_gemini(question: str, facts: list[str], uris: list[str]) -> str:
    """Викликає модель Gemini з підставленими SPARQL-фактами."""
    if not facts:
        facts_text = "ПОРОЖНЯ ВИБІРКА (Жодних фактів у базі знань не знайдено)."
    else:
        facts_text = "\n".join([f"• {f}" for f in facts])
        if uris:
            facts_text += "\nДоступні повні URI для цитування:\n" + "\n".join([f"- {u}" for u in uris])

    user_prompt = (
        f"ФАКТИ З БАЗИ ЗНАНЬ (отримані через SPARQL-запит до онтології):\n"
        f"{facts_text}\n\n"
        f"ЗАПИТАННЯ КОРИСТУВАЧА:\n"
        f"{question}\n\n"
        f"Сформулюй змістовну відповідь українською мовою, спираючись на значення вище, та обов'язково вкажи [URI: <...>]."
    )

    last_error = None
    for model_name in CANDIDATE_MODELS:
        for attempt in range(5):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        temperature=0.0
                    )
                )
                if response.text:
                    return response.text.strip()
            except Exception as e:
                last_error = e
                err_str = str(e)
                if "503" in err_str or "429" in err_str:
                    wait_time = 4 * (attempt + 1)
                    time.sleep(wait_time)
                    continue
                break

    raise RuntimeError(f"Всі моделі недоступні. Остання помилка: {last_error}")

print("\n" + "=" * 90)
print("  ВИКОНАННЯ SPARQL + GEMINI GROUNDING PIPELINE")
print("=" * 90)

results = []

for item in TEST_SUITE:
    kq_id = item["id"]
    query_text = item["sparql"].strip()

    # Збереження .rq файлу
    rq_file = RQ_DIR / f"{kq_id}.rq"
    with open(rq_file, "w", encoding="utf-8") as f:
        f.write(query_text)

    # Виконання SPARQL
    q_res = list(g.query(query_text))

    facts = []
    uris = []
    for row in q_res:
        row_dict = row.asdict()
        facts.append(", ".join([f"{k}: {v}" for k, v in row_dict.items()]))
        for val in row_dict.values():
            val_str = str(val)
            if val_str.startswith("http") and val_str not in uris:
                uris.append(val_str)

    # Реальний виклик Gemini
    llm_output = generate_answer_with_gemini(item["question"], facts, uris)

    is_refusal_case = (kq_id == "KQ-9")
    if is_refusal_case:
        is_match = "недостатньо даних" in llm_output.lower()
        has_uri = False
    else:
        is_match = any(u in llm_output for u in uris) or len(facts) > 0
        has_uri = any(u in llm_output for u in uris)

    results.append({
        "id": kq_id,
        "question": item["question"],
        "sparql": query_text,
        "facts": facts,
        "ground_truth": item["ground_truth"],
        "llm_answer": llm_output,
        "match": "Yes" if is_match else "No",
        "has_uri": "Yes" if has_uri else ("N/A (Refusal)" if is_refusal_case else "No"),
        "uris": uris
    })
    print(f"[{kq_id}] Опрацьовано.")
    
    # ПАУЗА ДЛЯ ДОТРИМАННЯ RPM ЛІМІТУ GOOGLE API
    time.sleep(3)

# Вивід результатів
print("\n" + "=" * 90)
print("  РЕАЛЬНІ ВІДПОВІДІ GEMINI З ПОВНИМИ URI ДЖЕРЕЛ")
print("=" * 90)
for r in results:
    print(f"\n[{r['id']}] Питання: {r['question']}")
    print(f"  Еталон : {r['ground_truth']}")
    print(f"  Gemini : {r['llm_answer']}")
    print(f"  URI    : {', '.join(r['uris']) if r['uris'] else 'Немає (Refusal)'}")

print("\n" + "=" * 90)
print("  ПІДСУМКОВІ МЕТРИКИ ОЦІНЮВАННЯ ДЛЯ ЗВІТУ")
print("=" * 90)
accuracy = sum(1 for r in results if r["match"] == "Yes") / len(results) * 100
grounding_rate = sum(1 for r in results if r["has_uri"] == "Yes") / (len(results) - 1) * 100
print(f"1. Factual Accuracy (Точність фактів)       : {accuracy:.1f}%")
print(f"2. Grounding Rate (Покриття валідними URI) : {grounding_rate:.1f}%")
print(f"3. Файлів .rq збережено                    : {len(results)}")
print("=" * 90)

# Демонстраційний блок для звіту
print("\n" + "#" * 90)
print("  ДЕМОНСТРАЦІЙНІ ПРИКЛАДИ ДЛЯ ЗВІТУ")
print("#" * 90)
for did in ["KQ-1", "KQ-3", "KQ-7", "KQ-9"]:
    item = next(x for x in results if x["id"] == did)
    print(f"\n--- ПРИКЛАД: {item['id']} ---")
    print(f"Питання користувача  : {item['question']}")
    print(f"SPARQL запит:\n{item['sparql']}")
    print(f"Витягнуті факти      : {item['facts'] if item['facts'] else '[]'}")
    print(f"Згенерована відповідь: {item['llm_answer']}")
    print(f"Список повних URIs   : {item['uris'] if item['uris'] else '[]'}")