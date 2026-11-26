"""Talk to a running NextBot backend over MCP (Streamable HTTP) with the official SDK.

    pip install "mcp>=2.3" httpx
    python scripts/mcp_client_demo.py --email asha@nextbot.demo --password Demo@1234
"""
from __future__ import annotations

import argparse
import asyncio
import json

import httpx
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


async def main(base: str, email: str, password: str) -> None:
    token = httpx.post(f"{base}/api/v1/auth/login", json={"email": email, "password": password}, timeout=10).json()["access_token"]
    http = httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=30)
    async with Client(streamable_http_client(f"{base}/mcp/", http_client=http)) as client:
        tools = await client.list_tools()
        print("tools:", [t.name for t in tools.tools])
        res = await client.call_tool("search_products", {"category": "footwear", "colour": "black", "max_price": 3000})
        print(json.dumps(res.structured_content, indent=2)[:1500])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--email", default="asha@nextbot.demo")
    ap.add_argument("--password", default="Demo@1234")
    a = ap.parse_args()
    asyncio.run(main(a.base, a.email, a.password))
