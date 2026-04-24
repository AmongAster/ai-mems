from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Literal

from PIL import Image, ImageDraw, ImageFont

from .settings import settings


ProviderName = Literal["local_text", "openai_images"]


@dataclass
class GeneratedImage:
    content_type: str
    data: bytes


def _local_text_image(prompt: str) -> GeneratedImage:
    # Простая генерация “мема” локально: картинка + текст.
    w, h = 1024, 1024
    img = Image.new("RGB", (w, h), (25, 25, 28))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 44)
    except Exception:
        font = ImageFont.load_default()

    text = (prompt or "рандомный мем").strip()
    if len(text) > 140:
        text = text[:140] + "…"

    padding = 60
    max_width = w - padding * 2

    # very small wrapping helper
    words = text.split()
    lines: list[str] = []
    cur = ""
    for word in words:
        candidate = (cur + " " + word).strip()
        if draw.textlength(candidate, font=font) <= max_width:
            cur = candidate
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)

    y = padding
    for line in lines[:10]:
        draw.text((padding, y), line, fill=(245, 245, 245), font=font)
        y += int(font.size * 1.3)

    # нижняя подпись
    footer = "ai-mems"
    draw.text((padding, h - padding - 40), footer, fill=(160, 160, 170), font=font)

    buf = BytesIO()
    img.save(buf, format="PNG")
    return GeneratedImage(content_type="image/png", data=buf.getvalue())


def _openai_image(prompt: str) -> GeneratedImage:
    """
    Опциональный провайдер. Требует:
    - pip install openai
    - OPENAI_API_KEY в окружении
    """
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY не задан")
    try:
        from openai import OpenAI  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("Не установлен пакет openai. Сделай: pip install openai") from e

    client = OpenAI(api_key=settings.openai_api_key)
    # API может меняться, поэтому держим это максимально простым и безопасным.
    result = client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size="1024x1024",
    )
    b64 = result.data[0].b64_json
    import base64

    return GeneratedImage(content_type="image/png", data=base64.b64decode(b64))


def generate_meme_image(prompt: str) -> GeneratedImage:
    provider: ProviderName = settings.ai_provider  # type: ignore[assignment]
    if provider == "openai_images":
        return _openai_image(prompt)
    return _local_text_image(prompt)

