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
    visible_text: list[str] = Field(default_factory=list, description="Readable strings on the product")
    estimated_price_usd: int | None = Field(default=None, description="Typical retail price guess, int or null")
    query_precise: str = Field(default="", description="brand gender type attrs, max 12 words, lowercase")
    query_broad: str = Field(default="", description="Fallback query without brand / uncertain attrs")


class VisualMatch(BaseModel):
    """Résultat du re-ranking visuel : quel candidat ressemble le plus à la photo."""

    best_index: int = Field(description="0-based index of the best-matching candidate")
    confidence: float = Field(default=0.0, description="0..1 confidence in the match")
    reasoning: str = Field(default="", description="Short why")


class Product(BaseModel):
    variant_id: str
    title: str
    price_min: int = Field(description="Price in cents")
    price_max: int = Field(description="Price in cents")
    currency: str = "CAD"
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


class HealthResponse(BaseModel):
    status: str = "ok"


class LoginRequest(BaseModel):
    email: str | None = None
    password: str | None = None
    apple_token: str | None = None


class LoginResponse(BaseModel):
    token: str
    user_id: str
