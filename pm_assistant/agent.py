"""Layer 2 (the agent) wired between layer 1 and layer 3.

The model only decides "soft" things: which tools to call and how to phrase the answer. Code decides
the "hard" things: identity, customer scope, numbers, and whether the answer is shown.
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

from pm_assistant import data, guardrails
from pm_assistant.tools import TOOLS, Tool, ToolError, call_tool

MAX_ROUNDS = 5
NO_INFO = "לא מצאתי מידע רלוונטי במסמכים הזמינים."


@dataclass
class ToolCall:
    name: str
    args: dict = field(default_factory=dict)


History = list[tuple[ToolCall, dict]]


class LLM(Protocol):
    """Same shape as a Converse tool-use loop: return tool calls to run, or the final answer text."""

    def next_step(self, question: str, tools: list[Tool], history: History) -> list[ToolCall] | str: ...


@dataclass
class Result:
    text: str
    status: str  # answered | no_info | refused_advice | refused_injection | denied | blocked_output
    tool_calls: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)


def _usd(x: Decimal) -> str:
    return f"${x:,.2f}"


class MockLLM:
    """Deterministic stand-in: keyword routing + templates. Never computes a number itself."""

    def next_step(self, question: str, tools: list[Tool], history: History) -> list[ToolCall] | str:
        if not history:
            return self._plan(question)
        return self._compose({call.name: out for call, out in history})

    def _plan(self, q: str) -> list[ToolCall]:
        calls = []
        if "שווי" in q or ("תיק" in q and not ("חשיפה" in q or "חריג" in q)):
            calls.append(ToolCall("get_portfolio_valuation"))
        if "חשיפה" in q or "חריג" in q:
            calls.append(ToolCall("check_exposure_policy"))
        if "דמי ניהול" in q:
            calls.append(ToolCall("calculate_management_fee"))
        if not calls:
            calls.append(ToolCall("search_knowledge_base", {"query": q}))
        return calls

    def _compose(self, out: dict[str, dict]) -> str:
        parts = []
        if v := out.get("get_portfolio_valuation"):
            lines = ", ".join(f"{p['asset']} {_usd(p['valueUsd'])} ({p['weightPct']}%)" for p in v["positions"])
            parts.append(
                f"השווי הנוכחי של התיק של {v['customerId']} הוא {_usd(v['totalValueUsd'])}. "
                f"פירוט: {lines}. נתוני ההחזקות נכונים ל-{v['holdingsAsOf']}, השערים ל-{v['pricesAsOf']}."
            )
        if e := out.get("check_exposure_policy"):
            capped = ", ".join(f"{a['asset']} {a['weightPct']}%" for a in e["assets"] if a["subjectToLimit"])
            breaches = [a["asset"] for a in e["assets"] if a["breach"]]
            verdict = f"יש חריגה ב: {', '.join(breaches)}." if breaches else "אין חריגה ממדיניות החשיפה."
            parts.append(
                f"החשיפה לנכסים שאינם מטבע יציב: {capped}. המגבלה היא {e['limitPct']}% משווי התיק הדיגיטלי "
                f"לנכס בודד [{e['sourceDocId']}]. {verdict}"
            )
        if f := out.get("calculate_management_fee"):
            parts.append(
                f"דמי הניהול המשוערים לרבעון הקרוב: {_usd(f['quarterlyFeeUsd'])} "
                f"({f['annualFeePct']}% בשנה, נגבים רבעונית) [{f['sourceDocId']}]. "
                f"ההערכה מבוססת על השווי הנוכחי, {_usd(f['baseValueUsd'])}."
            )
        if s := out.get("search_knowledge_base"):
            if not s["results"]:
                return NO_INFO
            top = s["results"][0]
            parts.append(f"לפי {top['title']} [{top['docId']}]: {top['text']}")
        return "\n".join(parts)


def _retrieved_ids(outputs: list[dict]) -> set[str]:
    """Docs the answer may cite: search hits plus the policy doc a calculation tool applied."""
    ids = set()
    for o in outputs:
        ids |= {r["docId"] for r in o.get("results", [])}
        if "sourceDocId" in o:
            ids.add(o["sourceDocId"])
    return ids


def answer(pm_id: str, customer_id: str, question: str, llm: LLM | None = None) -> Result:
    llm = llm or MockLLM()

    # Layer 1: refuse before the model ever sees the question.
    if refusal := guardrails.check_input(question):
        status = "refused_injection" if refusal == guardrails.INJECTION_REFUSAL else "refused_advice"
        return Result(refusal, status)

    # Layer 2: bounded tool loop.
    history: History = []
    text = None
    for _ in range(MAX_ROUNDS):
        step = llm.next_step(question, list(TOOLS.values()), history)
        if isinstance(step, str):
            text = step
            break
        for call in step:
            args = dict(call.args)
            # Customer scope comes from the session, not the model, so an injected
            # "show me C-9999" can't widen access.
            if "customer_id" in TOOLS[call.name].schema["properties"]:
                args["customer_id"] = customer_id
            try:
                history.append((call, call_tool(call.name, pm_id, **args)))
            except ToolError as e:
                return Result(str(e), "denied", [c.name for c, _ in history] + [call.name])
    calls = [c.name for c, _ in history]
    if text is None:
        return Result(guardrails.SAFE_ANSWER, "blocked_output", calls, ["max rounds exceeded"])

    # Layer 3: verify before showing anything.
    outputs = [out for _, out in history]
    if violations := guardrails.check_output(text, outputs, _retrieved_ids(outputs)):
        return Result(guardrails.SAFE_ANSWER, "blocked_output", calls, violations)

    # Source list is built by code from verified citations, not written by the model.
    cited = sorted(set(guardrails.CITATION.findall(text)))
    if cited:
        text += "\n\nמקורות: " + "; ".join(f"[{d}] {data.DOCUMENTS[d]['title']}" for d in cited)
    # Tracked separately so the eval can tell "nothing found" from a real answer.
    return Result(text, "no_info" if text == NO_INFO else "answered", calls)
