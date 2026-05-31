import asyncio
import base64
import logging
from time import perf_counter

from config import settings
from models.schemas import Product, ScanResponse
from services import ucp, vision

logger = logging.getLogger(__name__)

# Size of the shortlist handed to the Gemini multimodal reranker. The cheap
# token ranker is only a coarse recall filter; we send a generous slice so the
# true match isn't dropped before the strong (visual + text) reranker sees it.
# Bigger because keyword-light titles (e.g. "Corne MX Split Keyboard") of the
# actual product score low on token overlap and were being cut pre-rerank.
RERANK_SHORTLIST = settings.rerank_shortlist
SEARCH_COUNTRIES = ("US", "CA")


def _format_price(cents: int, currency: str) -> str:
    if not cents:
        return ""
    return f"{currency} {cents / 100:.2f}"


def _target_spec(v: dict, voice_context: str | None = None) -> str:
    """Human-readable spec of the photographed product, for the reranker."""
    lines: list[str] = []
    if v.get("summary"):
        lines.append(v["summary"])
    voice = (voice_context or "").strip()
    if voice:
        lines.append(f"user voice request: {voice}")

    fields = [
        ("brand", v.get("brand")),
        ("type", v.get("product_type")),
        ("gender", v.get("gender")),
        ("material", v.get("material")),
        ("pattern", v.get("pattern")),
        ("fit", v.get("fit")),
    ]
    colors = ", ".join(c for c in (v.get("primary_color"), v.get("secondary_color")) if c)
    if colors:
        fields.append(("color", colors))
    lines.extend(f"{label}: {value}" for label, value in fields if value)

    if v.get("distinguishing_features"):
        lines.append("distinguishing features: " + "; ".join(v["distinguishing_features"]))
    if v.get("graphic_detail"):
        lines.append("logo/graphic: " + v["graphic_detail"])
    if v.get("visible_text"):
        lines.append("visible text/logos: " + "; ".join(v["visible_text"]))
    est = v.get("estimated_price_usd")
    if est:
        lines.append(f"approx. retail: USD {est}")
    return "\n".join(lines)


def _build_shortlist(ranked: list, limit: int) -> list:
    """Pick the candidates the reranker will actually see, deduped by image.

    Mostly token-ranked, but reserves ~1/3 of the slots for the catalog's own
    top relevance hits (lowest ``rank``) within each query. Keyword scoring
    buries short-titled exact matches (e.g. "Corne MX Split Keyboard") under
    keyword-stuffed generic listings; this guarantees those still reach the
    visual reranker instead of being filtered out beforehand.
    """
    seen_img: set[str] = set()
    seen_id: set[str] = set()
    out: list = []

    def add(c) -> None:
        key = c.product.image_url or c.product_id
        if key in seen_img or c.product_id in seen_id:
            return
        seen_img.add(key)
        seen_id.add(c.product_id)
        out.append(c)

    reserve = max(1, limit // 3)
    for c in sorted(ranked, key=lambda c: c.rank):
        if len(out) >= reserve:
            break
        add(c)
    for c in ranked:
        if len(out) >= limit:
            break
        add(c)
    return out[:limit]


async def run_scan(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    voice_context: str | None = None,
) -> ScanResponse:
    scan_started = perf_counter()
    try:
        stage_started = perf_counter()
        vision_result = await vision.analyze_image_bytes(
            image_bytes,
            mime_type,
            voice_context=voice_context,
        )
        logger.info("scan timing: Gemini extraction %.3fs", perf_counter() - stage_started)
    except Exception as exc:
        logger.exception("vision analysis failed")
        return ScanResponse(
            status="error",
            error=f"Could not analyze the image: {exc}",
        )

    query_precise = vision_result.get("query_precise") or ""
    query_broad = vision_result.get("query_broad") or ""
    search_query = (
        query_precise or query_broad or vision_result.get("product_type") or "product"
    )
    summary = vision_result.get("summary") or search_query
    search_intent = summary
    if voice_context:
        search_intent = f"{summary} User request: {voice_context.strip()}"

    # Distinct queries to fan out (precise + broad fallback), deduped.
    queries = [q for q in (query_precise, query_broad) if q]
    queries = list(dict.fromkeys(queries)) or [search_query]

    # We deliberately do NOT hard-filter on price: the vision estimate is rough,
    # and a wrong guess would exclude the true match entirely. Each query may
    # fail independently; gather with return_exceptions so one outage doesn't
    # sink the whole scan, and tell a service outage apart from a real no-match.
    stage_started = perf_counter()
    results = await asyncio.gather(
        *(
            ucp.search_catalog(
                q,
                intent=search_intent,
                ships_to_country=country,
            )
            for q in queries
            for country in SEARCH_COUNTRIES
        ),
        return_exceptions=True,
    )
    logger.info(
        "scan timing: UCP catalog search %.3fs (%d queries across %s)",
        perf_counter() - stage_started,
        len(queries),
        ", ".join(SEARCH_COUNTRIES),
    )
    groups = [r for r in results if not isinstance(r, Exception)]
    if not groups:
        logger.error("all catalog searches failed: %s", results)
        return ScanResponse(
            status="error",
            vision_summary=summary,
            search_query=search_query,
            vision=vision_result,
            error="Catalog search is currently unavailable. Please try again.",
        )
    candidates = [c for group in groups for c in group]

    # Optional visual-similarity search (off by default: the public endpoint
    # rejects `like`). Best-effort — never let it fail the scan.
    if settings.ucp_like_search_enabled:
        try:
            like_b64 = base64.b64encode(image_bytes).decode("ascii")
            like_results = await asyncio.gather(
                *(
                    ucp.search_catalog(
                        search_query,
                        intent=search_intent,
                        ships_to_country=country,
                        like_image_b64=like_b64,
                        like_image_mime=mime_type,
                    )
                    for country in SEARCH_COUNTRIES
                )
            )
            candidates += [candidate for group in like_results for candidate in group]
        except Exception:
            logger.info("UCP like-image search unavailable; skipping")

    candidates = ucp.rank_candidates(ucp.dedup_candidates(candidates), vision_result)

    # Two-stage retrieve-then-rerank. The token ranker above is only a coarse
    # recall filter: take a generous, image-deduped shortlist and let Gemini do
    # the authoritative match against the photo, the candidate titles/prices,
    # and the full target spec (brand, type, colors, distinguishing features).
    confidence: float | None = None
    match_reason: str | None = None
    shortlist = _build_shortlist(candidates, RERANK_SHORTLIST)
    if len(shortlist) > 1:
        stage_started = perf_counter()
        outcome = await vision.rerank_candidates(
            image_bytes,
            [
                {
                    "title": c.product.title,
                    "price": _format_price(c.product.price_min, c.product.currency),
                    "image_url": c.product.image_url,
                }
                for c in shortlist
            ],
            _target_spec(vision_result, voice_context),
            mime_type,
        )
        logger.info(
            "scan timing: visual rerank %.3fs (%d candidates)",
            perf_counter() - stage_started,
            len(shortlist),
        )
        if outcome is not None:
            confidence = outcome.confidence
            match_reason = outcome.reason or None
            if outcome.order:
                reranked = [shortlist[i] for i in outcome.order]
                # Deterministic guardrail: `order` holds only same-product
                # matches, so within it always prefer a single unit over a
                # multipack/bundle. sort() is stable, so it preserves Gemini's
                # order inside each group.
                reranked.sort(key=lambda c: ucp.is_multipack(c.product.title))
                chosen_ids = {c.product_id for c in reranked}
                candidates = reranked + [
                    c for c in candidates if c.product_id not in chosen_ids
                ]

    # Unverified (no rerank / no key / weak match) => flag so the UI can hedge.
    low_confidence = confidence is None or confidence < settings.rerank_confidence_threshold

    # Exact only when the reranker is confident it's the SAME product (model +
    # color + logo). Otherwise the top candidate is the closest look-alike that
    # the reranker ordered by visual similarity -> "similar".
    match_quality = "exact" if not low_confidence else "similar"

    product: Product | None = candidates[0].product if candidates else None
    # Always surface a few runner-ups (even on an exact match) so the shopper can
    # compare / pick a closer color or cheaper seller.
    alternatives = [c.product for c in candidates[1:5]] if product else []

    if not product:
        return ScanResponse(
            status="error",
            vision_summary=summary,
            search_query=search_query,
            vision=vision_result,
            error="No matching product found",
        )

    try:
        continue_url, cart_id = await ucp.create_cart(
            product.variant_id,
            product.merchant_url,
        )
    except NotImplementedError:
        # No merchant deep-link possible; fall back to the variant checkout URL
        # if we have one rather than discarding an otherwise-good product.
        if product.checkout_url:
            continue_url, cart_id = product.checkout_url, ""
        else:
            return ScanResponse(
                status="error",
                vision_summary=summary,
                search_query=search_query,
                vision=vision_result,
                product=product,
                confidence=confidence,
                match_reason=match_reason,
                low_confidence=low_confidence,
                match_quality=match_quality,
                alternatives=alternatives,
                error="Could not build a checkout link for this product",
            )

    response = ScanResponse(
        status="ready",
        vision_summary=summary,
        search_query=search_query,
        vision=vision_result,
        product=product,
        continue_url=continue_url,
        cart_id=cart_id,
        confidence=confidence,
        match_reason=match_reason,
        low_confidence=low_confidence,
        match_quality=match_quality,
        alternatives=alternatives,
    )
    logger.info("scan timing: total pipeline %.3fs", perf_counter() - scan_started)
    return response
