import pytest

pytestmark = pytest.mark.integration


def test_health_and_openapi(client):
    assert client.get("/health").json()["demo_mode"] is True
    ready = client.get("/health/ready").json()
    assert ready["status"] == "ready" and ready["checks"]["plugins"]["enabled"] == 12
    paths = client.get("/openapi.json").json()["paths"]
    for p in (
        "/api/v1/auth/login",
        "/api/v1/products/search",
        "/api/v1/ai/chat",
        "/api/v1/plugins/{plugin_id}/enable",
        "/api/v1/admin/approvals",
        "/api/v1/orders/{order_id}/tracking",
    ):
        assert p in paths


def test_auth_flow(client):
    r = client.post("/api/v1/auth/register", json={"email": "new.user@example.com", "password": "Str0ngPass!", "full_name": "New User"})
    assert r.status_code == 201
    tokens = r.json()
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}).json()
    assert me["email"] == "new.user@example.com" and me["roles"] == ["CUSTOMER"]
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 200
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]}).status_code == 401  # wrong type
    assert client.post("/api/v1/auth/login", json={"email": "asha@nextbot.demo", "password": "wrong"}).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/register", json={"email": "asha@nextbot.demo", "password": "Str0ngPass!", "full_name": "Asha Again"}
        ).status_code
        == 409
    )  # duplicate email
    assert client.get("/api/v1/cart").status_code == 401


def test_product_search_filters(client):
    r = client.get("/api/v1/products", params={"category": "footwear", "colour": "black", "variant_size": "9", "max_price": 3000})
    names = [p["name"] for p in r.json()["items"]]
    assert names == ["Stridex Velocity Run"]
    # regression: `size` is the PAGE size — the catalogue page sends size=24 and must still list products
    page = client.get("/api/v1/products/search", params={"size": 24}).json()
    assert page["total"] >= 20 and len(page["items"]) == min(24, page["total"])
    laptops = client.get("/api/v1/products/search", params={"category": "laptops", "max_price": 60000}).json()["items"]
    assert laptops and all(float(p["price"]) <= 60000 for p in laptops)
    sem = client.get("/api/v1/products/search", params={"q": "noise cancelling headphones", "semantic": True}).json()["items"]
    assert sem and sem[0]["category"] == "audio"
    detail = client.get(f"/api/v1/products/{laptops[0]['id']}").json()
    assert detail["specifications"]["RAM"] and detail["variants"]
    assert client.get("/api/v1/products/99999").status_code == 404


def test_sql_injection_attempt_is_inert(client):
    r = client.get("/api/v1/products", params={"q": "' OR 1=1; DROP TABLE products; --"})
    assert r.status_code == 200 and r.json()["items"] == []
    assert client.get("/api/v1/products").json()["total"] >= 20


def test_catalog_write_requires_role(client, asha, inventory_mgr):
    body = {
        "name": "Test Socks",
        "brand_id": 4,
        "category_id": 5,
        "price": 299,
        "mrp": 399,
        "variants": [{"sku": "TST-SOCK-1", "size": "M", "colour": "black", "initial_stock": 3}],
    }
    assert client.post("/api/v1/products", json=body, headers=asha).status_code == 403
    r = client.post("/api/v1/products", json=body, headers=inventory_mgr)
    assert r.status_code == 201 and r.json()["variants"][0]["stock_available"] == 3
