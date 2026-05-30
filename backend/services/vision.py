import json
from pathlib import Path

from config import settings

MOCK_VISION = {
    "search_query": "blue cotton crew neck t-shirt men",
    "item_type": "t-shirt",
    "color": "blue",
    "style": "casual crew neck",
}


async def analyze_image(image_path: Path) -> dict:
    """Return vision fields used for UCP search."""
    if not settings.gemini_api_key:
        return {**MOCK_VISION, "summary": "Blue cotton crew neck t-shirt (mock)"}

    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    image_bytes = image_path.read_bytes()
    prompt = (
        "Analyze this clothing item. Respond with JSON only, no markdown:\n"
        '{"search_query": "...", "item_type": "...", "color": "...", "style": "...", '
        '"summary": "one sentence description"}'
    )

    response = await model.generate_content_async(
        [
            prompt,
            {"mime_type": "image/jpeg", "data": image_bytes},
        ]
    )
    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return json.loads(text)
