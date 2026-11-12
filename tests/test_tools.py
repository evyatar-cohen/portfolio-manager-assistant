from decimal import Decimal

import pytest

from pm_assistant.tools import ACCESS_DENIED, TOOLS, ToolError, call_tool

PM = "PM-001"


def test_total_value():
    assert call_tool("get_portfolio_valuation", PM, customer_id="C-1042")["totalValueUsd"] == Decimal("104510.00")


def test_weights():
    positions = call_tool("get_portfolio_valuation", PM, customer_id="C-1042")["positions"]
    assert {p["asset"]: p["weightPct"] for p in positions} == {
        "BTC": Decimal("51.24"),
        "ETH": Decimal("34.41"),
        "USDC": Decimal("14.35"),
    }


def test_no_exposure_breach_and_stablecoin_exempt():
    result = call_tool("check_exposure_policy", PM, customer_id="C-1042")
    assert result["anyBreach"] is False
    usdc = next(a for a in result["assets"] if a["asset"] == "USDC")
    assert usdc["subjectToLimit"] is False


def test_quarterly_fee():
    assert call_tool("calculate_management_fee", PM, customer_id="C-1042")["quarterlyFeeUsd"] == Decimal("209.02")


def test_prices():
    assert call_tool("get_prices", PM, assets=["BTC", "ETH"])["pricesUsd"] == {"BTC": Decimal("63000"), "ETH": Decimal("2900")}


@pytest.mark.parametrize("name", [n for n, t in TOOLS.items() if "customer_id" in t.schema["properties"]])
@pytest.mark.parametrize("pm, customer", [("PM-001", "C-2000"), ("PM-999", "C-1042")])
def test_not_found_and_unauthorized_are_indistinguishable(name, pm, customer):
    with pytest.raises(ToolError) as exc:
        call_tool(name, pm, customer_id=customer)
    assert str(exc.value) == ACCESS_DENIED


@pytest.mark.parametrize("name, args", [("get_prices", {"assets": ["BTC"]}), ("search_knowledge_base", {"query": "ETH"})])
def test_unknown_pm_rejected_by_non_customer_tools(name, args):
    with pytest.raises(ToolError, match=ACCESS_DENIED):
        call_tool(name, "PM-999", **args)
