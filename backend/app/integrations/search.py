"""Optional OpenSearch backend for product search (SEARCH_BACKEND=opensearch).

PostgreSQL remains the source of truth; OpenSearch is a read-optimised index that adds fuzzy,
multi-field relevance ranking. Results are returned as product IDs and hydrated from the DB.
"""

from __future__ import annotations

from typing import Any

from app.schemas.catalog import ProductFilter

INDEX = "nextbot-products"


class OpenSearchProductIndex:
    def __init__(self, url: str) -> None:
        self.url = url.rstrip("/")

    async def _req(self, method: str, path: str, json: Any = None) -> Any:
        import httpx

        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.request(method, f"{self.url}/{path}", json=json)
            r.raise_for_status()
            return r.json()

    async def index_products(self, docs: list[dict[str, Any]]) -> None:
        for d in docs:
            await self._req("PUT", f"{INDEX}/_doc/{d['id']}", d)
        await self._req("POST", f"{INDEX}/_refresh")

    async def search_ids(self, f: ProductFilter) -> list[int]:
        must: list[dict[str, Any]] = []
        filt: list[dict[str, Any]] = [{"term": {"is_active": True}}]
        if f.query:
            must.append({"multi_match": {"query": f.query, "fields": ["name^3", "tags^2", "description"], "fuzziness": "AUTO"}})
        if f.category:
            filt.append({"term": {"category": f.category}})
        if f.brand:
            filt.append({"term": {"brand": f.brand}})
        if f.colour:
            filt.append({"term": {"colours": f.colour}})
        if f.size:
            filt.append({"term": {"sizes": f.size}})
        rng = {k: float(v) for k, v in (("gte", f.min_price), ("lte", f.max_price)) if v is not None}
        if rng:
            filt.append({"range": {"price": rng}})
        body = {
            "query": {"bool": {"must": must or [{"match_all": {}}], "filter": filt}},
            "size": f.limit,
            "from": f.offset,
            "_source": False,
        }
        res = await self._req("POST", f"{INDEX}/_search", body)
        return [int(h["_id"]) for h in res["hits"]["hits"]]
