from pathlib import Path

from config import settings
from models.schemas import VisionAttributes as VisionResult

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
The image may show one or many physical products (clothing, footwear,
accessories, or consumer goods). Extract every attribute that would help a
shopper find the intended product on a global catalog.

Rules:
- If the user provided voice context, use it to choose the SINGLE target
  product in the image. The voice context may be phrased naturally, such as
  "find the baseball cap", "what shoes is that person wearing", or
  "I like the green hoodie".
- If the voice context is vague, infer the most likely matching product from
  the instruction and visible products.
- If no voice context is provided, focus on the SINGLE most prominent /
  centered / held product and ignore everything else.
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


def _prompt_with_context(voice_context: str | None) -> str:
    cleaned = (voice_context or "").strip()
    if not cleaned:
        return PROMPT + "\n\nVoice context: none provided."
    return (
        PROMPT
        + "\n\nVoice context from the user. Use this to decide which visible "
        + "product is the target, but do not copy uncertain words into the "
        + f"catalog query unless the image supports them:\n{cleaned}"
    )


async def analyze_image_bytes(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    voice_context: str | None = None,
) -> dict:
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
                _prompt_with_context(voice_context),
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
