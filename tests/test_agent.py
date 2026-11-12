from pm_assistant.agent import ToolCall, answer
from pm_assistant.guardrails import SAFE_ANSWER


class HallucinatingLLM:
    """Calls the right tool, then makes up a number. Layer 3 must block it."""

    def next_step(self, question, tools, history):
        return [ToolCall("get_portfolio_valuation")] if not history else "שווי התיק הוא $250,000.00."


class CrossCustomerLLM:
    """Tries to read another customer's portfolio. Code must override the customer ID."""

    def next_step(self, question, tools, history):
        if not history:
            return [ToolCall("get_portfolio_valuation", {"customer_id": "C-2000"})]
        return f"שווי: {history[0][1]['customerId']}"


def test_invented_number_blocked_end_to_end():
    result = answer("PM-001", "C-1042", "מה השווי?", HallucinatingLLM())
    assert result.status == "blocked_output"
    assert result.text == SAFE_ANSWER


def test_model_cannot_choose_customer():
    assert answer("PM-001", "C-1042", "מה השווי?", CrossCustomerLLM()).text == "שווי: C-1042"
