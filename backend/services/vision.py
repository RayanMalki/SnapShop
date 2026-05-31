from pathlib import Path

from config import settings
from models.schemas import VisionAttributes as VisionResult

MODEL = "gemini-2.5-flash"

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


def _mime_for(image_path: Path) -> str:
    return _MIME_BY_SUFFIX.get(image_path.suffix.lower(), "image/jpeg")


async def analyze_image_bytes(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """Analyse des bytes image en mémoire (depuis l'upload FastAPI)."""
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

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
            temperature=0.0,
        ),
    )

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
