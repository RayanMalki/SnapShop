from typing import Literal

from pydantic import BaseModel, Field


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
    products: list[Product] = Field(default_factory=list)
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
