import asyncio
import sys
from pathlib import Path

import httpx

from config import settings
from services.vision import analyze_image

DEMO_IMAGE_URL = "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=800"


async def _ensure_image(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    dest = Path(settings.upload_dir) / "demo_tshirt.jpg"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(DEMO_IMAGE_URL)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
    return dest


async def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    image_path = await _ensure_image(arg)
    mode = "MOCK (no GEMINI_API_KEY)" if not settings.gemini_api_key else "GEMINI"
    print(f"[mode] {mode}")
    print(f"[image] {image_path}")
    result = await analyze_image(image_path)
    print("[result]")
    for k, v in result.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    asyncio.run(main())
