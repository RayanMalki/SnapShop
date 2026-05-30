"""UCP client — talks MCP Streamable HTTP directly to Shopify's global catalog.

Bypasses @shopify/ucp-cli@0.6.0, whose Ajv (draft-07) validator rejects
the `$schema: https://json-schema.org/draft/2020-12/schema` declared by the
global catalog server's tool input schemas (MCP_INVALID_RESPONSE).

We speak the same JSON-RPC over HTTP that the CLI does, minus the strict
client-side schema validation. The payload shape comes from
https://shopify.dev/ucp/schemas/2026-04-08/shopify_catalog_global.json.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

import httpx

from config import settings
from models.schemas import Product

logger = logging.getLogger(__name__)

CATALOG_MCP_URL = "https://catalog.shopify.com/api/ucp/mcp"
# Public demo agent profile baked into @shopify/ucp-cli; works out of the box
# until we host our own at https://snapshop.dev/.well-known/ucp-agent.json.
DEFAULT_AGENT_PROFILE_URL = "https://www.igvita.com/ucp/profile.json"

_MOCK_PRODUCT = Product(
    variant_id="gid://shopify/ProductVariant/41293818167385",
    title="Sony WH-CH520 Wireless Bluetooth Headphones (mock)",
    price_min=5999,
    price_max=5999,
    currency="USD",
    image_url="https://placehold.co/512x512/png?text=Mock+Product",
    merchant_domain="audiogear.example.com",
    merchant_url="https://audiogear.example.com",
    checkout_url="https://audiogear.example.com/cart/41293818167385:1",
)


def _agent_profile_url() -> str:
    return settings.ucp_agent_profile_url or DEFAULT_AGENT_PROFILE_URL


# ---------------------------------------------------------------------------
# Minimal MCP Streamable HTTP client
# ---------------------------------------------------------------------------


class MCPClient:
    """Single-shot UCP-over-MCP client.

    Matches what @shopify/ucp-cli's `mcp-client.ts` actually does: one
    JSON-RPC POST per call, `Accept: application/json`, no session lifecycle,
    no `initialize`, no SSE. UCP discovery on the server runs on the first
    `tools/*` call, keyed off `meta.ucp-agent.profile` inside `params.arguments`.

    Intentionally skips client-side `inputSchema` validation (the bug that
    breaks the CLI today) — the server is the source of truth.
    """

    def __init__(self, endpoint: str, *, timeout: float = 30.0) -> None:
        self.endpoint = endpoint
        self._client = httpx.AsyncClient(timeout=timeout)
        self._next_id = 0

    def _make_id(self) -> int:
        self._next_id += 1
        return self._next_id

    async def _rpc(
        self, method: str, params: dict[str, Any] | None = None
    ) -> Any:
        request_id = self._make_id()
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        resp = await self._client.post(
            self.endpoint,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            body = resp.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"MCP HTTP {resp.status_code}: non-JSON body: {resp.text[:300]}"
            ) from exc
        if "error" in body:
            err = body["error"]
            raise RuntimeError(
                f"MCP RPC error ({err.get('code')}): {err.get('message')} "
                f"data={err.get('data')}"
            )
        return body.get("result", {})

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._rpc(
            "tools/call", {"name": name, "arguments": arguments}
        )

    async def list_tools(
        self, profile_url: str | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] | None = None
        if profile_url:
            params = {
                "arguments": {
                    "meta": {"ucp-agent": {"profile": profile_url}}
                }
            }
        return await self._rpc("tools/list", params)

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "MCPClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()


# ---------------------------------------------------------------------------
# Public API used by the pipeline
# ---------------------------------------------------------------------------


async def search_catalog(query: str) -> Product | None:
    """Search the Shopify global catalog and return the top product."""
    if settings.use_mock_ucp:
        logger.info("UCP mock mode — returning placeholder product for %r", query)
        return _MOCK_PRODUCT

    arguments = {
        "meta": {"ucp-agent": {"profile": _agent_profile_url()}},
        "catalog": {
            "query": query,
            "context": {"address_country": "US"},
            "pagination": {"limit": 5},
        },
    }

    try:
        async with MCPClient(CATALOG_MCP_URL) as client:
            result = await client.call_tool("search_catalog", arguments)
    except Exception:
        logger.exception("UCP search_catalog failed; falling back to mock")
        return _MOCK_PRODUCT

    product = _first_product(result)
    if product is None:
        logger.warning("UCP search returned no products for %r", query)
    return product


async def create_cart(variant_id: str, merchant_url: str) -> tuple[str, str]:
    """Construct a one-click cart URL for the given variant.

    For the hackathon we hand off to the merchant's existing `/cart/{variant}:1`
    deep-link instead of negotiating a per-merchant UCP session (which not every
    Shopify shop has enabled). This matches the `buy` column in the UCP catalog
    search output.
    """
    var_num = variant_id.rsplit("/", 1)[-1] if variant_id else ""
    if not merchant_url or not var_num:
        raise NotImplementedError(
            "Cannot construct cart URL without merchant and variant ids"
        )
    base = merchant_url.rstrip("/")
    continue_url = f"{base}/cart/{var_num}:1"
    cart_id = f"deeplink-{uuid.uuid4().hex[:12]}"
    return continue_url, cart_id


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _first_product(tool_result: dict[str, Any]) -> Product | None:
    structured = _structured_content(tool_result)
    products = structured.get("products") if structured else None
    if not products:
        return None

    raw = products[0]
    variants = raw.get("variants") or []
    variant = variants[0] if variants else {}

    variant_id = variant.get("id") or raw.get("id") or ""

    price = variant.get("price") or {}
    if not price:
        price_range = raw.get("price_range") or {}
        price = price_range.get("min") or price_range.get("max") or {}
    amount = _to_minor_units(price.get("amount"))
    currency = price.get("currency") or "USD"

    price_range = raw.get("price_range") or {}
    price_min = _to_minor_units((price_range.get("min") or {}).get("amount")) or amount
    price_max = _to_minor_units((price_range.get("max") or {}).get("amount")) or amount

    image_url = _first_media_url(variant.get("media")) or _first_media_url(
        raw.get("media")
    ) or "https://placehold.co/512x512/png?text=Product"

    seller = variant.get("seller") or {}
    merchant_domain = seller.get("domain") or ""
    merchant_url = seller.get("url") or (
        f"https://{merchant_domain}" if merchant_domain else ""
    )

    checkout_url = variant.get("checkout_url") or _build_deeplink(
        merchant_url, variant_id
    )

    return Product(
        variant_id=variant_id,
        title=raw.get("title") or "Untitled",
        price_min=price_min,
        price_max=price_max,
        currency=currency,
        image_url=image_url,
        merchant_domain=merchant_domain or _domain_from_url(merchant_url),
        merchant_url=merchant_url or checkout_url,
        checkout_url=checkout_url or None,
    )


def _structured_content(tool_result: dict[str, Any]) -> dict[str, Any] | None:
    if not tool_result:
        return None
    sc = tool_result.get("structuredContent")
    if isinstance(sc, dict):
        return sc
    # Fallback: some servers stuff JSON into the text content block.
    for block in tool_result.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            try:
                return json.loads(block.get("text") or "")
            except (json.JSONDecodeError, TypeError):
                continue
    return None


def _first_media_url(media: list[Any] | None) -> str | None:
    if not media:
        return None
    for item in media:
        if isinstance(item, dict):
            url = item.get("url")
            if url:
                return url
        elif isinstance(item, str):
            return item
    return None


def _to_minor_units(amount: Any) -> int:
    """UCP returns amounts in ISO 4217 minor units already (cents).

    Some servers send them as ints, some as strings. Be lenient.
    """
    if amount is None:
        return 0
    if isinstance(amount, bool):
        return 0
    if isinstance(amount, int):
        return amount
    if isinstance(amount, float):
        return int(round(amount))
    if isinstance(amount, str):
        try:
            return int(amount)
        except ValueError:
            try:
                return int(round(float(amount)))
            except ValueError:
                return 0
    return 0


def _build_deeplink(merchant_url: str, variant_id: str) -> str:
    if not merchant_url or not variant_id:
        return ""
    var_num = variant_id.rsplit("/", 1)[-1]
    return f"{merchant_url.rstrip('/')}/cart/{var_num}:1"


def _domain_from_url(url: str) -> str:
    if not url:
        return ""
    stripped = url.split("://", 1)[-1]
    return stripped.split("/", 1)[0]


# ---------------------------------------------------------------------------
# Manual smoke test: `python -m services.ucp "wireless headphones"`
# ---------------------------------------------------------------------------


if __name__ == "__main__":  # pragma: no cover
    import sys

    async def _main() -> None:
        query = " ".join(sys.argv[1:]) or "wireless headphones under $100"
        prev = settings.use_mock_ucp
        settings.use_mock_ucp = False
        try:
            product = await search_catalog(query)
        finally:
            settings.use_mock_ucp = prev
        print(json.dumps(product.model_dump() if product else None, indent=2))

    asyncio.run(_main())
