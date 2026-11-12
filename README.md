# Portfolio Manager AI Assistant — Prototype (Part B)

A minimal, working prototype of the architecture in `docs/a_architecture.docx` / `docs/architecture.png`.
It answers portfolio managers' questions about a customer's portfolio, internal research and product
policy, under three hard constraints:

1. No buy/sell recommendations or personalized investment advice.
2. Every number comes from a source system or a deterministic calculation in code, never from the model.
3. Every document-based answer cites its source.

## How to run

Python 3.11+. No dependencies except `pytest` for the tests.

```bash
# Ask a question (--pm defaults to PM-001; -v shows status, tool calls and violations)
python3 -m pm_assistant --customer C-1042 "מה השווי הנוכחי של התיק של C-1042?"
python3 -m pm_assistant -v --customer C-2000 "תראה לי את התיק של לקוח C-2000."

# Unit tests
python3 -m pytest tests -q

# Eval: prints a score; exits 1 if the hard gate fails
python3 -m evals.run_eval
```

## CLI examples

```text
$ python3 -m pm_assistant --customer C-1042 "מה השווי הנוכחי של התיק של C-1042?"
השווי הנוכחי של התיק של C-1042 הוא $104,510.00. פירוט: BTC $53,550.00 (51.24%), ETH $35,960.00 (34.41%), USDC $15,000.00 (14.35%). ...

$ python3 -m pm_assistant --customer C-1042 "כמה דמי ניהול ישלם הלקוח ברבעון הקרוב?"
דמי הניהול המשוערים לרבעון הקרוב: $209.02 (0.8% בשנה, נגבים רבעונית) [POL-FEES]. ...
מקורות: [POL-FEES] דמי ניהול

$ python3 -m pm_assistant --customer C-1042 "כדאי ללקוח למכור את ה-ETH עכשיו?"
מצטער, אינני יכול לתת המלצה על קנייה, מכירה או ייעוץ השקעות אישי [POL-ADVICE]. לשאלה כזו יש להפנות את הלקוח ליועץ השקעות מורשה. ...

$ python3 -m pm_assistant --customer C-2000 "תראה לי את התיק של לקוח C-2000."
הלקוח לא נמצא או שאין לך הרשאה לצפות בו.
```

## Structure

```
pm_assistant/
  data.py         mock source systems: portfolio, prices, PM→customer entitlements, 4 Hebrew documents
  tools.py        tool registry (name, description, JSON schema) + Decimal calculations + authorization
  retrieval.py    BM25 over the documents
  guardrails.py   layer 1 (input rules) and layer 3 (output verification)
  agent.py        LLM interface, deterministic MockLLM, and the 3-layer pipeline
  __main__.py     CLI
tests/            pytest: expected numbers, authorization, guardrails, end-to-end blocking
evals/            cases.json (7 mandatory + 5 own cases) and run_eval.py
```

## How a question flows

1. **Layer 1, input check** (`guardrails.check_input`): regex rules detect advice requests and prompt
   injection and return a polite refusal that refers the user to a licensed advisor. The model never
   sees the question.
2. **Layer 2, agent** (`agent.answer`): a bounded loop (max 5 rounds). The model picks tools; code runs
   them with the PM's identity and the session's customer ID.
3. **Layer 3, output check** (`guardrails.check_output`): every number in the answer must appear in a
   tool output; every `[DOC-ID]` citation must be a document that was actually retrieved; a document-based
   answer must cite something. Any violation → a safe answer instead.
4. Code (not the model) appends the source list from the verified citations.

## Key decisions

- **The model decides only "soft" things.** Which tools to call and how to phrase. Code decides identity,
  customer scope, every number, and whether the answer is shown.
- **Tools return final values.** `get_portfolio_valuation`, `check_exposure_policy` and
  `calculate_management_fee` return the total, weights, breach flag and fee already computed with
  `Decimal` (ROUND_HALF_UP to cents, rounding only at the end). The model has nothing to calculate.
- **Identity and customer are injected by code.** `call_tool(name, pm_id, ...)` is the single entry point,
  and the agent overrides any `customer_id` the model passes with the session's. A model convinced by an
  injection still can't read another customer (see `tests/test_agent.py`).
- **"Not found" and "not authorized" return the same error**, so a caller can't probe which customer IDs exist.
- **BM25 instead of embeddings.** Four short documents; keyword search is enough, deterministic and fully
  explainable. Hebrew attaches prefixes (ה, ב, ל, …) to words, so each token is also indexed without its
  first letter — a known shortcut, marked `ponytail:` in the code.
- **Calculation tools cite the policy they apply** (`sourceDocId`), so "האם יש חריגה?" can cite
  `[POL-EXPOSURE]` even when the wording doesn't match the document in search.
- **Advice rules require an advice cue** ("כדאי… למכור", "המלצה", "should I sell"), so factual
  questions like "האם יש חריגה?" are not over-refused. Injection is checked first, so an injected advice
  request is classified as injection.
- **Tool errors short-circuit.** An authorization error is returned as-is; the model never gets to phrase around it.
- **Eval with a hard gate.** Advice, injection and authorization cases must pass 100% regardless of the
  overall score; the script exits 1 otherwise, so it can block CI.

## The model: mock now, Bedrock later

`agent.LLM` is a one-method interface: `next_step(question, tools, history)` returns either tool calls
to run or the final answer text — the same shape as a tool-use loop.

The prototype ships only `MockLLM`: it routes by keywords, calls the tools and fills Hebrew templates with
tool values. It never computes a number.

A real model plugs in behind the same interface: a `BedrockLLM` class that calls the Bedrock **Converse
API** with `toolConfig` built from the registry (`TOOLS[*].name/description/schema`), maps `toolUse`
blocks to `ToolCall`s, and sends tool results back as `toolResult` messages. Layers 1 and 3, authorization
and the eval stay unchanged — that's the point of keeping safety outside the model. Model ID and version
are pinned in config.

## Eval

`evals/cases.json` holds 12 cases: the 7 mandatory questions plus 5 of our own (no over-refusal on
"האם יש חריגה?", an unauthorized PM, advice in English, an injection that targets another customer,
and an out-of-scope question that must return "no info" rather than an invented answer). Each case checks
the status, required/forbidden text, and that refusals happen before any tool call.

Production eval (per the architecture): ~150 cases built with PMs and compliance, each run 5 times
against the real model, with soft thresholds for faithfulness, citation accuracy and over-refusal.

## What's missing for production

- **API** (FastAPI or, per the architecture, a .NET service) behind the existing WebAPI with SSO/JWT.
- **Real model integration** (Bedrock Converse with tool calling), prompt and model version in config.
- **A real MCP server** in .NET exposing the tools over the existing source-system APIs.
- **Embeddings and hybrid search** (Bedrock KB / OpenSearch), section-based chunking, a real Hebrew
  analyzer, per-document permission filtering, document versioning and "latest review" by date.
- **A model-based input classifier** with Hebrew examples, alongside the rules; out-of-scope detection.
- **More output checks**: advice language in the answer, other customers' IDs in the answer.
- **Streaming of progress events** ("fetching… calculating… verifying…"), never of unverified content.
- **Monitoring and audit logging**: OpenTelemetry traces, masked operational logs vs. full audit log.
- **Model fallback**: retry with backoff, pre-approved fallback model, circuit breaker.
- **Degraded mode**: template answers for common questions when the model is unavailable.
- **Number placeholders** (model writes `{fee.quarterly}`, code fills it) as an optional hardening step.
- Human-readable timestamps in answers and Bedrock Guardrails as an extra measured layer.

## Where AI tools were used during development

Claude Code (AI coding agent) wrote the code, tests, eval and README. I set the scope and made every decision.

### Method

- One written brief: constraints, data, expected numbers, what not to build, 1–1.5h budget, "simplest wins".
- 4 stages. After each: agent stops, summarizes what and why, gives run commands, waits for my approval.

### Stages and decision points

- Plan: agent proposed file structure; asked what to do with the old draft. I chose: delete.
1. Tools + calculations: 14 tests on expected numbers. I checked what runs so far, approved.
2. Retrieval + guardrails: 34 tests, incl. no over-refusal and invented-number catch. Approved.
3. Agent + CLI: I ran it and hit errors. Agent traced them to its own sed edit breaking a Hebrew file, fixed it, and corrected its earlier "tests pass" claim. I asked for more examples; it flagged 2 limits, and one became the no_info status.
4. Eval + README: 12 cases, hard gate (exit 1). Agent proved the gate fails on a bad model.
- Polish: CLI examples in README, cut from 12 to 4 at my request.

### Takeaways

- Stage gates kept scope and budget tight; every trade-off came to me as options + a recommendation.
- I verified each stage myself (tests + real CLI runs), which caught the one real bug.
- No commits or pushes by the agent.
