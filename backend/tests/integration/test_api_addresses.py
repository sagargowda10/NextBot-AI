import pytest

pytestmark = pytest.mark.integration

BASE = "/api/v1/auth/me/addresses"


def addr(label, **kw):
    return {"label": label, "line1": "12 MG Road", "city": "Mysuru", "state": "Karnataka", "pincode": "570001", "phone": "9876543210", **kw}


def new_customer(client, email):
    reg = client.post("/api/v1/auth/register", json={"email": email, "password": "Newbie@1234", "full_name": "New Customer"})
    assert reg.status_code == 201, reg.text
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


def test_address_book_crud_and_single_default(client, asha):
    h = new_customer(client, "addr.owner@nextbot.demo")
    home = client.post(BASE, json=addr("Home"), headers=h)
    assert home.status_code == 201 and home.json()["is_default"] is True  # first address is the default

    work = client.post(BASE, json=addr("Work", is_default=True), headers=h).json()
    rows = client.get(BASE, headers=h).json()
    assert [a["label"] for a in rows if a["is_default"]] == ["Work"] and rows[0]["label"] == "Work"

    assert client.post(BASE, json=addr("Work"), headers=h).status_code == 409  # duplicate label
    assert client.post(BASE, json=addr("Bad", pincode="012345"), headers=h).status_code == 422  # invalid PIN

    upd = client.put(f"{BASE}/{work['id']}", json=addr("Work", city="Bengaluru", is_default=True), headers=h).json()
    assert upd["city"] == "Bengaluru"

    hid = home.json()["id"]
    assert client.post(f"{BASE}/{hid}/default", headers=h).json()["is_default"] is True
    assert client.delete(f"{BASE}/{hid}", headers=h).status_code == 204
    left = client.get(BASE, headers=h).json()
    assert [a["label"] for a in left] == ["Work"] and left[0]["is_default"] is True  # default re-assigned

    # another customer can't read or change it
    assert client.delete(f"{BASE}/{work['id']}", headers=asha).status_code == 404
    assert client.put(f"{BASE}/{work['id']}", json=addr("X"), headers=asha).status_code == 404


def test_checkout_uses_new_default_address(client):
    h = new_customer(client, "addr.buyer@nextbot.demo")
    no_addr = client.post("/api/v1/orders", json={"payment_method": "mock_upi"}, headers=h)
    assert no_addr.status_code in (400, 409, 422)  # empty cart or missing address — never an order
    client.post(BASE, json=addr("Home", pincode="560034"), headers=h)
    item = next(p for p in client.get("/api/v1/products", params={"size": 50}).json()["items"] if p["in_stock"])
    v = next(v for v in item["variants"] if v["stock_available"] > 0)
    client.post("/api/v1/cart/items", json={"variant_id": v["id"], "quantity": 1}, headers=h)
    order = client.post("/api/v1/orders", json={"payment_method": "mock_upi"}, headers=h).json()
    assert order["shipping_pincode"] == "560034"
