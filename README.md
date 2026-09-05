# RAG Drift Detector

**Catch retrieval quality degradation in your RAG system before your users do.**

Most RAG systems are evaluated once, at build time, and never again. Then the
corpus grows, documents get re-chunked, someone swaps the embedding model, the
index goes stale — and retrieval quality decays *silently*. Nothing errors. The
LLM keeps producing fluent answers, just with worse context behind them. By the
time anyone notices, it has been broken for weeks.

RAG Drift Detector is a small, self-hostable, open-source tool that watches one
thing well: **is retrieval still returning the documents it used to?**

It is not an LLM observability platform. There is no tracing, no token
accounting, no per-span waterfall. It scores a golden set against your vector
index on a schedule, tracks the metrics over time, decides *statistically*
whether a drop is a real regression or normal noise, and tells you in plain
English what most likely caused it.

---

## Status

Built in stages, each one working end to end before the next begins.

| Stage | Scope | Status |
| ----- | ------------------------------------------- | ------ |
| 1 | Golden eval set + scoring engine | ✅ Done |
| 2 | Historical tracking (SQLite) + REST API | ✅ Done |
| 3 | Statistical drift detection | ✅ Done |
| 4 | Root-cause diagnostics rule engine | ✅ Done |
| 5 | React + TypeScript dashboard | ✅ Done |
| 6 | Docker packaging + full documentation | ✅ Done |

---

## What it looks like

<p align="center">
  <img src="docs/screenshots/dashboard.png" alt="Dashboard showing a detected regression, health status and headline metrics" width="100%">
</p>

The dashboard answers one question first — *is retrieval still working?* — and
backs the answer with the interval and p-value that produced it.

<table>
<tr>
<td width="50%"><img src="docs/screenshots/trends.png" alt="Metric trends with regressions marked on the line"></td>
<td width="50%"><img src="docs/screenshots/dashboard-dark.png" alt="Dashboard in dark mode"></td>
</tr>
<tr>
<td><b>Trends.</b> Four metrics over time. Detected regressions are marked in
place, and each marker links to the assessment that produced it.</td>
<td><b>Dark mode.</b> A separate palette, not an inversion — surfaces keep a
blue cast and borders carry the elevation shadows cannot show.</td>
</tr>
</table>

<p align="center">
  <img src="docs/screenshots/drift-events.png" alt="A drift event expanded, showing the statistical comparison table and, separately, the heuristic root-cause diagnostics" width="100%">
</p>

A drift event, expanded. The **statistical assessment** — every metric with its
confidence interval, its adjusted p-value and the method footnote — and then,
visually separate and explicitly labelled, the **heuristic diagnostics**.
Keeping those two apart is the point; see
[the framing boundary](#root-cause-diagnostics--and-why-they-are-framed-differently).

The screenshots are generated from a live instance by
`frontend/scripts/screenshots.mjs`, so they cannot quietly drift out of date.


---

## Architecture

```mermaid
flowchart LR
    GS["Golden set<br/>(JSON / CSV)"] --> SE
    VS[("Vector store<br/>Chroma")] <--> CN["VectorStoreConnector<br/>(pluggable ABC)"]
    CN --> SE["Scoring engine"]
    SE --> M["Recall@k · Precision@k<br/>MRR · NDCG@k"]
    M --> DB[("SQLite<br/>run history")]
    DB --> DD["Drift detector<br/>(bootstrap CI)"]
    DD --> RC["Root-cause<br/>rule engine"]
    DB --> API["FastAPI"]
    DD --> API
    RC --> API
    API --> UI["React dashboard"]
```

The dependency direction is the point: the scoring engine depends on the
`VectorStoreConnector` abstraction and the pure metric functions, never on
Chroma. Adding Qdrant or pgvector is one new module and a registry entry — no
change to metrics, drift detection, or the API.

```
backend/
├── app/
│   ├── domain/          value objects (golden set, retrieval, metrics, history)
│   ├── connectors/      VectorStoreConnector ABC + registry + Chroma impl
│   ├── embeddings/      EmbeddingProvider ABC + registry + offline hashing impl
│   ├── db/              SQLAlchemy models, sessions, Alembic helpers
│   ├── repositories/    SQL lives here; returns domain objects, never ORM rows
│   ├── services/        business logic (scoring, golden sets, runs, bootstrap)
│   ├── api/             FastAPI app, routers, schemas, error mapping
│   ├── core/            config, logging, errors, composition root
│   └── cli.py           thin adapter over the services
└── alembic/versions/    migrations — the single source of truth for the schema
```

Layering is enforced by direction of imports: `api → services → repositories →
db`, with `domain` depended on by everything and depending on nothing. No route
handler touches a repository; no repository knows what HTTP is.

---

## Quickstart

### With Docker (recommended)

```bash
git clone https://github.com/zainabraza06/RAG_Drift_detector.git
cd RAG_Drift_detector
docker compose up --build
```

Then open **http://localhost:8080**.

On a fresh volume the backend migrates its schema, indexes the bundled demo
corpus into Chroma and imports the demo golden set, so the dashboard has
something to show the moment it loads. Every step is idempotent, so restarts
are safe. Click **Run evaluation** twice — the second run is the first one that
has a baseline to compare against.

nginx serves the built UI and proxies `/api` to the backend on the same origin,
so CORS is not part of the production path at all. Copy `.env.example` to
`.env` to change the port, the cutoffs, or to start empty against your own
corpus with `DRIFT_BOOTSTRAP_DEMO=false`.

To populate a history worth looking at — ten runs across twelve days, with a
deliberate regression part way through:

```bash
docker compose exec backend python -m scripts.seed_demo_history --reset
```

### From source

Requires Python 3.11+ and Node 20+.

```bash
cd backend
python -m venv .venv
. .venv/Scripts/activate      # Windows;  source .venv/bin/activate on Unix
pip install -r requirements-dev.txt

python -m app.cli seed        # index the bundled demo corpus into Chroma
python -m app.cli evaluate -v # score the golden set and record the run
python -m app.cli serve       # start the API on http://127.0.0.1:8000
```

The first database-touching command migrates the schema and imports the demo
golden set automatically, so there is no separate init step.

Output:

```
Golden set : acme-cloud-support v1 (ac6007e1dbb45cb2)
Store      : chroma/drift_demo - 32 documents
Embeddings : hashing-v1-d384
Queries    : 30   Duration: 2282 ms

  k   Recall@k   Precision@k      MRR    NDCG@k
-----------------------------------------------
  1     0.8667        0.9333   0.9333    0.9333
  3     0.9000        0.3222   0.9500    0.9433
  5     0.9333        0.2067   0.9583    0.9582 *
 10     0.9833        0.1133   0.9583    0.9622

* primary cutoff (k=5) - the one drift detection tests
```

Other commands:

```bash
python -m app.cli info                     # resolved config + index status
python -m app.cli history                  # recorded runs, newest first
python -m app.cli db status                # current vs head schema revision
python -m app.cli import-golden-set FILE   # store a JSON/CSV set in the database
python -m app.cli golden-set --check-index # validate a golden set against the index
python -m app.cli evaluate --no-save       # score without recording history
```

Everything is configurable through `DRIFT_`-prefixed environment variables (see
`backend/app/core/config.py`), e.g. `DRIFT_CHROMA_COLLECTION`,
`DRIFT_EVAL_K_VALUES=1,5,20`, `DRIFT_EVAL_PRIMARY_K=5`.

---

## REST API

`python -m app.cli serve` — interactive docs at `/docs`, OpenAPI at
`/openapi.json`.

| Method | Path | Purpose |
| ------ | ------------------------------ | ---------------------------------- |
| GET | `/api/health` | Liveness; 503 if the DB or vector store is down |
| GET | `/api/system/info` | Resolved config, schema revision, index status |
| GET | `/api/dashboard` | Everything the home screen needs, in one request |
| POST | `/api/runs` | **Run an evaluation now** |
| GET | `/api/runs` | Paginated history, newest first |
| GET | `/api/runs/latest` | Most recent run, or `null` |
| GET | `/api/runs/{id}` | One run's aggregate metrics |
| GET | `/api/runs/{id}/queries` | Per-query breakdown at the primary cutoff |
| DELETE | `/api/runs/{id}` | Delete a run |
| GET | `/api/metrics/trends?k=5` | All four metrics over time, one request |
| GET | `/api/metrics/series?metric=&k=` | One metric over time |
| GET | `/api/metrics/cutoffs` | Cutoffs that actually have data |
| GET | `/api/runs/{id}/drift` | Statistical drift assessment for a run |
| GET | `/api/drift/events` | Past assessments, filterable by verdict |
| GET | `/api/drift/latest` | Most recent assessment |
| GET | `/api/runs/{id}/diagnostics` | Heuristic root-cause report for a regression |
| GET/POST | `/api/golden-sets` | List / create |
| PUT | `/api/golden-sets/{id}` | Replace judgements |
| POST | `/api/golden-sets/{id}/activate` | Choose the set runs use by default |
| POST | `/api/golden-sets/import` | Import a JSON/CSV file |

Every error shares one envelope:

```json
{ "error": { "code": "run_not_found", "message": "run 'abc' not found" } }
```

Clients branch on `code`; `message` wording is free to change.

---

## Running it

```bash
docker compose up --build
open http://localhost:8080
```

That is the whole quickstart. On a fresh volume the backend migrates the
schema, indexes the bundled demo corpus into Chroma and imports the demo
golden set, so the dashboard has something real to show on first load. Every
step is idempotent, so restarts are safe.

Three services: **nginx** serving the built SPA and proxying `/api`,
**FastAPI** holding the run history in SQLite, and **Chroma** as the vector
store. The API is not published — nginx is the only thing that needs to reach
it, and exposing it would give the UI two different origins and drag CORS into
the production path for no reason.

### Why Chroma runs as a server

This is a correctness requirement rather than a deployment preference, and it
is the single most important thing in the compose file.

`chromadb`'s `PersistentClient` caches a collection's vector segment in memory
for the life of the process and does not observe another process's writes.
Reopening the client does not help — the underlying `System` is cached per
path. A drift detector reads an index that some *other* pipeline writes, so an
embedded client would keep scoring the index as it looked when the API booted
and would **never notice the change it exists to detect**. A server is the
single owner of the index; every writer and reader goes through it.

### Giving the demo a history worth looking at

One run is not a trend, and drift detection needs a baseline:

```bash
docker compose exec backend python -m scripts.seed_demo_history --reset
```

This runs *real* evaluations against the *real* index and deliberately deletes
six expected documents part way through, producing a genuine regression with
genuine intervals and diagnostics. The only thing simulated is *when* the runs
happened — they are stamped across the past twelve days so the trend charts
have a readable axis instead of a dozen points inside one minute.

### Configuration

Copy `.env.example` to `.env` to override defaults. Set
`DRIFT_BOOTSTRAP_DEMO=false` to start empty against your own corpus, which is
what a real deployment wants.

---

## Dashboard

```bash
cd backend && python -m app.cli serve     # API on :8000
cd frontend && npm install && npm run dev # UI on :5173, proxying /api
```

Four views: **Dashboard** (health, headline metrics, run action), **Trends**
(four charts with regressions marked in place), **Drift events** (expandable
timeline with full statistical reasoning), **Golden set** (validated editor).

React 18 + TypeScript strict + Tailwind + Recharts, with dark mode, a
responsive shell, and route-level code splitting that keeps the initial bundle
at ~89 kB gzipped by deferring Recharts to the trends route.

### The framing boundary is enforced in the UI too

The care taken in Stages 3 and 4 would be wasted if the interface flattened it
back out, so the two halves are kept visually and structurally apart:

* The statistical verdict and the heuristic diagnostics are **separate
  components** in separate sections, never one merged list.
* The diagnostics panel's *"these are heuristics, not statistical findings"*
  notice sits **above** the findings. A disclaimer below the conclusions is
  read after they have already landed. There is a test asserting the document
  order.
* Evidence strength renders as a **word** — `Direct`, `Circumstantial`,
  `Context` — never a bar or a percentage. A test fails if a `progressbar` or
  a "% confident" string ever appears in the rendered tree, because that is
  precisely how a numeric confidence would sneak back in.
* A finding that cannot honestly count queries shows **no** coverage figure
  rather than a fabricated one.
* "Ruled out" and "could not check" stay visually distinct.

### Other decisions worth noting

**"Unknown" is not green.** A system never compared against a baseline is not
*known* to be healthy, so the traffic light shows grey, matching the backend.

**Significance and materiality are shown separately.** A change can be
statistically real and operationally irrelevant; a UI that merged them into one
badge would hide the distinction the detector is careful to make.

**Deltas are in points, not percent.** "Recall fell 4.2%" is ambiguous between
an absolute and a relative change.

**Chart axes are padded, not pinned to [0, 1].** Retrieval metrics sit in a
narrow band near the top, and a full-range axis flattens exactly the movement
this tool exists to surface — but the axis never exceeds [0, 1], so a shape
cannot read as more dramatic than it is.

**Every state is designed.** Skeletons mirror the shape of what they replace so
the layout does not jump; empty states say what to do next; error states use
the API's error `code` to say something specific and offer retry only when
retrying could help.

---

## How drift detection works

This is the part of the project worth reading closely. "Retrieval got worse"
is easy to assert and hard to justify: metrics move between runs for reasons
that have nothing to do with the system, and a threshold like *"alert if
recall drops 5%"* fires on noise and misses real regressions in equal measure.

### The comparison is paired, because the runs are not independent

Two runs are only ever compared when they were scored against the **same
golden set fingerprint**. That means query *i* appears in both runs, and the
runs are not independent samples — an intrinsically hard query drags both down
together.

So the statistic is the **mean paired difference**. For per-query scores `b`
(baseline) and `c` (current), over `n` queries:

```
d_i  = c_i − b_i                        per-query paired difference
θ̂    = mean(d)                          the observed change
θ*_r = mean(d[I_r]),   I_r ~ Uniform{1..n} with replacement, |I_r| = n
```

Each bootstrap resample draws **query indices**, and for each drawn index takes
*both* runs' scores. Between-query difficulty cancels inside every difference.
Resampling the two runs independently would carry that difficulty variance —
usually far larger than the effect being measured — into the estimate twice.

The difference is not subtle. On 40 queries with difficulty spread across
[0, 1] and a true shift of −0.05 applied to every query:

| | 95% interval | width |
| -------- | ------------------ | ----- |
| paired | [−0.0500, −0.0500] | 0.000 |
| unpaired | [−0.1112, +0.0513] | 0.163 |

The unpaired interval contains zero and detects nothing. There is a test that
pins this (`test_pairing_cancels_between_query_difficulty`).

### The interval and the p-value come from different resamples

Conflating these is the most common way to get bootstrap inference quietly
wrong.

* The **interval** is read off the uncentred resamples `θ*`, whose
  distribution is centred near `θ̂`. It answers *how precisely do we know the
  change?*
* The **p-value** needs a distribution generated under `H₀: E[d] = 0`. The
  uncentred distribution is not that, so the differences are re-centred
  (`d_i − θ̂`) before resampling and `θ̂` is compared against the result. The
  estimate uses the `(1 + #extreme) / (R + 1)` form, which is standard, is
  unbiased, and cannot report the impossible `p = 0` — with R = 10,000 the
  floor is 1/10,001.

Intervals are **BCa** (bias-corrected and accelerated) by default rather than
plain percentile, because metrics are bounded in [0, 1] and pile up against
those bounds, which skews the bootstrap distribution. When the correction is
undefined — every query moved by exactly the same amount, so the distribution
is a point mass — it falls back to the percentile interval rather than
inventing one.

### What the interval actually means

> If this whole procedure were repeated many times on fresh samples of
> queries, about 95% of the intervals it produced would contain the true mean
> paired difference.

It is **not** "a 95% probability the true change is in this interval" — the
true change is fixed, the interval is what varies.

And the resampling is over **queries**, so the interval quantifies uncertainty
about *which queries happen to be in the golden set*. It treats the retrieval
system as fixed. It does not cover a non-deterministic index, embedding
non-determinism, or the golden set being unrepresentative of real user
traffic. The inference is about the population of queries the golden set can
be regarded as a sample from, and no wider.

### Coverage is verified, not assumed

A "95% interval" is a claim that has to be earned. Measured coverage of the
true effect under the null, over 1,500 simulated trials per cell:

| queries | BCa | percentile |
| ------- | ----- | ---------- |
| 10 | 0.883 | 0.889 |
| 20 | 0.915 | 0.921 |
| 30 | 0.941 | 0.939 |
| 60 | 0.935 | 0.935 |
| 120 | 0.953 | 0.952 |
| 400 | 0.950 | 0.949 |

Coverage reaches nominal from roughly 30 queries and is **anti-conservative
below that** — at 10 queries a "95%" interval really covers about 88%. This is
the expected finite-sample behaviour of the bootstrap, and it is why the
detector refuses to return a verdict below `min_queries` (default 15) and
attaches an explicit warning below 30 rather than quietly reporting an
interval it cannot back up.

### One pre-specified primary metric

The verdict is decided on a **single metric chosen in advance** (NDCG@k by
default, because it responds both to losing a document and to merely ranking
it lower). The other three are reported as supporting context.

This is the correct response to multiplicity, not an evasion of it. The four
metrics are deterministic functions of the *same* ranked lists, so they move
together almost perfectly — when a document drops out of the index, Recall,
MRR and NDCG all fall for the same queries. Applying a 4× Holm-Bonferroni
penalty across them buys almost no error control and costs most of the power.

That is not hypothetical. Deleting 4 expected documents from the demo index
produces:

```
recall_at_k      diff=-0.1167  CI=[-0.3000,-0.0500]  p_holm×4=0.1336   not significant
```

An 11.7-point recall drop whose confidence interval **excludes zero outright**,
reported as "stable" — purely because three metrics that are near-copies of it
were counted as independent hypotheses. Testing one pre-specified endpoint at
full alpha (as a clinical trial does with its primary outcome) gives
`p = 0.0436` on NDCG@5 and the correct `degraded` verdict, while Holm still
applies to the supporting family where it belongs.

### Significant and material are separate thresholds

A verdict of `degraded` requires the primary metric to be **both**:

* **significant** — adjusted p below alpha *and* the confidence interval
  excludes zero. Requiring both means a verdict can never rest on a p-value
  that disagrees with its own interval.
* **material** — `|difference| ≥ min_effect` (default 0.01).

With a large golden set, a 0.2-point drop can be statistically unambiguous and
operationally irrelevant. Alerting on it is how a dashboard teaches people to
ignore it. Both flags are reported separately, so the UI can show "real, but
below your threshold".

### Hit rate uses McNemar, not a two-proportion z-test

The fraction of queries retrieving anything relevant is a proportion, but the
two runs score the *same* queries — they are not independent samples, so a
two-proportion z-test does not apply. **McNemar's exact test** conditions on
the discordant pairs (the queries whose outcome actually changed), which is
both valid under pairing and more powerful, since concordant queries carry no
information about change. The exact binomial form is used rather than the
chi-squared approximation because discordant counts are usually small.

This test is honest about its own limits. With 5 discordant pairs all moving
the same way, the smallest achievable two-sided p is 2 × 0.5⁵ = **0.0625** — it
*cannot* reach significance at α = 0.05 no matter how one-sided the evidence.
The continuous metrics detect that same regression easily; the hit-rate test
says so rather than pretending otherwise.

### Reproducibility

The seed is fixed (default `20240517`) and the query ordering is sorted, so
identical inputs always produce an identical verdict. A monitoring tool that
returned a different answer on a refresh would be worse than useless. The full
`DriftConfig` is stored with every assessment, so an old verdict can always be
reproduced and understood even after the settings change.

### What a verdict looks like

```
verdict : degraded
summary : Retrieval quality regressed: NDCG@5 fell 19.3 points (0.958 to 0.765),
          95% CI [-0.362, -0.086], p=0.0258. Also down: MRR, Recall@5, Precision@5.
queries : 30   baseline runs: 3

  metric              base     now     diff                 95% CI    p_adj  sig mat
  recall_at_k       0.9333  0.7667  -0.1667     [-0.3667, -0.1000]   0.0258   Y   Y
  precision_at_k    0.2067  0.1733  -0.0333     [-0.0733, -0.0200]   0.0236   Y   Y
  mrr               0.9583  0.7678  -0.1906     [-0.3600, -0.0811]   0.0258   Y   Y
  ndcg_at_k         0.9582  0.7648  -0.1934     [-0.3622, -0.0864]   0.0258   Y   Y
  hit rate: 1.000 -> 0.833 | became misses 5, became hits 0, McNemar p=0.0625
```

Never `{"drift": true}`. A verdict you cannot argue with is not evidence, it is
an assertion.

### Refusing to answer

The detector returns `insufficient_data` rather than guessing when:

* there is no earlier run scored against the same golden set fingerprint;
* the only candidates used a different primary cutoff (Recall@5 and Recall@10
  are different quantities);
* fewer than `min_queries` queries are shared between the runs.

Each refusal says which, and ignored runs are counted in the warnings.

---

## Root-cause diagnostics — and why they are framed differently

Once drift is confirmed, the tool tries to explain it. This section exists
because that explanation is the **one place in the project that says something
without a rigorous test behind it**, and pretending otherwise would undo the
care taken in the section above.

### The boundary, stated plainly

| | Drift detection (Stage 3) | Diagnostics (Stage 4) |
| ---------- | ---------------------------------- | ---------------------------------- |
| Question | *Did quality really change?* | *What plausibly caused it?* |
| Method | Paired bootstrap, exact McNemar | Heuristic checks over recorded facts |
| Output | Interval, p-value, stated α | Ranked observations |
| Verified | Coverage checked by simulation | Not verifiable — no ground truth |
| Can it decide? | Yes — it produces the verdict | **No** — it only annotates one |

A diagnostic can never create, upgrade or contradict a verdict. Diagnostics
are only generated for runs already judged `degraded`, and a healthy run
returns `diagnostics: null` rather than a speculative list of things that
happen to have changed.

### The boundary is enforced by vocabulary, not by convention

It would be easy for a "likely cause" heuristic to *feel* as confident as the
statistics it sits next to. So the types make that hard to write:

* **No numeric confidence anywhere.** `DiagnosticFinding` has no field
  containing `confidence`, `probability`, `p_value` or `significant` — and
  there is a test that fails if one is ever added. A float would invite
  "78% likely", and nothing here could calibrate that number.
* **Strength is ordinal**, not a score: `direct` → `circumstantial` →
  `contextual`. The levels describe *how directly the fact links to the
  queries that broke*, not how likely the explanation is to be true.
* **Every report carries its own framing.** The serialised payload includes
  `"basis": "heuristic"` and a disclaimer, so the framing travels with the
  data instead of living only in documentation nobody re-reads.

### The one number a finding may quote

`explains: 5, out_of: 5` — how many of the queries that actually broke
reference the thing the rule found. That is arithmetic over observed data, not
inference, so it is allowed.

Each finding also names the population it counted, because two findings
quoting "2 of 2" and "23 of 30" against silently different denominators would
invite exactly the false comparison this is trying to avoid.

Note what the embedding-change rule does here: it reports **no** coverage at
all. A model swap affects every query at once, so quoting a per-query
attribution would imply a specificity it does not have. A rule that cannot
honestly count says nothing.

### The rules

A registry, not an `if`-chain — heuristics are exactly the kind of code that
accretes, and the accretion has to be additive. Adding one is a new class plus
a `@register_rule` decorator; the engine, API and existing rules are untouched.

| Rule | Strength | What it observes |
| ------------------------------ | ---------------- | ---------------------------- |
| `missing_expected_documents` | direct | Documents the golden set expects are absent from the index |
| `embedding_model_changed` | direct | The recorded `model_id` or dimensionality differs between runs |
| `expected_documents_demoted` | direct | Expected documents are still indexed but fell out of the top-k |
| `corpus_size_changed` | circumstantial | Document count moved by more than 10% |
| `regression_shape` | contextual | Whether the damage is concentrated or systemic |

Rules perform no I/O. Everything they may inspect is on a `DiagnosticContext`,
which keeps them trivially testable and means an unreachable vector store
degrades to *"this check was skipped"* rather than to an exception halfway
through a report. A rule that raises is isolated and recorded as skipped — the
verdict is already established by that point, and losing the whole explanation
would be far worse than losing one line of it.

### Skipped is not the same as passed

Reports distinguish three states, because collapsing them would overstate what
the tool knows:

* **finding** — the check fired
* **`checks_passed`** — the check ran and found nothing (*ruled out*)
* **`checks_skipped`** — the check could not run, with the reason (*unknown*)

Negative results are kept deliberately. "The embedding model is unchanged" is
worth as much to someone debugging as any positive finding, and a report that
only ever shows hits looks like it is fishing.

### Two causes, correctly discriminated

Both scenarios below produce a `degraded` verdict with a comparable drop. The
diagnostics tell them apart — and the *ruled out* lists are mirror images:

**Six expected documents deleted from the index**

```
1. [DIRECT]         Expected documents missing from the index   [explains 5/5]
   6 document(s) the golden set expects are absent from the index. 5 of the 5
   queries that stopped retrieving anything relevant expect at least one of them.
2. [CIRCUMSTANTIAL] Indexed document count changed
   The index shrank from 32 to 26 documents (-19%).
3. [CONTEXTUAL]     Shape of the regression                     [explains 6/30]
   6 of 30 queries scored worse (20%). A small, specific set of queries moved,
   which points at particular documents rather than at the index as a whole.

ruled out: embedding_model_changed, expected_documents_demoted
```

**A re-index that created duplicate fragments (nothing deleted)**

```
1. [DIRECT]         Expected documents still indexed but no longer retrieved  [2/2]
   The content is intact; what changed is the ranking.
2. [CIRCUMSTANTIAL] Indexed document count changed
   The index grew from 32 to 135 documents (+322%).
3. [CONTEXTUAL]     Shape of the regression                     [explains 23/30]
   23 of 30 queries scored worse (77%). Most of the golden set moved together,
   which points at something systemic.

ruled out: embedding_model_changed, missing_expected_documents
```

The first is a content problem, the second a ranking problem, and the
`expected_documents_demoted` rule is the discriminator between them: it fires
only when the expected documents are *verifiably still in the index*.

---

## How it is packaged

```
┌─ frontend (nginx :80) ──────────────┐
│  /            → built React SPA     │
│  /api/*       → proxy to backend    │   one origin, so no CORS in production
│  /docs        → proxy to backend    │
└──────────────┬──────────────────────┘
               │ docker network
┌──────────────▼──────────────────────┐
│  backend (uvicorn :8000)            │
│  FastAPI · SQLAlchemy · SciPy       │
│  /app/data ──► drift-data volume    │   run history (SQLite)
└──────────────┬──────────────────────┘
               │ HTTP
┌──────────────▼──────────────────────┐
│  chroma (server :8000)              │
│  /data ──────► chroma-data volume   │   the vector index
└─────────────────────────────────────┘
```

### Why Chroma runs as a server and not as an embedded client

This is a correctness requirement, not a preference, and it is the single most
important thing to understand about deploying this tool.

`chromadb.PersistentClient` caches a collection's vector segment in memory for
the life of the process, and does **not** observe writes made by another
process. Reopening the client does not help either — chromadb caches the
underlying `System` per path, so a "fresh" client hands back the same stale
segment.

A drift detector reads an index that some *other* pipeline writes. With an
embedded client it would keep scoring the index as it looked when the API
booted, and would never notice the change it exists to detect — while still
reporting a correct document count, because `count()` reads metadata rather
than the cached segment. That combination is worse than an outright failure:
the numbers look plausible and are silently wrong.

Measured, with the index served by a Chroma server and six expected documents
deleted by a separate process:

```
run 1   docs=32   recall@5=0.9333      # healthy
                                       # another process deletes 6 documents
run 2   docs=26   recall@5=0.7667      # detected
```

With the embedded client, `run 2` returned `docs=26` and `recall@5=0.9333` —
the count moved, the retrieval did not.

If you point this tool at your own index, use a Chroma server
(`DRIFT_CHROMA_MODE=http`). The embedded `persistent` mode is only safe when
nothing else writes the index, which in practice means local development and
the test suite.

Both images are multi-stage and copy dependency manifests before source, so a
code change does not invalidate the slow install layer. The backend runs as an
unprivileged user with the data directory as its only writable path.

The backend's healthcheck calls its own `/api/health`, which returns 503 when
the database or the vector store is unreachable — so it reports genuine
readiness rather than merely that a process is listening. The frontend waits
for `service_healthy`, not `service_started`, so the first page load never
races the migrations and the demo bootstrap.

Both SQLite and the Chroma index live under one directory, so a single named
volume is the whole persistence story. `docker compose down -v` resets
everything.


---

## Storing history

Runs go into SQLite through SQLAlchemy, with **Alembic** as the only source of
truth for the schema — there is no `create_all` shortcut, and the test suite
runs the real migrations for every test, so a schema nobody has proved
deployable can never pass CI.

Two schema decisions carry most of the weight:

**Golden sets are relational, not JSON blobs.** Queries and expected documents
are real rows, so the dashboard's editor can change one pair without rewriting
the set, and diagnostics can join judgements against results in SQL.

**Runs denormalise the golden set they were scored against.** Alongside the
foreign key, each run stores the golden set's name, version and *fingerprint*
as plain columns. Deleting or editing a golden set therefore cannot rewrite
history — a metric is only meaningful next to the ruler that produced it, and
that ruler must not be able to change retroactively. Editing judgements
recomputes the fingerprint, which automatically excludes runs either side of
the edit from each other's drift comparison.

Two SQLite pragmas are set explicitly on every connection: `foreign_keys=ON`
(without it, every declared `ON DELETE CASCADE` is silently inert) and
`journal_mode=WAL` (so a dashboard poll does not block on an in-progress
evaluation).

---

## The golden set

A golden set is the ground truth definition of "good retrieval" for *your*
system: queries paired with the documents that should come back for them.

JSON, with optional graded relevance:

```json
{
  "name": "acme-cloud-support",
  "version": "1",
  "queries": [
    {
      "query_id": "q-429",
      "query": "getting HTTP 429 with a Retry-After header from the api",
      "expected_documents": [
        { "document_id": "doc-api-001", "relevance": 3 },
        { "document_id": "doc-api-004", "relevance": 1 }
      ]
    }
  ]
}
```

CSV, for sets maintained in a spreadsheet — one row per (query, document) pair:

```csv
query_id,query,expected_document_id,relevance
q-429,getting HTTP 429 from the api,doc-api-001,3
q-429,getting HTTP 429 from the api,doc-api-004,1
```

Every golden set carries a **fingerprint**: a content hash of the judgements
alone, ignoring name and timestamps. Two runs are only comparable for drift
purposes if they were scored against the same fingerprint — otherwise you are
measuring a change in the ruler, not a change in the system.

---

## Metrics, and the conventions behind them

IR metrics have several defensible definitions in the wild, so this project
states which ones it uses. All four are reported in `[0, 1]` and **macro**
averaged — each query counts once regardless of how many documents it expects,
so a handful of many-document queries cannot mask a broad regression.

| Metric | Definition used here |
| ------------- | ------------------------------------------------------------ |
| Recall@k | `\|relevant ∩ top-k\| / \|relevant\|` |
| Precision@k | `\|relevant ∩ top-k\| / min(k, \|retrieved\|)` — the denominator is clamped to what was actually returned, so a store holding fewer than *k* documents is not punished for the size of its corpus |
| MRR | mean of `1 / rank` of the *first* relevant hit within top-k; `0` on a miss |
| NDCG@k | exponential gain `2^rel − 1`, `log2(rank + 1)` discount, normalised by the ideal ranking of that query's own judgements — honours graded relevance |

Metrics for *every* configured cutoff come from a **single** retrieval at
`max(k_values)`. Retrieval is the expensive step, and deriving Recall@1/@3/@5/@10
from one ranked list is both cheaper and more internally consistent than issuing
four queries whose results could differ.

Why track all four? Recall is blind to ordering: a change that pushes the right
document from rank 1 to rank 5 leaves Recall@5 untouched while NDCG and MRR both
drop. That is precisely the kind of silent degradation this tool exists to catch.

---

## Embeddings, and why they are explicit

The Chroma connector embeds queries itself through an `EmbeddingProvider` rather
than delegating to Chroma's built-in embedding function. Two reasons:

1. **Silently swapping embedding models is one of the most common real causes of
   retrieval drift.** Making the provider explicit means every run records a
   `model_id`, and the collection records the model that *built* it — so a
   mismatch between them is detectable rather than invisible (Stage 4).
2. **The demo has to run with zero setup.** The default `hashing` provider is a
   deterministic, dependency-free implementation of the hashing trick (signed
   feature hashing over word unigrams, word bigrams and character trigrams;
   sub-linear term weighting; L2 normalised). It is not a semantic model — it is
   an honest, reproducible, offline stand-in so the whole pipeline is runnable
   and testable without downloading anything.

Production deployments register a real provider under a different name; the
recorded `model_id` makes the swap visible.

---

## Development

```bash
# Backend — 279 tests, mypy --strict clean across 62 modules
cd backend
python -m pytest
python -m ruff check app tests alembic
python -m mypy app

# Frontend — 29 tests, TypeScript strict, ESLint clean
cd ../frontend
npm test
npm run typecheck
npm run lint
```

Test coverage concentrates where it matters. The metric primitives are pinned
to hand-computed values; the bootstrap's interval coverage is verified by
simulation; the scoring engine runs against a fake connector so the suite needs
no vector store; repository tests run the real Alembic migrations rather than
`create_all`; and the API tests drive a fully bootstrapped application with
nothing mocked.

Two design commitments are protected by tests rather than by convention: that
each published metric is exactly the macro-mean of the per-query values the
bootstrap resamples, and that the diagnostics layer never acquires a numeric
confidence — on the backend as a field-name check, on the frontend as an
assertion that no progress bar or "% confident" string ever reaches the DOM.

---

## Licence

MIT.
