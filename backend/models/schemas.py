from typing import Literal

from pydantic import BaseModel, Field


class VisionAttributes(BaseModel):
    """Attributs produit extraits par Gemini Vision (structured output)."""

    summary: str = Field(default="", description="One human sentence describing the item")
    product_type: str = Field(default="", description="Specific noun phrase, e.g. 'crew neck t-shirt'")
    category: str = Field(default="other", description="apparel|footwear|accessory|electronics|home|beauty|other")
    brand: str | None = Field(default=None, description="From a visible logo/tag/text, else null")
    gender: str | None = Field(default=None, description="men|women|unisex|kids|null")
    primary_color: str = Field(default="", description="Common color name")
    secondary_color: str | None = Field(default=None, description="Common color name or null")
    material: str | None = Field(default=None, description="e.g. cotton, leather, null")
    pattern: str | None = Field(default=None, description="solid|striped|checked|floral|graphic|logo|other|null")
    fit: str | None = Field(default=None, description="e.g. slim, oversized, regular, cropped, null")
    distinguishing_features: list[str] = Field(default_factory=list, description="Short phrases")
    graphic_detail: str | None = Field(
        default=None,
        description=(
            "If the product has a logo/print/graphic: its SIZE relative to the "
            "item and PLACEMENT, e.g. 'small logo centered on the front fold', "
            "'large print covering the chest'. Null if there is none."
        ),
    )
    visible_text: list[str] = Field(default_factory=list, description="Readable strings on the product")
    estimated_price_usd: int | None = Field(default=None, description="Typical retail price guess, int or null")
    query_precise: str = Field(default="", description="brand gender type attrs, max 12 words, lowercase")
    query_broad: str = Field(default="", description="Fallback query without brand / uncertain attrs")


class RerankVerdict(BaseModel):
    """Gemini's multimodal verdict over a shortlist of catalog candidates.

    Candidate numbers refer to the order the candidates were presented to the
    model (0-based). ``ranking`` is best-match-first; ``best_index`` is the top
    pick (mirrors ``ranking[0]``) and ``-1`` means nothing plausibly matched.
    """

    ranking: list[int] = Field(
        default_factory=list,
        description="Candidate numbers, best match first. Exclude clear non-matches.",
    )
    best_index: int = Field(
        default=-1, description="Best candidate number, or -1 if none match"
    )
    confidence: float = Field(
        default=0.0, description="0..1 confidence that best_index is the same product"
    )
    reason: str = Field(default="", description="Brief justification for the top pick")


class Product(BaseModel):
    variant_id: str
    title: str
    price_min: int = Field(description="Price in cents")
    price_max: int = Field(description="Price in cents")
    currency: str = "USD"
    image_url: str
    merchant_domain: str
    merchant_url: str
    checkout_url: str | None = None


class ScanResponse(BaseModel):
    status: Literal["processing", "ready", "error"]
    vision_summary: str | None = None
    search_query: str | None = None
    vision: VisionAttributes | None = None
    product: Product | None = None
    continue_url: str | None = None
    cart_id: str | None = None
    error: str | None = None
    confidence: float | None = Field(
        default=None, description="0..1 reranker confidence the product matches the photo"
    )
    match_reason: str | None = Field(
        default=None, description="Why the reranker picked this product (color/style/etc.)"
    )
    low_confidence: bool = Field(
        default=False,
        description="True when the match is unverified or below the confidence threshold",
    )
    alternatives: list[Product] = Field(
        default_factory=list,
        description="Other strong matches (best first) so the UI can offer options",
    )


class HealthResponse(BaseModel):
    status: str = "ok"


class LoginRequest(BaseModel):
    email: str | None = None
    password: str | None = None
    apple_token: str | None = None


class LoginResponse(BaseModel):
    token: str
    user_id: str
