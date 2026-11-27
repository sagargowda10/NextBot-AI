import pytest

pytestmark = pytest.mark.integration


def test_order_workflow_trace_for_admin(client, rahul, admin):
    item = next(p for p in client.get("/api/v1/products", params={"size": 50}).json()["items"] if p["in_stock"])
    v = next(v for v in item["variants"] if v["stock_available"] > 0)
    client.post("/api/v1/cart/items", json={"variant_id": v["id"], "quantity": 1}, headers=rahul)
    order = client.post("/api/v1/orders", json={"payment_method": "mock_upi"}, headers=rahul).json()

    r = client.get(f"/api/v1/admin/orders/{order['id']}/workflow", headers=admin)
    assert r.status_code == 200, r.text
    wf = r.json()
    nodes = {n["id"]: n for n in wf["nodes"]}
    assert len(nodes) == 13 and len(wf["edges"]) == 12
    assert nodes["checkout"]["status"] == "done" and nodes["checkout"]["details"]["order_number"] == order["order_number"]
    assert nodes["payment"]["status"] == "done" and "SUCCEEDED" in nodes["payment"]["summary"]
    assert nodes["inventory"]["status"] == "done"
    assert nodes["return"]["status"] == "skipped"
    assert nodes["n8n"]["status"] == "skipped"  # not configured in tests
    assert wf["timeline"][0]["title"] == "Order created"
    assert {e["source"] for e in wf["edges"]} <= set(nodes)

    status = client.get("/api/v1/admin/workflows/n8n", headers=admin).json()
    assert status["configured"] is False and status["editor_url"]


def test_workflow_is_staff_only(client, rahul, admin):
    oid = client.get("/api/v1/orders", headers=rahul).json()["items"][0]["id"]
    assert client.get(f"/api/v1/admin/orders/{oid}/workflow", headers=rahul).status_code == 403
    assert client.get("/api/v1/admin/orders/999999/workflow", headers=admin).status_code == 404
