import asyncio
from pathlib import Path

from config import settings
from models.schemas import VisionAttributes as VisionResult
from models.schemas import VisualMatch

MODEL = "gemini-2.5-flash-lite"

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
  product (e.g. "Gray ThermoFlask stainless steel water bottle."), NOT
  "A person holding...".
- Use null when an attribute is not confidently visible. Never guess.
- "brand" must come from a visible logo, tag, or printed text. Otherwise null.
- "visible_text" captures any readable string on the product (logos,
  model numbers, slogans, size tags). Empty list if none.
- Colors must be common names ("navy blue", "burgundy", "off-white"), not hex.
- "query_precise" = compact keyword string, ordered:
  brand · gender · product_type · key_attributes (color, material, fit,
  pattern, distinguishing_feature). No stop words, no punctuation other
  than spaces, max 12 words. Lowercase.
- "query_broad" = same but drop the brand and any attribute you are < 80%
  sure of. Used as a fallback if the precise query returns nothing.
- "estimated_price_usd" = your best guess of typical retail price for an
  item that looks like this, as an integer. Null if unsure.
- "category" must be one of: apparel, footwear, accessory, electronics,
  home, beauty, other.
- "gender" must be one of: men, women, unisex, kids, null.
- "pattern" must be one of: solid, striped, checked, floral, graphic, logo,
  other, null."""


MOCK_VISION = VisionResult(
    summary="Blue cotton crew neck t-shirt (mock).",
    product_type="crew neck t-shirt",
    category="apparel",
    brand=None,
    gender="men",
    primary_color="blue",
    secondary_color=None,
    material="cotton",
    pattern="solid",
    fit="regular",
    distinguishing_features=["short sleeves", "ribbed collar"],
    visible_text=[],
    estimated_price_usd=25,
    query_precise="men crew neck t-shirt blue cotton regular fit",
    query_broad="crew neck t-shirt blue",
)


def _mime_for(image_path: Path) -> str:
    return _MIME_BY_SUFFIX.get(image_path.suffix.lower(), "image/jpeg")


async def analyze_image_bytes(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """Analyse des bytes image en mémoire (depuis l'upload FastAPI)."""
    if not settings.gemini_api_key:
        return MOCK_VISION.model_dump()

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.gemini_api_key)

        response = await client.aio.models.generate_content(
            model=MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                PROMPT,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VisionResult,
                temperature=0.2,
            ),
        )

        result = response.parsed
        if result is None:
            raise ValueError(f"Gemini returned no structured result: {response.text!r}")
        return result.model_dump()

    except Exception as e:
        print(f"[vision] Gemini error, falling back to mock: {e}")
        return MOCK_VISION.model_dump()


async def analyze_image(image_path: Path) -> dict:
    """Version Path conservée pour compat avec test_vision.py."""
    return await analyze_image_bytes(
        image_path.read_bytes(),
        mime_type=_mime_for(image_path),
    )


# ---------------------------------------------------------------------------
# Re-ranking visuel : compare la photo aux images des candidats UCP
# ---------------------------------------------------------------------------

MATCH_PROMPT = (
    "The FIRST image is a photo a shopper took of the product they want to buy.\n"
    "The remaining images are CANDIDATE products from a store catalog, each "
    "preceded by 'Candidate N:' and its title.\n"
    "Pick the candidate that is the SAME product as the photo — matching the "
    "exact type (e.g. snapback vs fitted cap), color, and visual style. "
    "Trust the candidate IMAGE over its title when they disagree.\n"
    "Return best_index = the candidate number (0-based) that matches best, and "
    "confidence between 0 and 1."
)


async def _fetch_thumb(http, url: str) -> tuple[bytes, str] | None:
    """Télécharge une image candidate -> (bytes, mime) ou None si échec."""
    if not url:
        return None
    try:
        resp = await http.get(url)
        resp.raise_for_status()
        mime = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        if not mime.startswith("image/"):
            mime = "image/jpeg"
        return resp.content, mime
    except Exception:
        return None


async def pick_best_match(
    query_image: bytes,
    query_mime: str,
    candidates: list,
    *,
    max_candidates: int = 8,
) -> int | None:
    """Renvoie l'index (dans `candidates`) du produit visuellement le plus proche.

    Retourne None si la clé manque, s'il n'y a aucune image exploitable, ou si
    l'appel Gemini échoue -> le caller doit alors retomber sur le ranking texte.
    """
    if not settings.gemini_api_key or not candidates:
        return None

    pool = candidates[:max_candidates]

    try:
        import httpx
        from google import genai
        from google.genai import types

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as http:
            thumbs = await asyncio.gather(
                *[_fetch_thumb(http, getattr(c, "image_url", "")) for c in pool]
            )

        # On ne garde que les candidats dont l'image a été récupérée, en gardant
        # le lien vers leur index d'origine dans `candidates`.
        presented: list[int] = []
        contents: list = [
            "PHOTO from the shopper:",
            types.Part.from_bytes(data=query_image, mime_type=query_mime),
            "CANDIDATES:",
        ]
        for orig_idx, thumb in enumerate(thumbs):
            if thumb is None:
                continue
            img_bytes, img_mime = thumb
            pos = len(presented)
            contents.append(f"Candidate {pos}: {getattr(pool[orig_idx], 'title', '')}")
            contents.append(types.Part.from_bytes(data=img_bytes, mime_type=img_mime))
            presented.append(orig_idx)

        if not presented:
            return None
        if len(presented) == 1:
            return presented[0]

        contents.append(MATCH_PROMPT)

        client = genai.Client(api_key=settings.gemini_api_key)
        response = await client.aio.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VisualMatch,
                temperature=0.0,
            ),
        )

        match = response.parsed
        if match is None or not (0 <= match.best_index < len(presented)):
            return None
        return presented[match.best_index]

    except Exception as e:
        print(f"[vision] visual re-rank failed, falling back to text rank: {e}")
        return None
