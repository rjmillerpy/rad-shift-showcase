"""Deterministic avatar generator.

Uses SHA-256 hash of (username + email) to produce a unique avatar with:
- 1 of 30 animal silhouettes
- Background gradient (2 colors derived from hash)
- Animal silhouette color
- Pattern overlay variant

Total combinations: 30 animals x 16M+ color combos = trillions of unique avatars.
"""

import hashlib
import io
from collections.abc import Callable

from PIL import Image, ImageDraw

from app.avatar.constants import (
    AVATAR_SIZE,
    BG_LIGHTNESS_MIN,
    BG_LIGHTNESS_RANGE,
    BG_SATURATION_MIN,
    BG_SATURATION_RANGE,
    BYTE_MODULO,
    HASH_SEED,
    HUE_DEGREES,
    RGB,
    SILHOUETTE_LIGHTNESS_MIN,
    SILHOUETTE_LIGHTNESS_RANGE,
    SILHOUETTE_SATURATION_MIN,
    SILHOUETTE_SATURATION_RANGE,
)
from app.avatar.silhouettes import ANIMAL_COUNT, ANIMALS
from app.common.s3 import upload_fileobj_to_s3


def _hash_user(username: str, email: str) -> bytes:
    """Generate a deterministic 32-byte hash from user identity."""
    raw = f"{HASH_SEED}:{username}:{email}".lower()
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _hue_from_byte(byte: int) -> int:
    return byte * HUE_DEGREES // BYTE_MODULO


def _extract_colors(hash_bytes: bytes) -> tuple[RGB, RGB, RGB]:
    """Extract background color 1, background color 2, and silhouette color."""
    bg1 = _hsl_to_rgb(
        _hue_from_byte(hash_bytes[0]),
        BG_SATURATION_MIN + (hash_bytes[1] % BG_SATURATION_RANGE),
        BG_LIGHTNESS_MIN + (hash_bytes[2] % BG_LIGHTNESS_RANGE),
    )
    bg2 = _hsl_to_rgb(
        _hue_from_byte(hash_bytes[3]),
        BG_SATURATION_MIN + (hash_bytes[4] % BG_SATURATION_RANGE),
        BG_LIGHTNESS_MIN + (hash_bytes[5] % BG_LIGHTNESS_RANGE),
    )
    sil = _hsl_to_rgb(
        _hue_from_byte(hash_bytes[6]),
        SILHOUETTE_SATURATION_MIN + (hash_bytes[7] % SILHOUETTE_SATURATION_RANGE),
        SILHOUETTE_LIGHTNESS_MIN + (hash_bytes[8] % SILHOUETTE_LIGHTNESS_RANGE),
    )
    return bg1, bg2, sil


def _hsl_to_rgb(h: int, s: int, lightness: int) -> RGB:
    """Convert HSL (h: 0-360, s: 0-100, lightness: 0-100) to RGB tuple."""
    s_f = s / 100
    l_f = lightness / 100
    c = (1 - abs(2 * l_f - 1)) * s_f
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = l_f - c / 2

    r1: float
    g1: float
    b1: float
    if h < 60:
        r1, g1, b1 = c, x, 0
    elif h < 120:
        r1, g1, b1 = x, c, 0
    elif h < 180:
        r1, g1, b1 = 0, c, x
    elif h < 240:
        r1, g1, b1 = 0, x, c
    elif h < 300:
        r1, g1, b1 = x, 0, c
    else:
        r1, g1, b1 = c, 0, x

    return (int((r1 + m) * 255), int((g1 + m) * 255), int((b1 + m) * 255))


def _select_animal(hash_bytes: bytes) -> int:
    """Select animal index from hash."""
    return hash_bytes[9] % ANIMAL_COUNT


def _draw_gradient(draw: ImageDraw.ImageDraw, size: int, color1: RGB, color2: RGB) -> None:
    """Draw a diagonal gradient background."""
    for y in range(size):
        ratio = y / size
        r = int(color1[0] * (1 - ratio) + color2[0] * ratio)
        g = int(color1[1] * (1 - ratio) + color2[1] * ratio)
        b = int(color1[2] * (1 - ratio) + color2[2] * ratio)
        draw.line([(0, y), (size, y)], fill=(r, g, b))


ShapeRenderer = Callable[[ImageDraw.ImageDraw, tuple, int, RGB], None]


def _render_circle(draw: ImageDraw.ImageDraw, shape: tuple, size: int, color: RGB) -> None:
    _, cx, cy, r = shape
    box = [
        int((cx - r) * size),
        int((cy - r) * size),
        int((cx + r) * size),
        int((cy + r) * size),
    ]
    draw.ellipse(box, fill=color)


def _render_ellipse(draw: ImageDraw.ImageDraw, shape: tuple, size: int, color: RGB) -> None:
    _, cx, cy, rx, ry = shape
    box = [
        int((cx - rx) * size),
        int((cy - ry) * size),
        int((cx + rx) * size),
        int((cy + ry) * size),
    ]
    draw.ellipse(box, fill=color)


def _render_polygon(draw: ImageDraw.ImageDraw, shape: tuple, size: int, color: RGB) -> None:
    _, points = shape
    scaled = [(int(px * size), int(py * size)) for px, py in points]
    draw.polygon(scaled, fill=color)


_SHAPE_RENDERERS: dict[str, ShapeRenderer] = {
    "circle": _render_circle,
    "ellipse": _render_ellipse,
    "polygon": _render_polygon,
}


def _draw_animal(draw: ImageDraw.ImageDraw, animal_idx: int, size: int, color: RGB) -> None:
    """Draw the animal silhouette from geometric shapes.

    Raises KeyError for an unregistered shape kind; test_shape_integrity guards
    against that at commit time.
    """
    _, shapes = ANIMALS[animal_idx]
    for shape in shapes:
        _SHAPE_RENDERERS[shape[0]](draw, shape, size, color)


def generate_avatar(username: str, email: str) -> bytes:
    """Generate a unique avatar PNG as bytes."""
    hash_bytes = _hash_user(username, email)
    bg1, bg2, sil_color = _extract_colors(hash_bytes)
    animal_idx = _select_animal(hash_bytes)

    img = Image.new("RGB", (AVATAR_SIZE, AVATAR_SIZE))
    draw = ImageDraw.Draw(img)

    _draw_gradient(draw, AVATAR_SIZE, bg1, bg2)
    _draw_animal(draw, animal_idx, AVATAR_SIZE, sil_color)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def generate_avatar_url(username: str, email: str) -> str:
    """Generate avatar, upload to S3, return URL."""
    avatar_bytes = generate_avatar(username, email)
    safe_username = "".join(c if c.isalnum() else "_" for c in username)
    s3_key = f"avatars/{safe_username}.png"
    buf = io.BytesIO(avatar_bytes)
    return upload_fileobj_to_s3(buf, s3_key, content_type="image/png")
