import pytest

from app.agents.intent import RuleBasedIntentParser, extract_entities

P = RuleBasedIntentParser()


@pytest.mark.parametrize(
    "msg,intent",
    [
        ("Find me a laptop under ₹60,000.", "product_search"),
        ("Show me black running shoes in size 9.", "product_search"),
        ("Recommend a smartphone based on my budget.", "recommend"),
        ("Add the first product to my cart.", "add_to_cart"),
        ("Place my order.", "checkout"),
        ("Track my latest order.", "track_order"),
        ("What is your return policy?", "faq"),
        ("Show products with low inventory.", "low_stock"),
        ("I want to return my order.", "return_request"),
        ("Show me this month's sales.", "sales_report"),
        ("Show me the status of all plugins.", "plugin_status"),
        ("Show me recent AI agent executions.", "agent_executions"),
        ("hello", "greeting"),
        ("Cancel my order", "cancel_order"),
        ("I want to talk to a human", "escalate"),
        ("How long does delivery take to 110001?", "faq"),
        ("Compare the first two", "compare_products"),
    ],
)
def test_demo_intents(msg, intent):
    assert P.parse(msg).intent == intent


def test_entities_for_spec_example():
    e = extract_entities("Find me black running shoes under ₹3,000 in size 9. Check availability and delivery.")
    assert e["category"] == "footwear" and e["colour"] == "black" and e["size"] == "9"
    assert e["max_price"] == 3000 and e["query"] == "running" and e["wants_delivery"] and e["wants_stock"]


def test_price_suffixes_and_ordinals():
    assert extract_entities("phones under 20k")["max_price"] == 20000
    assert extract_entities("laptop between 40000 and 1.2 lakh") == {"min_price": 40000, "max_price": 120000, "category": "laptops"}
    assert extract_entities("add the second one")["ordinal"] == 2
    assert extract_entities("this month's sales")["period"] == "this month"
