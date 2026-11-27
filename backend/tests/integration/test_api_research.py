import pytest

pytestmark = pytest.mark.integration


def test_admin_research_demo_mode_uses_store_data(client, admin):
    status = client.get("/api/v1/admin/research/status", headers=admin).json()
    assert status["provider"] == "mock"
    r = client.post("/api/v1/admin/research", json={"question": "How are our sales this month?"}, headers=admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["store_used"] is True and body["provider"] == "mock" and "Revenue" in body["answer"]
    assert body["answer"].count("\n- ") >= 3  # point-wise
    general = client.post("/api/v1/admin/research", json={"question": "Latest GST rate news?"}, headers=admin).json()
    assert general["store_used"] is False and "OpenAI API key" in general["answer"] and general["notice"]


def test_research_is_admin_only(client, rahul, inventory_mgr):
    for headers in (rahul, inventory_mgr):  # customers and non-admin staff are refused
        assert client.post("/api/v1/admin/research", json={"question": "hello there"}, headers=headers).status_code == 403
