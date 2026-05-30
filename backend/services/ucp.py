"""Shopify UCP: search_catalog + create_cart. Mock when USE_MOCK_UCP=true."""

import httpx

from config import settings
from models.schemas import Product

MOCK_PRODUCT = Product(
    variant_id="gid://shopify/ProductVariant/123456789",
    title="Classic Cotton Tee",
    price_min=2999,
    price_max=2999,
    currency="CAD",
    image_url="https://cdn.shopify.com/s/files/1/0533/2089/files/placeholder-images-image_large.png",
    merchant_domain="demo-store.myshopify.com",
    merchant_url="https://demo-store.myshopify.com",
)

MOCK_CONTINUE_URL = "https://demo-store.myshopify.com/cart/c/mock-cart-abc123"
MOCK_CART_ID = "gid://shopify/Cart/mock-cart-abc123"


async def search_catalog(query: str, country: str = "CA") -> Product | None:
    if settings.use_mock_ucp:
        return MOCK_PRODUCT

    # TODO: wire real UCP catalog search CLI or HTTP agent profile
    async with httpx.AsyncClient(timeout=30.0) as client:
        _ = client  # placeholder until UCP HTTP integration is added
    return None


async def create_cart(variant_id: str, merchant_url: str, country: str = "CA") -> tuple[str, str]:
    """Returns (continue_url, cart_id)."""
    if settings.use_mock_ucp:
        return MOCK_CONTINUE_URL, MOCK_CART_ID

    # TODO: ucp cart create --business {merchant_url} --set /line_items/0/item/id=...
    raise NotImplementedError("Real UCP create_cart not wired yet; set USE_MOCK_UCP=true")
