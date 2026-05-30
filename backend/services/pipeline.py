from models.schemas import Product, ScanResponse
from services import ucp, vision


async def run_scan(image_bytes: bytes, mime_type: str = "image/jpeg") -> ScanResponse:
    vision_result = await vision.analyze_image_bytes(image_bytes, mime_type)

    query_precise = vision_result.get("query_precise") or ""
    query_broad = vision_result.get("query_broad") or ""
    search_query = query_precise or query_broad or "clothing item"
    summary = vision_result.get("summary") or search_query

    # Recherche UCP : on tente la requête précise, puis on retombe sur la
    # requête large (sans marque / attributs incertains) si rien ne sort.
    product: Product | None = await ucp.search_catalog(search_query)
    if not product and query_broad and query_broad != search_query:
        product = await ucp.search_catalog(query_broad)
        search_query = query_broad

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
