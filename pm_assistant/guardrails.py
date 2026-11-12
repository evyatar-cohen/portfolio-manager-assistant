"""Layer 1 (input check) and layer 3 (output check). Both are plain code so they can't be talked out of it."""
import re
from decimal import Decimal

# --- Layer 1 -------------------------------------------------------------------------------------
# ponytail: keyword rules only; production adds a small-model classifier with Hebrew examples.
_INJECTION = re.compile(
    r"התעלם|תתעלם|הוראות\s+(?:ה)?קודמות|ignore\s+(?:all\s+)?(?:previous|prior|above)|system\s+prompt"
    r"|אתה\s+עכשיו|you\s+are\s+now|העמד\s+פנים|jailbreak",
    re.IGNORECASE,
)
# Needs an advice cue ("כדאי"/"should"/"המלצה"), so factual questions like "האם יש חריגה?" pass.
_ADVICE = re.compile(
    r"(?:כדאי|שווה|עדיף|מומלץ)\S*\s+(?:\S+\s+){0,2}?(?:לקנות|למכור|להחזיק|להשקיע|לממש|להגדיל|להקטין)"
    r"|המלצ\S*|תמליץ|ממליץ"
    r"|\bshould\s+(?:i|we|they|he|she|the\s+client)\s+(?:buy|sell|hold)|\brecommend",
    re.IGNORECASE,
)

ADVICE_REFUSAL = (
    "מצטער, אינני יכול לתת המלצה על קנייה, מכירה או ייעוץ השקעות אישי [POL-ADVICE]. "
    "לשאלה כזו יש להפנות את הלקוח ליועץ השקעות מורשה. "
    "אשמח לעזור בנתוני התיק, במדיניות המוצר או בסקירות המחקר."
)
INJECTION_REFUSAL = (
    "מצטער, אינני יכול לבצע את הבקשה. אני פועל רק לפי כללי המערכת. "
    "אשמח לעזור בשאלות על תיק הלקוח, מדיניות המוצר או סקירות המחקר. "
    "לייעוץ השקעות יש לפנות ליועץ השקעות מורשה."
)


def check_input(question: str) -> str | None:
    """Return a refusal message if the question must not reach the agent, else None."""
    # Injection first: an injected advice request should be classified (and logged) as injection.
    if _INJECTION.search(question):
        return INJECTION_REFUSAL
    if _ADVICE.search(question):
        return ADVICE_REFUSAL
    return None


# --- Layer 3 -------------------------------------------------------------------------------------
SAFE_ANSWER = "מצטער, לא הצלחתי לאמת את התשובה מול מקורות המידע. נא לנסח את השאלה מחדש או לפנות לצוות התמיכה."

_NUMBER = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
# Public: the agent reuses it to build the source list from verified citations.
CITATION = re.compile(r"\[([A-Z]+(?:-[A-Z0-9]+)+)\]")


def _numbers_in(text: str) -> set[Decimal]:
    return {Decimal(n.replace(",", "")) for n in _NUMBER.findall(text)}


def _grounded_numbers(value: object) -> set[Decimal]:
    """Every number that appears anywhere in tool output, including inside strings (dates, doc text)."""
    if isinstance(value, dict):
        return set().union(*(_grounded_numbers(v) for v in value.values()), set())
    if isinstance(value, (list, tuple, set)):
        return set().union(*(_grounded_numbers(v) for v in value), set())
    if isinstance(value, bool):
        return set()
    if isinstance(value, (int, float, Decimal)):
        return {Decimal(str(value))}
    if isinstance(value, str):
        return _numbers_in(value)
    return set()


def check_output(answer: str, tool_outputs: list[dict], retrieved_ids: set[str]) -> list[str]:
    """Return a list of violations; empty means the answer may be shown."""
    violations = []
    # Decimal equality ignores trailing zeros, so "104,510" matches 104510.00.
    for n in sorted(_numbers_in(answer) - _grounded_numbers(tool_outputs)):
        violations.append(f"ungrounded number: {n}")
    cited = set(CITATION.findall(answer))
    for doc_id in sorted(cited - retrieved_ids):
        violations.append(f"citation not retrieved: {doc_id}")
    if retrieved_ids and not cited:
        violations.append("document-based answer without citation")
    return violations
