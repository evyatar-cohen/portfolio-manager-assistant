"""Tool registry. Tools return final computed values so the model never has to do arithmetic.

In production each tool is an MCP tool on the .NET server; the registry shape (name, description,
JSON schema) is what gets handed to the model for tool calling.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Callable

from pm_assistant import data, retrieval

CENT = Decimal("0.01")


class ToolError(Exception):
    pass


# One message for "missing" and "not yours", so a caller can't probe which customer IDs exist.
ACCESS_DENIED = "הלקוח לא נמצא או שאין לך הרשאה לצפות בו."


def _round(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def _authorize(pm_id: str, customer_id: str) -> dict:
    portfolio = data.PORTFOLIOS.get(customer_id)
    if portfolio is None or customer_id not in data.ENTITLEMENTS.get(pm_id, set()):
        raise ToolError(ACCESS_DENIED)
    return portfolio


def get_portfolio(pm_id: str, customer_id: str) -> dict:
    return _authorize(pm_id, customer_id)


def get_prices(pm_id: str, assets: list[str]) -> dict:
    # Prices aren't customer data, but the caller must still be a known PM.
    if pm_id not in data.ENTITLEMENTS:
        raise ToolError(ACCESS_DENIED)
    return {"pricesUsd": {a: data.PRICES_USD[a] for a in assets if a in data.PRICES_USD}, "asOf": data.PRICES_AS_OF}


def get_portfolio_valuation(pm_id: str, customer_id: str) -> dict:
    portfolio = _authorize(pm_id, customer_id)
    prices = get_prices(pm_id, [h["asset"] for h in portfolio["holdings"]])["pricesUsd"]
    values = {h["asset"]: h["quantity"] * prices[h["asset"]] for h in portfolio["holdings"]}
    total = sum(values.values(), Decimal(0))
    # Round only at the end; weights come from unrounded values so they don't drift.
    positions = [
        {
            "asset": a,
            "priceUsd": prices[a],
            "valueUsd": _round(v),
            "weightPct": _round(v / total * 100),
        }
        for a, v in values.items()
    ]
    return {
        "customerId": customer_id,
        "totalValueUsd": _round(total),
        "positions": positions,
        "holdingsAsOf": portfolio["lastUpdated"],
        "pricesAsOf": data.PRICES_AS_OF,
    }


def check_exposure_policy(pm_id: str, customer_id: str) -> dict:
    valuation = get_portfolio_valuation(pm_id, customer_id)
    limit = data.EXPOSURE_LIMIT_PCT[data.PORTFOLIOS[customer_id]["riskProfile"]]
    assets = [
        {
            "asset": p["asset"],
            "weightPct": p["weightPct"],
            "subjectToLimit": p["asset"] not in data.STABLECOINS,
            "breach": p["asset"] not in data.STABLECOINS and p["weightPct"] > limit,
        }
        for p in valuation["positions"]
    ]
    return {
        "customerId": customer_id,
        "limitPct": limit,
        "assets": assets,
        "anyBreach": any(a["breach"] for a in assets),
        "sourceDocId": "POL-EXPOSURE",
    }


def calculate_management_fee(pm_id: str, customer_id: str) -> dict:
    valuation = get_portfolio_valuation(pm_id, customer_id)
    # Assumption: next quarter's fee is estimated from current value.
    quarterly = _round(valuation["totalValueUsd"] * data.ANNUAL_FEE_PCT / 100 / 4)
    return {
        "customerId": customer_id,
        "annualFeePct": data.ANNUAL_FEE_PCT,
        "baseValueUsd": valuation["totalValueUsd"],
        "quarterlyFeeUsd": quarterly,
        "sourceDocId": "POL-FEES",
    }


def search_knowledge_base(pm_id: str, query: str) -> dict:
    # ponytail: all docs visible to every PM; production filters by per-document permissions in the query.
    if pm_id not in data.ENTITLEMENTS:
        raise ToolError(ACCESS_DENIED)
    return {"results": retrieval.search(query)}


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: dict
    fn: Callable[..., dict]


_CUSTOMER_SCHEMA = {
    "type": "object",
    "properties": {"customer_id": {"type": "string"}},
    "required": ["customer_id"],
}

TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        Tool("get_portfolio", "Raw holdings and risk profile of a customer.", _CUSTOMER_SCHEMA, get_portfolio),
        Tool(
            "get_prices",
            "Current USD prices for the given assets.",
            {"type": "object", "properties": {"assets": {"type": "array", "items": {"type": "string"}}}, "required": ["assets"]},
            get_prices,
        ),
        Tool("get_portfolio_valuation", "Total value and per-asset weights (computed).", _CUSTOMER_SCHEMA, get_portfolio_valuation),
        Tool("check_exposure_policy", "Per-asset exposure vs. the exposure policy limit.", _CUSTOMER_SCHEMA, check_exposure_policy),
        Tool("calculate_management_fee", "Estimated management fee for the next quarter.", _CUSTOMER_SCHEMA, calculate_management_fee),
        Tool(
            "search_knowledge_base",
            "Search policy and research documents. Cite results as [docId].",
            {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            search_knowledge_base,
        ),
    ]
}


def call_tool(name: str, pm_id: str, **args: Any) -> dict:
    """Single entry point so identity is always injected by code, never chosen by the model."""
    return TOOLS[name].fn(pm_id, **args)
