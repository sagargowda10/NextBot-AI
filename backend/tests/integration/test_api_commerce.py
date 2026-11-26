import time

import pytest

pytestmark = pytest.mark.integration


def variant_of(client, name):
    items = client.get("/api/v1/products", params={"q": name.split()[-1]}).json()["items"]
    p = next(i for i in items if i["name"] == name)
    return next(v for v in p["variants"] if v["stock_available"] > 0)


def test_cart_operations_and_stock_validation(client, rahul):
    v = variant_of(client, "Auralis Boom Mini")
    cart = client.post("/api/v1/cart/items", json={"variant_id": v["id"], "quantity": 2}, headers=rahul).json()
    item = cart["items"][0]
    assert item["quantity"] == 2 and float(cart["total"]) == float(item["unit_price"]) * 2
    upd = client.put(f"/api/v1/cart/items/{item['id']}", json={"quantity": 1}, headers=rahul).json()
    assert upd["items"][0]["quantity"] == 1
    too_many = client.put(f"/api/v1/cart/items/{item['id']}", json={"quantity": 11}, headers=rahul)
    assert too_many.status_code == 422
    assert client.delete(f"/api/v1/cart/items/{item['id']}", headers=rahul).json()["items"] == []


def test_checkout_mock_payment_success_and_fulfilment(client, rahul):
    v = variant_of(client, "Nimbus Band 8")
    before = v["stock_available"]
    client.post("/api/v1/cart/items", json={"variant_id": v["id"], "quantity": 1}, headers=rahul)
    order = client.post("/api/v1/orders", json={"payment_method": "mock_upi"}, headers=rahul).json()
    assert order["status"] in ("CONFIRMED", "PROCESSING") and order["payment_status"] == "SUCCEEDED"
    for _ in range(20):  # outbox relay → PaymentSuccessful → fulfilment consumer creates the shipment
        tracking = client.get(f"/api/v1/orders/{order['id']}/tracking", headers=rahul).json()
        if tracking:
            break
        time.sleep(0.25)
    assert tracking and tracking["status"] == "CREATED" and tracking["is_simulated"]
    assert variant_of(client, "Nimbus Band 8")["stock_available"] == before - 1


def test_payment_failure_retry_and_idempotency(client, rahul):
    v = variant_of(client, "HearthCo Electric Kettle 1.5L")
    client.post("/api/v1/cart/items", json={"variant_id": v["id"], "quantity": 1}, headers=rahul)
    order = client.post("/api/v1/orders", json={"payment_method": "mock_fail"}, headers=rahul).json()
    assert order["status"] == "PAYMENT_PENDING" and order["payment_status"] == "FAILED"
    body = {"order_id": order["id"], "method": "mock_upi", "idempotency_key": f"retry-{order['id']}-abc"}
    p1 = client.post("/api/v1/payments/initiate", json=body, headers=rahul).json()
    p2 = client.post("/api/v1/payments/initiate", json=body, headers=rahul).json()
    assert p1["id"] == p2["id"] and p1["status"] == "SUCCEEDED"  # replay returns the same payment
    assert client.get(f"/api/v1/orders/{order['id']}", headers=rahul).json()["status"] in ("CONFIRMED", "PROCESSING")


def test_three_failed_payments_cancel_and_release_stock(client, rahul):
    v = variant_of(client, "HearthCo Air Fryer 4L")
    before = v["stock_available"]
    client.post("/api/v1/cart/items", json={"variant_id": v["id"], "quantity": 1}, headers=rahul)
    order = client.post("/api/v1/orders", json={"payment_method": "mock_fail"}, headers=rahul).json()
    for i in range(2):
        client.post(
            "/api/v1/payments/initiate",
            json={"order_id": order["id"], "method": "mock_fail", "idempotency_key": f"fail-{order['id']}-{i}-key"},
            headers=rahul,
        )
    assert client.get(f"/api/v1/orders/{order['id']}", headers=rahul).json()["status"] == "CANCELLED"
    assert variant_of(client, "HearthCo Air Fryer 4L")["stock_available"] == before


def test_orders_are_private(client, asha, rahul):
    rahul_order = client.get("/api/v1/orders", headers=rahul).json()["items"][0]
    assert client.get(f"/api/v1/orders/{rahul_order['id']}", headers=asha).status_code == 404
    assert client.get(f"/api/v1/orders/{rahul_order['id']}/tracking", headers=asha).status_code == 404


def test_webhook_rejects_bad_signature(client):
    r = client.post(
        "/api/v1/payments/webhook",
        content=b'{"event_id":"x","provider_reference":"y","status":"SUCCEEDED"}',
        headers={"X-NextBot-Signature": "t=1,v1=deadbeef"},
    )
    assert r.status_code == 401


def test_returns_eligibility(client, asha, rahul):
    r = client.post("/api/v1/returns", json={"reason": "Size too small"}, headers=asha).json()
    assert r["eligible"] and r["status"] == "APPROVED"
    again = client.post("/api/v1/returns", json={"order_id": r["order_id"], "reason": "again"}, headers=asha).json()
    assert not again["eligible"] and "already" in again["eligibility_message"]
