from models.schemas import Product, ScanResponse
from services import ucp, vision

_STOPWORDS = {"the", "and", "with", "for", "men", "women", "unisex", "kids"}


def _keywords(vision_result: dict) -> set[str]:
    parts = [
        vision_result.get("query_precise") or "",
        vision_result.get("product_type") or "",
        vision_result.get("primary_color") or "",
    ]
    text = " ".join(parts).lower()
    return {w for w in text.split() if len(w) > 2 and w not in _STOPWORDS}


def _best_match(products: list[Product], vision_result: dict) -> Product:
    brand = (vision_result.get("brand") or "").lower().strip()
    keywords = _keywords(vision_result)

    def score(p: Product) -> int:
        title = (p.title or "").lower()
        s = sum(1 for kw in keywords if kw in title)
        if brand and brand in title:
            s += 5
        return s

    return max(products, key=score)


async def run_scan(image_bytes: bytes, mime_type: str = "image/jpeg") -> ScanResponse:
    vision_result = await vision.analyze_image_bytes(image_bytes, mime_type)

    query_precise = vision_result.get("query_precise") or ""
    query_broad = vision_result.get("query_broad") or ""
    search_query = query_precise or query_broad or "clothing item"
    summary = vision_result.get("summary") or search_query

    # Recherche UCP : on tente la requête précise, puis on retombe sur la
    # requête large (sans marque / attributs incertains) si rien ne sort.
    # search_catalog renvoie une list[Product] ; on garde le meilleur (1er).
    products = await ucp.search_catalog(search_query)
    if not products and query_broad and query_broad != search_query:
        products = await ucp.search_catalog(query_broad)
        search_query = query_broad

    product: Product | None = None
    if products:
        # 1) Re-ranking VISUEL : Gemini compare la photo aux images candidates.
        idx = await vision.pick_best_match(image_bytes, mime_type, products)
        # 2) Fallback : ranking texte (mots-clés) si le visuel échoue.
        product = products[idx] if idx is not None else _best_match(products, vision_result)

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
