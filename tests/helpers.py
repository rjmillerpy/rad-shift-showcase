"""Shared HTTP-level test helpers used by API contract tests.

These do NOT replace the DB-level fixtures in conftest (create_user/auth_header).
Use these when the test specifically verifies the signup/login HTTP contract.
"""

import io
from pathlib import Path

from openfeature import api
from openfeature.contrib.provider.flagd import FlagdProvider
from openfeature.contrib.provider.flagd.config import ResolverType
from PIL import Image, PngImagePlugin


def signup(client, username: str = "apiuser", password: str = "password123"):
    """Sign up a user via POST /auth/signup, return the Response."""
    return client.post(
        "/auth/signup",
        json={"username": username, "password": password, "email": f"{username}@test.com"},
    )


def login(client, username: str = "apiuser", password: str = "password123") -> dict:
    """Log in and return an Authorization header dict suitable for subsequent requests."""
    res = client.post("/auth/login", json={"username": username, "password": password})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def setup_user(client, username: str = "apiuser") -> dict:
    """Convenience: signup + login, return auth headers."""
    signup(client, username)
    return login(client, username)


def make_post(client, headers: dict, text: str = "Test post", **form_fields):
    """Create a post via POST /posts/add multipart form."""
    data = {"text": text, "post_metadata": "{}", "is_draft": "false", **form_fields}
    return client.post("/posts/add", data=data, headers=headers)


# ── Feature flags ───────────────────────────────────────────────────────────

FLAGS_FILE = Path(__file__).resolve().parent.parent / "flags" / "flags.flagd.json"


def serve_flags_file(path: Path) -> None:
    """Evaluate flags from `path` with the app's flagd provider, in its FILE mode."""
    api.set_provider_and_wait(
        FlagdProvider(resolver_type=ResolverType.FILE, offline_flag_source_path=str(path))
    )


def real_image(fmt: str = "JPEG") -> io.BytesIO:
    """A small, valid image file. Uploads are decoded to strip their metadata
    (app/common/images.py), so placeholder bytes named .jpg are rejected."""
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "orange").save(buf, format=fmt)
    buf.seek(0)
    return buf


# Images that say they were made by AI (app/common/provenance.py).
AI_IPTC_BASE = "http://cv.iptc.org/newscodes/digitalsourcetype/"


def xmp(source_type: str) -> bytes:
    """The XMP packet generators write: Iptc4xmpExt:DigitalSourceType."""
    return (
        '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/" '
        f'Iptc4xmpExt:DigitalSourceType="{AI_IPTC_BASE}{source_type}"/></rdf:RDF></x:xmpmeta>'
    ).encode()


def jpeg_with_xmp(source_type: str) -> io.BytesIO:
    out = io.BytesIO()
    Image.new("RGB", (8, 8), "teal").save(out, format="JPEG", xmp=xmp(source_type))
    out.seek(0)
    return out


def png_with_xmp(source_type: str) -> io.BytesIO:
    info = PngImagePlugin.PngInfo()
    info.add_itxt("XML:com.adobe.xmp", xmp(source_type).decode())
    out = io.BytesIO()
    Image.new("RGB", (8, 8), "teal").save(out, format="PNG", pnginfo=info)
    out.seek(0)
    return out


def jpeg_with_c2pa_segment() -> io.BytesIO:
    """A JPEG with an APP11 (JUMBF) segment like a C2PA manifest's: the
    c2pa.actions assertion names the digital source type as a CBOR text string."""
    plain = io.BytesIO()
    Image.new("RGB", (8, 8), "teal").save(plain, format="JPEG")
    payload = (
        b"JP\x00\x01jumb\x00c2pa\x00c2pa.actions"
        + (AI_IPTC_BASE + "trainedAlgorithmicMedia").encode()
    )
    segment = b"\xff\xeb" + (len(payload) + 2).to_bytes(2, "big") + payload
    data = plain.getvalue()
    return io.BytesIO(data[:2] + segment + data[2:])  # right after SOI
