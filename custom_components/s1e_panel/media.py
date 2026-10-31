"""Pictures for the panel: camera frames, image entities and notification photos.

The panel decodes baseline JPEG no larger than its screen, so every picture is
fitted into the requested box and re-encoded here, in Home Assistant.
"""
from __future__ import annotations
import base64
import io
import re

from .const import DOMAIN

ENTITY = re.compile(r"^(camera|image)\.[a-z0-9_]{1,240}$")
MAX_SIDE = 480
MAX_BYTES = 512 * 1024


def allowed_media(hass) -> set[str]:
    """Cameras that service calls showed on a panel (a live doorbell photo)."""
    return hass.data.setdefault(f"{DOMAIN}_media", set())


def fit_jpeg(content: bytes, width: int, height: int, fit: str = "contain") -> tuple[bytes, int, int]:
    """Any picture → baseline JPEG inside width × height, or cropped to fill it (runs in the executor)."""
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(content)) as source:
        picture = ImageOps.exif_transpose(source).convert("RGB")
    if fit == "cover":
        picture = ImageOps.fit(picture, (width, height), Image.Resampling.LANCZOS)
    else:
        picture.thumbnail((width, height), Image.Resampling.LANCZOS)
    for quality in (78, 65, 50):
        out = io.BytesIO()
        picture.save(out, "JPEG", quality=quality, optimize=True, progressive=False)
        if out.tell() <= MAX_BYTES:
            return out.getvalue(), picture.width, picture.height
    raise ValueError("picture too large")


async def fetch_jpeg(hass, entity_id: str, width: int, height: int, fit: str = "contain") -> dict:
    """The current picture of a camera or image entity as {jpeg (base64), width, height}."""
    if not isinstance(entity_id, str) or not ENTITY.match(entity_id):
        raise ValueError
    if fit not in ("contain", "cover"):
        raise ValueError
    if type(width) is not int or type(height) is not int or not (16 <= width <= MAX_SIDE and 16 <= height <= MAX_SIDE):
        raise ValueError
    if entity_id.startswith("camera."):
        from homeassistant.components.camera import async_get_image

        content = (await async_get_image(hass, entity_id, timeout=10)).content
    else:
        component = hass.data.get("image")  # EntityComponent of the image platform
        entity = component.get_entity(entity_id) if component else None
        if entity is None:
            raise ValueError
        content = await entity.async_image()
        if not content:
            raise ValueError
    data, w, h = await hass.async_add_executor_job(fit_jpeg, content, width, height, fit)
    return {"jpeg": base64.b64encode(data).decode("ascii"), "width": w, "height": h}
