from pathlib import Path
import uuid

from models.schemas import Product, ScanResponse
from services import ucp, vision


async def run_scan(image_path: Path) -> ScanResponse:
    vision_result = await vision.analyze_image(image_path)
    search_query = vision_result.get("search_query") or "clothing item"
    summary = vision_result.get("summary") or search_query

    product: Product | None = await ucp.search_catalog(search_query)
    if not product:
        return ScanResponse(
            status="error",
            vision_summary=summary,
            search_query=search_query,
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
            product=product,
            error=str(exc),
        )

    return ScanResponse(
        status="ready",
        vision_summary=summary,
        search_query=search_query,
        product=product,
        continue_url=continue_url,
        cart_id=cart_id,
    )


def save_upload(contents: bytes, upload_dir: Path, suffix: str = ".jpg") -> Path:
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / f"{uuid.uuid4().hex}{suffix}"
    path.write_bytes(contents)
    return path
