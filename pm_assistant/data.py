"""Mock source systems. In production these come from the existing .NET APIs via the MCP server."""
from decimal import Decimal

PORTFOLIOS: dict[str, dict] = {
    "C-1042": {
        "customerId": "C-1042",
        "riskProfile": "medium",
        "holdings": [
            {"asset": "BTC", "quantity": Decimal("0.85"), "avgCostUsd": Decimal("41200")},
            {"asset": "ETH", "quantity": Decimal("12.4"), "avgCostUsd": Decimal("2350")},
            {"asset": "USDC", "quantity": Decimal("15000"), "avgCostUsd": Decimal("1")},
        ],
        "lastUpdated": "2026-09-30T16:00:00Z",
    },
}

PRICES_USD: dict[str, Decimal] = {"BTC": Decimal("63000"), "ETH": Decimal("2900"), "USDC": Decimal("1")}
PRICES_AS_OF = "2026-09-30T16:00:00Z"

# Which customers each portfolio manager may see. Mirrors the SSO/JWT → customer mapping.
ENTITLEMENTS: dict[str, set[str]] = {"PM-001": {"C-1042"}}

# Policy parameters, kept next to the documents that state them so they stay in sync.
STABLECOINS = {"USDC"}
EXPOSURE_LIMIT_PCT = {"medium": Decimal("60")}
ANNUAL_FEE_PCT = Decimal("0.8")

DOCUMENTS: dict[str, dict[str, str]] = {
    "POL-EXPOSURE": {
        "title": "מדיניות חשיפה",
        "text": "מדיניות חשיפה: בפרופיל סיכון בינוני, נכס בודד שאינו מטבע יציב לא יעלה על 60% משווי התיק הדיגיטלי.",
    },
    "POL-FEES": {
        "title": "דמי ניהול",
        "text": "דמי ניהול: 0.8% בשנה משווי הנכסים הדיגיטליים, נגבים רבעונית.",
    },
    "POL-ADVICE": {
        "title": "מדיניות ייעוץ",
        "text": 'מדיניות ייעוץ: העוזר אינו ממליץ על פעולות. לשאלות מסוג "כדאי לי לקנות/למכור" יש להפנות ליועץ מורשה.',
    },
    "RES-2026-09": {
        "title": "סקירת שוק, ספטמבר 2026",
        "text": "סקירת שוק, ספטמבר 2026 (פיקטיבית): התנודתיות של ETH עלתה ברבעון האחרון, נפחי המסחר במטבעות יציבים נשארו יציבים.",
    },
}
