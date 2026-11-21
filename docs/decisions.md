# Design decisions

Each choice is explained in two or three plain sentences. All data in this repo is SYNTHETIC.

## Build mode
The project was built in one autonomous run from the "one prompt, auto mode" brief. Defaults were chosen
without asking and are recorded here. Nothing was pushed, published or deployed, and no cloud resources were created.

## Repository layout
Code lives in `app/` (api, agent, tools, retrieval, safety, store, models), with evals in `evals/` and tests in `tests/`.
`config/` holds the files a reviewer is expected to edit: the safety rules and the model prices.

## Two storage backends behind one interface
PostgreSQL with pgvector is the main store (`docker compose up -d db`, `STORE_BACKEND=postgres`). A SQLite
backend with the same interface (FTS5 for keywords, Python cosine for vectors) is used by the tests and the CI eval, so
they run with no Docker and no network. The corpus is small (about 35 chunks and 300 records), so a brute-force vector
search in Python is fast enough for SQLite.

## Windows without make
The build machine has no `make`, so `tasks.py` mirrors every Makefile target (`py tasks.py test`). The Makefile is
still the main interface on Linux and macOS and in CI.

## Synthetic stand-in manual
No real manual was supplied, so `make ingest` writes `data/manual/SYNTHETIC_centrifugal_pump_manual.txt` (20 pages,
`=== PAGE n ===` markers, numbered headings, a fault-code table and troubleshooting entries). If you drop a real PDF or
.txt into `data/manual/` (or set `MANUAL_PATH`), it is ingested instead. Remove the synthetic file first, because every
file in the folder is ingested.

## One catalog for the manual and the history
`app/data_gen/catalog.py` is the single source for the synthetic manual's fault codes and for the synthetic history,
so the two always agree. With a real manual the fault-code parser may find different codes; `make seed` reports any
history codes not found in the manual (`codes_not_in_manual`), and the catalog would need updating to match.

## Parsing and page numbers
Text files are split on page markers and PDFs are read page by page with pypdf. Every page keeps its number, so a
citation can always point to a page. Section headings are numbered lines (for example "4.3 Suction piping and NPSH").

## Heading-aware chunking
A chunk never crosses a section heading or a page boundary, and it is at most about 900 characters. The section heading
is stored with the chunk and prepended to the text it is searched by, so a short troubleshooting entry still matches on
its title. This keeps citations precise (one page) and keeps each troubleshooting entry in one piece.

## Hybrid search with Reciprocal Rank Fusion
Keyword search (PostgreSQL full-text or SQLite FTS5) and vector search each return a candidate list, and the two are
merged with Reciprocal Rank Fusion. RRF needs no score calibration between the two very different scorers. Keywords
catch exact codes such as "PF-104"; vectors catch paraphrases.

## Swappable rerank
`RERANKER=overlap` (default) boosts results by how many query terms they cover and adds a boost for exact fault-code
matches; `RERANKER=none` turns it off. It is a plain function in a registry, so a cross-encoder or a hosted reranker
can replace it without touching callers. `make compare` prints keyword, vector and hybrid results side by side.

## Deterministic fake embedder and FakeLLM
`HashEmbedder` uses feature hashing of words and word pairs, so the same text always gives the same vector, with no
model download. `FakeLLM` plays the three model tasks (triage, next tool, draft) with plain rules in
`app/agent/fake_policy.py`. This lets pytest and `make eval` run with no API key, but its scores say nothing about the
quality of a real model.

## Model adapter
`app/llm.py` exposes only `complete_json(task, payload)` and `embed(texts)`. `LLM_PROVIDER=azure` uses Azure OpenAI
(the default real provider) and `LLM_PROVIDER=openai` uses any OpenAI-compatible endpoint via `OPENAI_BASE_URL`. JSON
mode and temperature 0 keep outputs parseable and repeatable.

## Seeded synthetic history
`random.Random(42)` drives every choice, so `make seed` writes byte-identical files each time (a test checks this
with hashes). About 8% of records are deliberately ambiguous (vague symptom, no code, root cause "undetermined") and
about 4% are incomplete (missing fix or downtime). Root causes are drawn with per-code weights from the catalog.

## Tools return IDs
Every tool has Pydantic input and output models and returns page numbers, chunk IDs or fault record IDs. Bad input
returns `{"error": "invalid input", ...}` instead of raising, so the agent loop never crashes on a bad tool call.
Machine IDs and fault codes are validated with strict patterns.

## Safety gate in plain code, first
The safety check is the first graph node and calls no model: regex rules from `config/safety_rules.yaml`. On a match
the run ends with a fixed stop message, so no AI text is generated and no tool is called (a test uses a model that
raises if called). The rules are broad on purpose, are marked PROVISIONAL, and need review by a qualified person.

## Graph shape and the approval pause
LangGraph runs safety_check -> triage -> investigate (one tool per step, looping) -> draft -> approval_gate. The
approval gate "pauses" by saving the report with status `awaiting_approval`; the run resumes when someone calls
`POST /reports/{id}/decision`. Saving to the database instead of using an in-memory LangGraph checkpoint means a
pending approval survives a server restart.

## Tool-loop limit
`MAX_TOOL_CALLS=6` is checked in code inside the investigate node, so a model that never says "finish" still stops
after six calls and goes on to draft. The graph's recursion limit is set from the same number.

## Evidence is enforced in code
After the model drafts, `enforce_evidence` keeps only citations to pages and record IDs that a tool actually returned
in this run, drops any claim left without a citation, and escalates if no cause survives. An invalid draft (bad
schema) also escalates. The eval measures separately whether each quote really appears on the cited page or record.

## Escalation rule in the fake model
The fake model escalates ("Cannot tell, escalate to a senior technician.") when no fault code can be found, or when
there is no explicit code and either no symptom words were recognised or fewer than half of the similar past faults
share one code. This is a placeholder for a real model's judgement.

## Approval states
`awaiting_approval` can move to `approved`, `rejected` (a reason is required) or `approved_with_edits` (an edited
draft is required). `safety_stop` and `out_of_scope` reports accept no decision (409), and neither does a report that
has already been decided. Every decision is stored as its own row with the reviewer and time.

## Traces and cost
Each run writes `traces/run_<time>_<id>.json` with the inputs, every tool call (arguments, output, latency), every
model call (tokens, latency), the outputs and totals. Cost comes from `config/prices.yaml`. Real model prices are left
`null` until you fill them in, so cost shows as unknown rather than as a made-up number.

## Eval gate
`evals/cases.yaml` has 50 synthetic cases whose expected answers were drafted by the build agent and need human review.
`make eval` fails if the safety pass rate is below 100% or if any gated score drops more than `margin` (0.05,
PROVISIONAL) below `evals/baseline.json`. The current baseline is labelled "offline baseline (fake model), not a
quality measure". Latency and cost are reported but not gated, because fake-model numbers mean nothing for them.

## Safety metric definition
A safety case passes only if the status is `safety_stop`, the message is exactly the fixed stop message, no model call
was made and no draft exists. False alarms on non-safety cases are reported as `safety_false_alarm_rate`, not gated.

## Citation correctness
For a manual citation the quote must appear (whitespace- and case-insensitive) in the text of the cited page; for a
record citation it must appear in the stored record. This catches a citation that names a real page but does not
support the claim.

## CI workflow
`.github/workflows/eval.yml` runs pytest and `python -m evals.run_eval --fresh` on pull requests, offline. It was
added as a file only; nothing was pushed.
