import asyncio
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from time import perf_counter

import httpx

from config import settings
from models.schemas import RerankVerdict
from models.schemas import VisionAttributes as VisionResult

logger = logging.getLogger(__name__)
_image_http_client: httpx.AsyncClient | None = None


def _thinking_config(types):
    return types.ThinkingConfig(thinking_budget=settings.gemini_thinking_budget)


def _log_gemini_usage(stage: str, response) -> None:
    usage = response.usage_metadata
    if usage is None:
        return
    logger.info(
        "%s usage: total_tokens=%s thought_tokens=%s",
        stage,
        usage.total_token_count,
        usage.thoughts_token_count,
    )


@lru_cache(maxsize=1)
def _gemini_client():
    from google import genai

    return genai.Client(api_key=settings.gemini_api_key)


def _shared_image_http_client() -> httpx.AsyncClient:
    global _image_http_client
    if _image_http_client is None:
        _image_http_client = httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            http2=True,
        )
    return _image_http_client


async def close_http_client() -> None:
    global _image_http_client
    if _image_http_client is not None:
        await _image_http_client.aclose()
        _image_http_client = None


@dataclass
class RerankOutcome:
    """Result of a Gemini rerank: the new order plus the model's self-assessment.

    ``order`` is original candidate indices, best first (may be empty if the
    model judged nothing a match). ``confidence``/``reason`` let the caller flag
    or explain weak matches instead of presenting them as certain.
    """

    order: list[int]
    confidence: float
    reason: str

_MIME_BY_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".heif": "image/heif",
}

PROMPT = """You are a product identification expert for a visual shopping assistant.
The image shows ONE physical product (clothing, footwear, accessory, or
consumer good). Extract every attribute that would help a shopper find
THIS EXACT product on a global catalog.

Rules:
- If several products are visible, focus on the SINGLE most prominent /
  centered / held one and ignore everything else.
- Describe ONLY the product itself. Never mention the person, hands, pose,
  background, location, lighting, or any other item in the scene.
- "summary" = one short sentence about the product alone, starting with the
  product and INCLUDING its style/construction and, when present, the SIZE and
  PLACEMENT of any logo/graphic (e.g. "Black beanie with a small white logo
  centered on the front fold.", "Navy snapback cap with a flat brim and white
  NY logo."), NOT "A person holding...".
- Use null when an attribute is not confidently visible. Never guess.
- "brand" must come from a visible logo, tag, or printed text. Otherwise null.
- "visible_text" captures any readable string on the product (logos,
  model numbers, slogans, size tags). Empty list if none.
- "distinguishing_features" = the form/construction cues that separate THIS
  item from other products of the SAME type — this is critical for ranking, so
  be specific and visual. For WHATEVER the product is, capture its silhouette/
  shape, its distinct PARTS, closure/fastening, materials, and the per-part
  colorway (the color of each major part, not just the dominant one).
  The examples below show the LEVEL OF DETAIL expected — apply the SAME kind of
  thinking to ANY product type (electronics, watches, bottles, furniture, etc.),
  not only the ones listed:
  - cap: crown structure (structured vs unstructured/dad cap) + brim shape
    (flat vs curved) + back closure (fitted, snapback, strapback, elastic).
  - shoe: high-top vs low-top, toe shape, sole/outsole style, lacing, AND the
    per-part colorway (upper color, sole/midsole color, and any swoosh/stripe/
    accent color) — e.g. "white upper", "gum sole", "black swoosh".
  - bag: tote vs crossbody vs backpack, strap type, closure, pockets.
  - apparel: neckline, sleeve length, fit (slim/oversized), hood, zip vs pullover.
  Use short phrases (e.g. "flat brim", "snapback closure", "structured high
  crown"). Empty list only if the item is truly featureless.
- "graphic_detail" = if the product shows a logo, print, or graphic, describe
  its SIZE relative to the product and its PLACEMENT precisely (e.g. "small
  embroidered logo centered on the front fold", "left-chest logo about 4 cm
  wide", "large graphic covering most of the front"). This matters for
  matching: a small front logo is a DIFFERENT product from a large or all-over
  print of the same brand. Null only if the product has no logo/graphic.
- Colors must be common names ("navy blue", "burgundy", "off-white"), not hex.
- "query_precise" = compact keyword string a shopper would type, ordered:
  brand · gender · product_type · key_attributes (color, material, fit,
  pattern). Use plain words that are likely to appear in a real product
  TITLE; do NOT pack in long descriptive phrases (those go in
  distinguishing_features, which is used for ranking, not search). No stop
  words, no punctuation other than spaces, max 8 words. Lowercase.
- "query_broad" = same but drop the brand and any attribute you are < 80%
  sure of, keeping just product_type + the 1-2 most certain attributes.
  Used as a fallback / recall booster.
- "estimated_price_usd" = your best guess of typical retail price in USD for
  an item that looks like this, as an integer. This drives a price filter,
  so estimate carefully. Null only if you truly cannot tell.
- "category" must be one of: apparel, footwear, accessory, electronics,
  home, beauty, other.
- "gender" must be one of: men, women, unisex, kids, null.
- "pattern" must be one of: solid, striped, checked, floral, graphic, logo,
  other, null."""


def _prompt_with_context(voice_context: str | None) -> str:
    context = (voice_context or "").strip()
    if not context:
        return PROMPT

    return (
        PROMPT
        + "\n\nVoice instruction from the user:\n"
        + context
        + "\n\nAdditional targeting rules:\n"
        + "- The image may contain multiple visible products.\n"
        + "- Use the voice instruction to decide which product is the target.\n"
        + "- If the instruction names a product type, color, position, or wearer, "
        "focus on the matching product even if another object is more prominent.\n"
        + "- If the instruction is vague, infer the most likely shopping target "
        "from the instruction and image.\n"
        + "- Keep the output schema exactly the same."
    )


def _mime_for(image_path: Path) -> str:
    return _MIME_BY_SUFFIX.get(image_path.suffix.lower(), "image/jpeg")


async def analyze_image_bytes(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    voice_context: str | None = None,
) -> dict:
    """Analyse des bytes image en mémoire (depuis l'upload FastAPI)."""
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    from google.genai import types

    response = await _gemini_client().aio.models.generate_content(
        model=settings.gemini_analysis_model,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            _prompt_with_context(voice_context),
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=VisionResult,
            temperature=0.0,
            thinking_config=_thinking_config(types),
        ),
    )
    _log_gemini_usage("Gemini extraction", response)

    result = response.parsed
    if result is None:
        raise ValueError(f"Gemini returned no structured result: {response.text!r}")
    return result.model_dump()


async def analyze_image(image_path: Path) -> dict:
    """Version Path conservée pour compat avec test_vision.py."""
    return await analyze_image_bytes(
        image_path.read_bytes(),
        mime_type=_mime_for(image_path),
    )


RERANK_INSTRUCTIONS = """You are the final, authoritative matcher for a visual
shopping assistant. You are given:
1. A TARGET spec describing the product a shopper photographed (may include a
   "user voice request" line — honor it when choosing among similar candidates).
2. The shopper's REFERENCE PHOTO.
3. A numbered list of catalog CANDIDATES, each with its title, price, and image.

Decide which candidates are the SAME product the shopper photographed, then
rank them from best to worst match.

How to judge (in priority order):
1. Same product TYPE. Never match across types (a backpack is not a handbag,
   headphones are not earbuds).
2. Same brand AND same model/style. Use the TARGET brand and any visible
   text/logos, and read the candidate TITLES — a brand or model name in the
   title is strong evidence. A different brand is strong evidence AGAINST.
3. Same CONSTRUCTION / silhouette / style / layout. Match the form factor, not
   just the type. Use the TARGET distinguishing features and the photo's shape.
   Among the same type, a different construction is a WORSE match. Examples:
   a snapback is NOT a fitted or dad cap; a flat brim is NOT a curved brim;
   a high-top is NOT a low-top; a tote is NOT a crossbody; a pullover is NOT
   a full-zip; a compact column-staggered split mechanical keyboard is NOT a
   full-size membrane keyboard that merely has a center gap; a 60% board is NOT
   a full-size board. Match SIZE/layout and mechanism, not just buzzwords like
   "split" or "ergonomic". Read style words in candidate TITLES too.
4. Same COLORWAY / finish. DECISIVE when several candidates are the same brand
   and model in different colors: the shopper wants the exact color in the photo.
   - Compare the candidate IMAGE color and any color words in its TITLE
     (e.g. "Shadow", "Black", "Stone Blue", "Sea Glass", "Stainless",
     "Charcoal", "Navy") against the photo and the TARGET color.
   - A clearly different colorway is a WORSE match even when brand and model
     are identical. Light gray / silver / stainless is NOT dark gray / shadow /
     black; navy is not royal blue or teal; etc.
   - FOOTWEAR especially: a sneaker's colorway is multi-tone — match the WHOLE
     scheme (upper, toe, midsole/sole, laces, and any swoosh/stripes/accent),
     not just the dominant color. A different colorway of the SAME silhouette is
     NOT the same product: e.g. all-black is NOT white/black; "Panda" (black/
     white) is NOT "UNC" (blue/white); a gum sole is NOT a white sole; a black
     swoosh is NOT a red swoosh. If the upper, sole, or accent colors differ
     from the photo, it is at best a SIMILAR match (confidence < 0.5), not exact.
   - Allow for lighting and white-balance differences, but a fundamentally
     different color family is a mismatch.
5. Quantity & packaging. The shopper wants a SINGLE unit like the one in the
   photo. Strongly demote multipacks and bundles — titles containing "2 Pack",
   "3-Pack", "(2 Pack)", "Set of", "Bundle", "Combo", "Variety", "Value Pack",
   or images showing several units — UNLESS the photo clearly shows multiple
   items. Also demote accessory-only or replacement-part listings (e.g. "Lid
   only", "Replacement Lid", "Lid Combo") unless the photo is of just that
   accessory. A single-unit listing of the right product BEATS a multipack of
   the same product.
6. Logo / graphic SCALE, PLACEMENT, and COLOR. Match how the logo or print
   looks, not just that one exists. Use the TARGET "logo/graphic" note and
   compare BOTH images directly.
   - A small logo in a specific spot (e.g. centered on a beanie's front fold, or
     a left-chest mark) is a DIFFERENT product from a large, oversized, or
     all-over print of the same brand.
   - The logo / emblem COLOR is distinguishing: a WHITE swoosh is NOT a black
     swoosh; a tonal/same-color logo is NOT a contrasting logo. Compare the logo
     color you SEE in the photo against the candidate IMAGE (don't rely on the
     text alone — small logos are easy to misread, so trust the pixels).
   - Wrong logo size, position, OR color is a WORSE match even with the same
     brand and garment color, and must keep confidence BELOW the exact range.
7. Other visual attributes: material, pattern, capacity, and any remaining
   distinguishing features.
8. Ignore background, angle, watermarks, and image quality. Judge the product
   itself, not the photo.
9. Price is a weak tiebreaker only.

Output:
- "ranking": ALWAYS order the candidates from CLOSEST to least close to the
  photo, best first — even when NONE is an exact match. This is the "closest
  look-alike" list the app shows when there's no exact match, so it MUST be
  populated whenever there are same-type candidates. Order by: construction/
  silhouette, then COLOR (a wrong-color variant of the right item is still far
  closer than a different item), then logo, then other attributes. A wrong-color
  but same-type item belongs in the ranking (just lower) — do NOT drop it. Only
  OMIT a candidate that is a clearly different product TYPE (a bag when the photo
  is a hoodie, earbuds vs headphones). Push multipacks/bundles toward the end.
- "best_index": the single closest candidate number, or -1 ONLY if not one
  candidate is even the same product type.
- "confidence": 0..1 that best_index is the EXACT same product as the photo —
  same model AND color AND logo — judged INDEPENDENTLY of the ranking. This is
  what tells the app "exact" vs "similar", so be strict and honest:
  - A right-type look-alike with a different COLOR, logo, or construction is a
    SIMILAR match, not exact: keep confidence LOW (< 0.5) even if it tops the
    ranking. The shopper photographed a red hoodie; a black one of the same
    model is the closest similar item but is NOT an exact match.
  - If the TARGET has NO brand, you are matching by APPEARANCE alone. Reserve
    high confidence (> 0.8) for a candidate that is visually near-identical in
    form, size, color, and layout — not merely the same category.
  - Always rank the closest item even when confidence is low. Populate the
    ranking; use confidence (not an empty ranking) to signal "no exact match".
- "reason": one short sentence naming the matched construction/style, color,
  and logo scale/placement when relevant."""

_MAX_RERANK_IMAGE_BYTES = 6_000_000


async def _fetch_image(client: httpx.AsyncClient, url: str) -> tuple[bytes, str] | None:
    if not url or "placehold" in url:
        return None
    try:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
    except Exception:
        logger.info("visual rerank: failed to fetch %s", url)
        return None
    data = resp.content
    if not data or len(data) > _MAX_RERANK_IMAGE_BYTES:
        return None
    content_type = (resp.headers.get("content-type") or "image/jpeg").split(";")[0]
    if not content_type.startswith("image/"):
        content_type = "image/jpeg"
    return data, content_type


async def rerank_candidates(
    image_bytes: bytes,
    candidates: list[dict],
    target: str,
    mime_type: str = "image/jpeg",
) -> RerankOutcome | None:
    """Re-rank catalog candidates against the scanned photo using Gemini.

    ``candidates`` is a list of dicts with ``title``, ``price`` (display
    string), and ``image_url``. ``target`` is a text spec of what the shopper
    photographed (built from the vision attributes).

    Returns a :class:`RerankOutcome` whose ``order`` holds original indices
    (into ``candidates``) best match first, with clear non-matches dropped — or
    ``None`` when the rerank can't be performed at all (no key, no fetchable
    images, or the model call fails), in which case the caller should keep its
    existing order. When the model responds but matches nothing, ``order`` is
    empty and ``confidence`` is low.
    """
    if not settings.gemini_api_key or not candidates:
        return None

    urls = [c.get("image_url") or "" for c in candidates]
    fetch_started = perf_counter()
    client = _shared_image_http_client()
    fetched = await asyncio.gather(*(_fetch_image(client, url) for url in urls))
    logger.info(
        "visual rerank: downloaded %d/%d candidate images in %.3fs",
        sum(item is not None for item in fetched),
        len(urls),
        perf_counter() - fetch_started,
    )

    # Map the number shown to Gemini -> original candidate index. Images that
    # fail to download are dropped, so the presented numbering is dense.
    kept: list[tuple[int, bytes, str]] = []
    for orig_idx, item in enumerate(fetched):
        if item is not None:
            data, content_type = item
            kept.append((orig_idx, data, content_type))
    if not kept:
        return None

    from google.genai import types

    parts: list[object] = [
        RERANK_INSTRUCTIONS,
        f"TARGET spec:\n{target}",
        "REFERENCE PHOTO:",
        types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        "CANDIDATES:",
    ]
    for shown_idx, (orig_idx, data, content_type) in enumerate(kept):
        c = candidates[orig_idx]
        label = f"Candidate {shown_idx}: {c.get('title') or 'Untitled'}"
        price = c.get("price")
        if price:
            label += f" — {price}"
        parts.append(label)
        parts.append(types.Part.from_bytes(data=data, mime_type=content_type))

    try:
        rerank_started = perf_counter()
        response = await _gemini_client().aio.models.generate_content(
                model=settings.gemini_rerank_model,
            contents=parts,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=RerankVerdict,
                temperature=0.0,
                thinking_config=_thinking_config(types),
            ),
        )
        _log_gemini_usage("Gemini rerank", response)
        logger.info(
            "visual rerank: Gemini call completed in %.3fs",
            perf_counter() - rerank_started,
        )
    except Exception:
        logger.exception("visual rerank: Gemini call failed")
        return None

    verdict: RerankVerdict | None = response.parsed
    if verdict is None:
        return None

    # Translate the model's candidate numbers back to original indices, keeping
    # the model's order, de-duping, and ignoring out-of-range noise.
    order: list[int] = []
    seen: set[int] = set()
    shown_numbers = list(verdict.ranking)
    if verdict.best_index >= 0:
        shown_numbers = [verdict.best_index, *shown_numbers]
    for shown in shown_numbers:
        if 0 <= shown < len(kept):
            orig_idx = kept[shown][0]
            if orig_idx not in seen:
                seen.add(orig_idx)
                order.append(orig_idx)

    logger.info(
        "visual rerank: confidence=%.2f reason=%s order=%s",
        verdict.confidence,
        verdict.reason,
        order,
    )
    return RerankOutcome(
        order=order,
        confidence=float(verdict.confidence or 0.0),
        reason=verdict.reason or "",
    )
