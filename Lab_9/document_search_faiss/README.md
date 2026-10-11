# Document Search in FAISS Vector Database

Лабораторний проєкт з інформаційного пошуку для предметної області **«Цифрові моделі міських транспортних систем»**.

Проєкт відтворює типові сутності транспортної онтології `update.owl`: дорожні сегменти, автобусні маршрути, дорожні інциденти та сенсорну телеметрію. Якщо оригінальний `update.owl` доступний, його можна використовувати як семантичне джерело для подальшого розширення шаблонів; поточний репозиторій є повністю самодостатнім і не вимагає OWL-файла.

---

## 1. Мета лабораторної роботи

Побудувати та порівняти три стратегії щільного векторного пошуку:

1. **IndexFlatIP** — точний brute-force пошук.
2. **IndexHNSWFlat** — графовий approximate nearest-neighbor пошук.
3. **IndexIVFFlat** — inverted-file approximate пошук.

Додатково порівнюються:

- dense FAISS;
- BM25;
- hybrid search = dense + BM25 через Reciprocal Rank Fusion (RRF).

Корпус містить **560 українськомовних документів**, а набір evaluation queries містить **12 Competency Queries (KQ)** з явною binary relevance ground truth.

---

## 2. Архітектура

```text
                    ┌──────────────────────────┐
                    │ data_generator.py        │
                    │ 560 Ukrainian cards      │
                    │ 12 KQ + ground truth     │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────┐
                    │ sentence-transformers   │
                    │ multilingual MiniLM      │
                    │ L2 normalization         │
                    └────────────┬─────────────┘
                                 │
                  ┌──────────────┼──────────────┐
                  ▼              ▼              ▼
             FlatIP           HNSW            IVF
           exact search     ANN graph       inverted
                  │              │              │
                  └──────────────┼──────────────┘
                                 │
                    ┌────────────▼─────────────┐
                    │       evaluator.py       │
                    │ P@k / R@k / MRR@k        │
                    │ avg latency / p95        │
                    └────────────┬─────────────┘
                                 │
                 ┌───────────────┼────────────────┐
                 ▼               ▼                ▼
               Dense            BM25           Hybrid RRF
```

---

## 3. Математична основа

### 3.1 Cosine similarity та Inner Product

Для L2-нормалізованих векторів:

\[
\hat{x} = \frac{x}{||x||_2}, \qquad
\hat{y} = \frac{y}{||y||_2}
\]

тоді

\[
\hat{x}^{T}\hat{y} = \cos(x,y)
\]

Тому `IndexFlatIP` може використовувати Inner Product як точний еквівалент cosine similarity.

У проєкті нормалізація виконується через:

```python
faiss.normalize_L2(vectors)
```

### 3.2 Precision@k

\[
P@k = \frac{|Retrieved_k \cap Relevant|}{k}
\]

### 3.3 Recall@k

\[
R@k = \frac{|Retrieved_k \cap Relevant|}{|Relevant|}
\]

### 3.4 MRR@k

\[
MRR@k =
\begin{cases}
\frac{1}{rank_{first\ relevant}}, & \text{якщо релевантний документ знайдено}\\
0, & \text{інакше}
\end{cases}
\]

### 3.5 Reciprocal Rank Fusion

Для кожного документа:

\[
RRF(d) = \sum_{r \in R} \frac{1}{k_{RRF} + rank_r(d)}
\]

де в лабораторії:

\[
k_{RRF}=60
\]

Rank є 1-based. RRF не вимагає калібрування числових score між BM25 та cosine similarity.

---

## 4. Структура репозиторію

```text
document_search_faiss/
├── config.py
├── data_generator.py
├── indexer.py
├── search_engine.py
├── evaluator.py
├── main.py
├── requirements.txt
├── README.md
├── data/
│   ├── corpus.csv
│   └── queries.json
├── indexes/
│   ├── index_flat_ip.faiss
│   ├── index_hnsw_flat.faiss
│   ├── index_ivf_flat.faiss
│   └── index_metadata.json
├── outputs/
│   ├── evaluation_results.csv
│   ├── index_benchmark.csv
│   ├── latency_benchmark.csv
│   └── summary.md
└── tests/
    └── test_pipeline.py
```

`data/`, `indexes/` та `outputs/` створюються під час запуску і не повинні комітуватися до Git для великих реальних експериментів.

---

## 5. Встановлення

Рекомендовано Python 3.11.

### Linux/macOS

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Перший запуск завантажить multilingual SentenceTransformer-модель із Hugging Face. Для роботи без мережі модель потрібно попередньо закешувати.

---

## 6. Повний запуск

```bash
python main.py --rebuild
```

Прапорець `--rebuild`:

1. генерує 560 документів;
2. генерує 12 KQ;
3. будує embedding matrix;
4. створює три FAISS-індекси;
5. виконує HNSW sweep `efSearch = 16, 32, 64, 128`;
6. виконує IVF sweep `nprobe = 1, 2, 4, 8`;
7. оцінює `k = 5, 10`;
8. порівнює dense/BM25/hybrid;
9. вимірює average та p95 latency;
10. записує CSV і Markdown-звіт.

Для повторного аналізу вже збережених даних:

```bash
python main.py
```

---

## 7. Що саме вимірюється

### IndexFlatIP

Точний пошук по всіх векторах.

- не має параметра ANN tuning;
- використовується як retrieval baseline;
- його результати можна вважати ground-truth ranking для аналізу ANN recall, якщо потрібно розширити лабораторію.

### IndexHNSWFlat

Параметри:

- `M = 32`;
- `efConstruction = 64`;
- `efSearch ∈ {16, 32, 64, 128}`.

Зі збільшенням `efSearch` зазвичай зростає кількість кандидатів, а отже може зростати latency та якість ANN retrieval. Конкретний результат потрібно встановити експериментально на вашому середовищі.

### IndexIVFFlat

Параметр побудови:

- `nlist = 16`.

Sweep:

- `nprobe ∈ {1, 2, 4, 8}`.

`nprobe` визначає кількість inverted lists, які перевіряються під час пошуку.

---

## 8. BM25 та Hybrid

BM25 реалізовано через `rank-bm25`.

Для українського корпусу використовується детермінований regex tokenizer. Це навмисно просте рішення для лабораторної: воно не вимагає зовнішнього морфологічного аналізатора та робить experiment reproducible.

Hybrid:

```text
query
 ├── dense FAISS ──┐
 │                 ├── RRF(k=60) ── final ranking
 └── BM25 ─────────┘
```

Важливо: RRF комбінує **ранги**, а не сирі score. Тому cosine similarity та BM25 не потрібно штучно приводити до однієї шкали.

---

## 9. Ground truth

Ground truth не генерується самим FAISS або embedding model.

Кожен документ має структуровані атрибути:

- тип сутності;
- місто;
- дорога;
- довжина;
- кількість смуг;
- speed limit;
- congestion;
- номер маршруту;
- кількість зупинок;
- інтервал;
- тип/тяжкість інциденту;
- падіння швидкості;
- кількість транспортних засобів;
- timestamp.

Для кожної KQ задано явне predicate rule. Наприклад:

```text
KQ01:
road_segment AND congestion == "критичний"
AND speed_limit <= 40
```

Це дає контрольовану binary relevance annotation:

```json
{
  "query_id": "KQ01",
  "query": "...",
  "relevant_doc_ids": ["D....", "..."],
  "relevant_count": 10
}
```

Усі 12 KQ мають щонайменше 3 релевантні документи; генератор перевіряє це під час виконання.

---

## 10. Результати

### `outputs/index_benchmark.csv`

Містить:

- index name;
- FAISS path;
- build time;
- file size in bytes;
- embedding dimension;
- number of vectors.

### `outputs/evaluation_results.csv`

Містить query-level evaluation:

- method;
- index;
- parameter;
- query ID;
- k;
- Precision@k;
- Recall@k;
- MRR@k.

### `outputs/latency_benchmark.csv`

Містить:

- method;
- index;
- parameter;
- k;
- average latency;
- p95 latency;
- number of timing samples.

### `outputs/summary.md`

Містить агреговані таблиці, придатні для включення в лабораторний звіт.

---

## 11. Як інтерпретувати результати

Для академічного звіту варто розглянути окремо:

1. **Якість:** Precision@5, Recall@5, MRR@5.
2. **Глибину видачі:** Precision@10, Recall@10, MRR@10.
3. **Latency:** average та p95.
4. **Index footprint:** розмір `.faiss` файла.
5. **ANN trade-off:** як змінюється якість/latency HNSW при збільшенні `efSearch`.
6. **IVF trade-off:** як змінюється якість/latency при збільшенні `nprobe`.
7. **Hybrid effect:** чи доповнює lexical retrieval dense retrieval на KQ, де важливі конкретні числові або entity terms.

Не слід порівнювати лише середній latency: p95 показує хвіст розподілу часу відповіді.

---

## 12. Тести

Запустити:

```bash
pytest -q
```

Тести навмисно не завантажують SentenceTransformer. Вони перевіряють:

- кількість документів;
- дедуплікацію;
- мінімальну кількість ground-truth релевантних документів;
- метрики;
- tokenizer;
- RRF;
- створення/пошук FAISS на маленькому synthetic vector matrix.

---

## 13. Reproducibility

Генератор використовує:

```text
RANDOM_SEED = 42
```

Тому за однакового Python/package environment synthetic corpus та ground truth будуть стабільними.

Для повної наукової відтворюваності також зафіксуйте:

- OS;
- Python version;
- CPU;
- RAM;
- FAISS version;
- PyTorch version;
- SentenceTransformers version;
- кількість потоків BLAS/OpenMP;
- час запуску.

Для benchmark latency бажано виконувати експерименти на незавантаженій системі та не запускати паралельно інші CPU-heavy jobs.

---

## 14. Обмеження

Це синтетичний корпус, а не реальні транспортні дані. Тому:

- метрики відображають поведінку retrieval pipeline на контрольованій задачі;
- вони не є оцінкою якості системи на production traffic data;
- ground truth визначено правилами генератора;
- tokenizer не виконує повноцінну українську лематизацію;
- результати latency залежать від hardware та runtime environment.

Для наступної версії лабораторії можна додати:

- справжній `update.owl` через `rdflib`;
- ontology-aware query expansion;
- українську лематизацію;
- cross-encoder reranking;
- ANN recall@k відносно IndexFlatIP;
- statistical confidence intervals;
- repeated benchmark runs із confidence intervals;
- Dockerfile та CI.

---

## 15. Академічна структура звіту

Рекомендована структура:

1. **Мета роботи**
2. **Опис предметної області**
3. **Побудова синтетичного корпусу**
4. **Dense representation**
5. **L2 normalization та cosine similarity**
6. **FAISS indexes**
7. **HNSW / IVF hyperparameter sweep**
8. **BM25**
9. **Hybrid RRF**
10. **Evaluation methodology**
11. **Experimental results**
12. **Latency and storage analysis**
13. **Discussion of trade-offs**
14. **Conclusions**

У висновках розділяйте спостережені експериментальні факти від загальних властивостей алгоритмів.
