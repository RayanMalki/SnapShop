import asyncio

from models.schemas import Product, ScanResponse
from services import ucp, vision


async def run_scan(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    voice_context: str | None = None,
) -> ScanResponse:
    vision_result = await vision.analyze_image_bytes(
        image_bytes,
        mime_type,
        voice_context=voice_context,
    )

    query_precise = vision_result.get("query_precise") or ""
    query_broad = vision_result.get("query_broad") or ""
    search_query = query_precise or query_broad or "clothing item"
    summary = vision_result.get("summary") or search_query
    search_intent = summary
    if voice_context:
        search_intent = f"{summary} User request: {voice_context.strip()}"

    # Distinct queries to fan out (precise + broad fallback), deduped.
    queries = [q for q in (query_precise, query_broad) if q]
    queries = list(dict.fromkeys(queries)) or [search_query]

    # We deliberately do NOT hard-filter on price: the vision estimate is rough,
    # and a wrong guess would exclude the true match entirely (the cause of
    # "sometimes nothing good"). ships_to + currency remove the worst noise, and
    # price proximity is applied as a ranking signal instead.
    results = await asyncio.gather(
        *(ucp.search_catalog(q, intent=search_intent) for q in queries)
    )
    candidates = [c for group in results for c in group]

    candidates = ucp.rank_candidates(ucp.dedup_candidates(candidates), vision_result)
    product: Product | None = candidates[0].product if candidates else None

    if not product:
        return ScanResponse(
            status="error",
            vision_summary=summary,
            search_query=search_query,
            vision=vision_result,
            error="No product found from UCP search",
        )

    try:
        continue_url, cart_id = await ucp.create_cart(
            product.variant_id,
            product.merchant_url,
        )
    except NotImplementedError as exc:
        return ScanResponse(
            status="error",
            vision_summary=summary,
            search_query=search_query,
            vision=vision_result,
            product=product,
            error=str(exc),
        )

    return ScanResponse(
        status="ready",
        vision_summary=summary,
        search_query=search_query,
        vision=vision_result,
        product=product,
        continue_url=continue_url,
        cart_id=cart_id,
    )
