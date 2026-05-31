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
import math
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

from config import settings
from models.schemas import Product

logger = logging.getLogger(__name__)

CATALOG_MCP_URL = "https://catalog.shopify.com/api/ucp/mcp"
# Public demo agent profile baked into @shopify/ucp-cli; works out of the box
# until we host our own at https://snapshop.dev/.well-known/ucp-agent.json.
DEFAULT_AGENT_PROFILE_URL = "https://www.igvita.com/ucp/profile.json"


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


@dataclass
class Candidate:
    """A search hit plus the signals we need to re-rank it locally."""

    product: Product
    product_id: str  # UPID-style gid; clusters the same product across shops
    match_text: str  # title + seller + ML metadata, lowercased, for token overlap
    price_cents: int
    currency: str
    rank: int = 0  # original position in the server's relevance order
    score: float = field(default=0.0)
    proximity: float = field(default=0.0)  # price closeness to the vision estimate


async def search_catalog(
    query: str,
    *,
    limit: int = 15,
    price_min: int | None = None,
    price_max: int | None = None,
    ships_to_country: str | None = "US",
    currency: str | None = "USD",
    intent: str | None = None,
    available: bool = True,
    like_image_b64: str | None = None,
    like_image_mime: str | None = None,
) -> list[Candidate]:
    """Search the Shopify global catalog and return ranked-able candidates.

    Constraints are pushed into the structured request (``filters`` / ``context``)
    instead of the keyword string, because the catalog ignores natural-language
    qualifiers like "under $100". ``price_min`` / ``price_max`` are in minor
    units (cents). Returns candidates in the server's relevance order; call
    :func:`rank_candidates` to re-order against the vision attributes.
    """
    context: dict[str, Any] = {}
    if ships_to_country:
        context["address_country"] = ships_to_country
    if currency:
        context["currency"] = currency
    if intent:
        context["intent"] = intent

    filters: dict[str, Any] = {"available": available}
    price: dict[str, int] = {}
    if price_min is not None and price_min > 0:
        price["min"] = price_min
    if price_max is not None and price_max > 0:
        price["max"] = price_max
    if price:
        filters["price"] = price
    if ships_to_country:
        filters["ships_to"] = {"country": ships_to_country}

    catalog: dict[str, Any] = {
        "query": query,
        "context": context,
        "filters": filters,
        "pagination": {"limit": limit},
    }
    # Optional visual-similarity signal. Disabled on the public endpoint today
    # (returns a generic service error), but plumbed so it can be switched on.
    if like_image_b64 and like_image_mime:
        catalog["like"] = [
            {"image": {"content_type": like_image_mime, "data": like_image_b64}}
        ]

    arguments = {"meta": {"ucp-agent": {"profile": _agent_profile_url()}}, "catalog": catalog}

    try:
        async with MCPClient(CATALOG_MCP_URL) as client:
            result = await client.call_tool("search_catalog", arguments)
    except Exception:
        logger.exception("UCP search_catalog failed for %r", query)
        return []

    candidates = _parse_candidates(result)
    if not candidates:
        logger.info("UCP search returned no products for %r", query)
    return candidates


def dedup_candidates(candidates: list[Candidate]) -> list[Candidate]:
    """Collapse the same product sold by multiple merchants.

    Keys on the UPID-style product id (the catalog clusters cross-shop), falling
    back to a normalized title. Keeps the first occurrence, which preserves the
    server's relevance ordering within each source query.
    """
    seen: set[str] = set()
    out: list[Candidate] = []
    for c in candidates:
        key = c.product_id or _normalize_title(c.product.title)
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def rank_candidates(
    candidates: list[Candidate], vision: dict[str, Any]
) -> list[Candidate]:
    """Re-order candidates by how well they match the detected product.

    The score is dominated by *distinctive* signals (brand, model numbers, the
    fraction of query keywords the title covers) so near-identical generic items
    don't all collapse to the same value. Sorting is fully deterministic: equal
    scores fall back to price closeness, then the server's rank, then the stable
    product id — so identical inputs always yield the identical winner.
    """
    query_fields = [
        vision.get("query_precise"),
        vision.get("product_type"),
        vision.get("primary_color"),
        vision.get("secondary_color"),
        vision.get("material"),
        vision.get("fit"),
        vision.get("pattern"),
    ]
    qtokens: set[str] = set(_tokens(" ".join(f for f in query_fields if f)))
    for feature in vision.get("distinguishing_features") or []:
        qtokens.update(_tokens(str(feature)))

    # Brand + readable text (model numbers, names) are near-unique identifiers:
    # a hit on these in the *title* is far stronger evidence than a generic noun.
    brand = (vision.get("brand") or "").strip().lower()
    distinctive: set[str] = set(_tokens(brand))
    for text in vision.get("visible_text") or []:
        distinctive.update(_tokens(str(text)))
    qtokens |= distinctive

    est = vision.get("estimated_price_usd")
    has_est = isinstance(est, (int, float)) and est > 0

    for c in candidates:
        title_tokens = set(_tokens(c.product.title))
        meta_tokens = set(_tokens(c.match_text))

        # Coverage: what fraction of the query's keywords does the title carry?
        # Normalizing rewards titles that match *more* of the query, breaking the
        # ties we saw when every result merely shared "wireless over-ear".
        coverage = (len(qtokens & title_tokens) / len(qtokens)) if qtokens else 0.0
        score = 10.0 * coverage
        score += 1.0 * len(qtokens & title_tokens)
        score += 0.5 * len(qtokens & meta_tokens)

        # Distinctive matches in the title are the strongest signal.
        score += 5.0 * len(distinctive & title_tokens)
        if brand and " " not in brand and brand in title_tokens:
            score += 4.0
        elif brand and brand in c.match_text:
            score += 2.0

        if not c.product.image_url or "placehold" in c.product.image_url:
            score -= 3.0

        proximity = 0.0
        if has_est and c.price_cents > 0:
            ratio = c.price_cents / (est * 100.0)
            if ratio > 0:
                proximity = max(0.0, 1.0 - abs(math.log(ratio)))
                score += 5.0 * proximity

        c.score = round(score, 4)
        c.proximity = proximity

    return sorted(
        candidates,
        key=lambda c: (c.score, c.proximity, -c.rank, c.product_id),
        reverse=True,
    )


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


def _parse_candidates(tool_result: dict[str, Any]) -> list[Candidate]:
    structured = _structured_content(tool_result)
    raw_products = structured.get("products") if structured else None
    if not raw_products:
        return []
    parsed: list[Candidate] = []
    for idx, raw in enumerate(raw_products):
        candidate = _candidate_from_raw(raw, idx)
        if candidate is not None:
            parsed.append(candidate)
    return parsed


def _candidate_from_raw(raw: dict[str, Any], rank: int) -> Candidate | None:
    product = _product_from_raw(raw)
    if product is None:
        return None
    variant = (raw.get("variants") or [{}])[0]
    seller = variant.get("seller") or {}
    match_text = " ".join(
        part
        for part in (product.title, seller.get("name") or "", _metadata_text(raw))
        if part
    ).lower()
    return Candidate(
        product=product,
        product_id=raw.get("id") or product.variant_id,
        match_text=match_text,
        price_cents=product.price_min,
        currency=product.currency,
        rank=rank,
    )


def _metadata_text(raw: dict[str, Any]) -> str:
    metadata = raw.get("metadata") or {}
    parts: list[str] = []
    for key in ("top_features", "tech_specs", "unique_selling_points"):
        value = metadata.get(key)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(item) for item in value)
    for attr in metadata.get("attributes") or []:
        if isinstance(attr, dict):
            parts.append(f"{attr.get('name', '')} {attr.get('value', '')}")
    return " ".join(parts)


_STOPWORDS = {
    "the", "a", "an", "and", "or", "with", "for", "of", "to", "in", "on",
    "by", "at", "is", "it", "as", "from",
}


def _tokens(text: str) -> list[str]:
    return [
        tok
        for tok in re.findall(r"[a-z0-9]+", text.lower())
        if len(tok) > 1 and tok not in _STOPWORDS
    ]


def _normalize_title(title: str) -> str:
    return " ".join(_tokens(title))


def _product_from_raw(raw: dict[str, Any]) -> Product | None:
    if not isinstance(raw, dict):
        return None
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
        query = " ".join(sys.argv[1:])
        candidates = await search_catalog(query)
        candidates = dedup_candidates(candidates)
        candidates = rank_candidates(candidates, {"query_precise": query})
        print(
            json.dumps(
                [
                    {"score": round(c.score, 2), **c.product.model_dump()}
                    for c in candidates
                ],
                indent=2,
            )
        )

    asyncio.run(_main())
