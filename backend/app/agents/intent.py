"""Intent classification + entity extraction.

`RuleBasedIntentParser` powers the mock AI provider (demo mode). The OpenAI provider returns
the same `IntentResult` via function calling, so the rest of the pipeline is provider-agnostic.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

INTENTS = (
    "greeting",
    "product_search",
    "recommend",
    "product_details",
    "compare_products",
    "add_to_cart",
    "view_cart",
    "remove_from_cart",
    "checkout",
    "track_order",
    "order_history",
    "cancel_order",
    "return_request",
    "return_status",
    "faq",
    "general",
    "payment_issue",
    "delivery_estimate",
    "low_stock",
    "inventory_check",
    "sales_report",
    "plugin_status",
    "agent_executions",
    "escalate",
    "unknown",
)


class IntentResult(BaseModel):
    intent: str = Field(description="One of the supported intents")
    entities: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0


CATEGORY_SYNONYMS: dict[str, tuple[str, ...]] = {
    "laptops": ("laptop", "laptops", "notebook", "ultrabook", "macbook"),
    "smartphones": ("smartphone", "smartphones", "phone", "phones", "mobile", "mobiles"),
    "audio": ("headphone", "headphones", "earbuds", "earphones", "speaker", "speakers", "headset"),
    "footwear": ("shoe", "shoes", "sneaker", "sneakers", "trainers", "footwear", "boots"),
    "apparel": ("t-shirt", "tshirt", "shirt", "shirts", "hoodie", "jacket", "joggers", "apparel"),
    "wearables": ("smartwatch", "watch", "watches", "fitness band", "band", "wearable"),
    "home-kitchen": ("kettle", "mixer", "grinder", "cookware", "air fryer", "kitchen"),
}
COLOURS = ("black", "white", "blue", "red", "grey", "gray", "green", "navy", "silver", "pink", "beige", "yellow", "orange")
QUERY_HINTS = ("running", "gaming", "wireless", "noise cancelling", "trail", "casual", "office", "5g", "ultralight", "cotton")
BRANDS = ("voltix", "nimbus", "auralis", "stridex", "hearthco")
ORDINALS = {
    "first": 1,
    "1st": 1,
    "second": 2,
    "2nd": 2,
    "third": 3,
    "3rd": 3,
    "fourth": 4,
    "4th": 4,
    "fifth": 5,
    "5th": 5,
    "last": -1,
    "cheapest": "cheapest",
    "that": 1,
    "this": 1,
    "it": 1,
}

SORT_HINTS: list[tuple[str, str]] = [
    (r"\b(cheapest|lowest[- ]?(price|priced|cost)|least expensive|most affordable|low(est)? to high|budget[- ]friendly)\b", "price_asc"),
    (r"\b(most expensive|costliest|priciest|highest[- ]?(price|priced|cost)|premium|high(est)? to low)\b", "price_desc"),
    (r"\b(top[- ]rated|best[- ]rated|highest[- ]rated|best reviewed|most popular|best[- ]selling|bestsellers?)\b", "rating"),
    (r"\b(newest|latest|new arrivals?|recently added)\b", "newest"),
]

_NUM = r"(?:₹|rs\.?|inr)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(k|lakh|l)?"


def _amount(num: str, suffix: str | None) -> float:
    n = float(num.replace(",", ""))
    if suffix in ("k",):
        n *= 1_000
    elif suffix in ("lakh", "l"):
        n *= 100_000
    return n


def extract_entities(text: str) -> dict[str, Any]:
    t = text.lower()
    ents: dict[str, Any] = {}
    if m := re.search(r"(?:under|below|less than|within|upto|up to|max(?:imum)?|budget(?: of)?|<)\s*" + _NUM, t):
        ents["max_price"] = _amount(m.group(1), m.group(2))
    if m := re.search(r"(?:above|over|more than|at least|min(?:imum)?|>)\s*" + _NUM, t):
        ents["min_price"] = _amount(m.group(1), m.group(2))
    if m := re.search(r"between\s*" + _NUM + r"\s*(?:and|-|to)\s*" + _NUM, t):
        ents["min_price"], ents["max_price"] = _amount(m.group(1), m.group(2)), _amount(m.group(3), m.group(4))
    if m := re.search(r"\b(?:size|uk|us|eu)\s*([0-9]{1,2}(?:\.5)?|xs|s|m|l|xl|xxl)\b", t):
        ents["size"] = m.group(1).upper() if m.group(1).isalpha() else m.group(1)
    for colour in COLOURS:
        if re.search(rf"\b{colour}\b", t):
            ents["colour"] = "grey" if colour == "gray" else colour
            break
    for slug, words in CATEGORY_SYNONYMS.items():
        if any(re.search(rf"\b{re.escape(w)}\b", t) for w in words):
            ents["category"] = slug
            break
    for b in BRANDS:
        if re.search(rf"\b{b}\b", t):
            ents["brand"] = b
    hints = [h for h in QUERY_HINTS if h in t]
    if hints:
        ents["query"] = " ".join(hints)
    for word, val in ORDINALS.items():
        if re.search(rf"\b{re.escape(word)}\b", t):
            ents["ordinal"] = val
            break
    if m := re.search(r"(?:#|number|item|product)\s*([0-9]{1,2})\b", t):
        ents["ordinal"] = int(m.group(1))
    if m := re.search(r"\b(?:qty|quantity|x)\s*([0-9]{1,2})\b|\b([0-9]{1,2})\s*(?:pcs|pieces|units)\b", t):
        ents["quantity"] = int(m.group(1) or m.group(2))
    if m := re.search(r"\b([1-9][0-9]{5})\b", t):
        ents["pincode"] = m.group(1)
    if m := re.search(r"\b(nb-[0-9a-z-]{4,})\b", t):
        ents["order_number"] = m.group(1).upper()
    if m := re.search(r"\b(today|yesterday|this week|last week|this month|last month|last 7 days|last 30 days|this year)\b", t):
        ents["period"] = m.group(1)
    if any(w in t for w in ("delivery", "deliver", "shipping time", "arrive", "when will")):
        ents["wants_delivery"] = True
    if any(w in t for w in ("availability", "available", "in stock", "stock")):
        ents["wants_stock"] = True
    for pattern, order in SORT_HINTS:
        if re.search(pattern, t):
            ents["sort"] = order
            break
    if m := re.search(r"coupon\s+([a-z0-9]{3,20})", t):
        ents["coupon_code"] = m.group(1).upper()
    return ents


_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("agent_executions", re.compile(r"\b(agent|agents)\b.*\b(execution|executions|runs|activity|logs?)\b|\brecent (ai )?agent", re.I)),
    ("plugin_status", re.compile(r"\bplugins?\b.*\b(status|health|enabled|list|all)\b|\bstatus of (all )?plugins?\b", re.I)),
    ("sales_report", re.compile(r"\b(sales|revenue|turnover|gmv)\b", re.I)),
    (
        "low_stock",
        re.compile(
            r"\b(low|running out|out of)\b.{0,15}\b(stock|inventory)\b|\blow[- ]stock\b|\binventory\b.{0,20}\blow\b|\bproducts? with low",
            re.I,
        ),
    ),
    ("return_status", re.compile(r"\b(status of|where is|track)\b.{0,20}\b(my )?(return|refund)\b", re.I)),
    (
        "faq",
        re.compile(
            r"\b(return|refund|exchange|warranty|shipping|delivery|cancellation|cod|cash on delivery|payment) (policy|policies|charges?|options?|methods?|terms|time)\b|\bwhat is your\b|\bhow (do|does|can|long)\b|\bdo you (offer|ship|accept)\b|\bstore (hours|timings?|address|location)\b",  # noqa: E501 - one readable regex
            re.I,
        ),
    ),
    (
        "return_request",
        re.compile(
            r"\b(return|send back|refund)\b.{0,25}\b(my |the |this )?(order|item|product|purchase|it)\b|\bi want (a )?(refund|to return)\b",
            re.I,
        ),
    ),
    ("cancel_order", re.compile(r"\bcancel\b.{0,20}\border\b", re.I)),
    ("track_order", re.compile(r"\b(track|where('s| is)|status of)\b.{0,25}\b(order|package|parcel|shipment|delivery)\b", re.I)),
    ("order_history", re.compile(r"\b(my|past|previous|recent) orders\b|\border history\b", re.I)),
    (
        "payment_issue",
        re.compile(r"\bpayment\b.{0,30}\b(failed|issue|problem|deducted|declined|stuck|pending)\b|\bmoney (deducted|debited)\b", re.I),
    ),
    ("checkout", re.compile(r"\b(place|confirm|complete|submit)\b.{0,15}\border\b|\bcheck ?out\b|\bbuy (it|now|this)\b|\bpay now\b", re.I)),
    ("remove_from_cart", re.compile(r"\b(remove|delete|drop)\b.{0,30}\b(cart|basket)\b", re.I)),
    ("add_to_cart", re.compile(r"\badd\b.{0,40}\b(cart|basket|bag)\b|\badd (it|this|that|the first|the second)\b", re.I)),
    ("view_cart", re.compile(r"\b(show|view|what'?s in|see)\b.{0,10}\b(my )?(cart|basket|bag)\b|^cart$", re.I)),
    ("inventory_check", re.compile(r"\b(stock|inventory) (level|levels|of|for)\b|\bwarehouse\b", re.I)),
    (
        "delivery_estimate",
        re.compile(r"\b(deliver|delivery|ship)\b.{0,20}\b(to|in|by)\b.{0,10}\b[1-9][0-9]{5}\b|\bhow long.{0,20}deliver", re.I),
    ),
    ("compare_products", re.compile(r"\bcompare\b|\bvs\.?\b|\bversus\b|\bdifference between\b", re.I)),
    ("recommend", re.compile(r"\b(recommend|suggest|suggestion|best .* for me|what should i buy|based on my)\b", re.I)),
    ("product_details", re.compile(r"\b(spec|specs|specifications|details|tell me more|features) (of|about|for)\b", re.I)),
    ("product_search", re.compile(r"\b(find|show|search|looking for|need|want|buy|get me|any)\b", re.I)),
    # "which is the lowest price product?", "cheapest item", "top rated products" - a sort order alone is a search
    (
        "product_search",
        re.compile(
            r"\b(cheapest|lowest[- ]?(price|priced|cost)|least expensive|most affordable|most expensive|costliest|priciest|"
            r"highest[- ]?(price|priced|cost)|top[- ]rated|best[- ]rated|highest[- ]rated|best[- ]selling|newest|latest)\b",
            re.I,
        ),
    ),
    ("escalate", re.compile(r"\b(human|real person|agent please|speak to (someone|support)|talk to (someone|support)|complaint)\b", re.I)),
    ("greeting", re.compile(r"^\s*(hi|hello|hey|namaste|good (morning|afternoon|evening))\b[\s!.]*$", re.I)),
]


class RuleBasedIntentParser:
    """Deterministic parser used in demo mode — fast, free and testable."""

    def parse(self, message: str) -> IntentResult:
        text = message.strip()
        ents = extract_entities(text)
        for intent, pattern in _RULES:
            if pattern.search(text):
                if intent == "product_search" and not ents.keys() & {"category", "query", "brand", "sort"}:
                    continue
                return IntentResult(intent=intent, entities=ents, confidence=0.85)
        if "category" in ents or "brand" in ents:
            return IntentResult(intent="product_search", entities=ents, confidence=0.6)
        return IntentResult(intent="faq", entities=ents, confidence=0.3)
