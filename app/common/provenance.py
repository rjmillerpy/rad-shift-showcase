"""Does an uploaded image say it was made by AI? Read before its metadata is stripped.

Generators that follow the industry standards mark their output with the
IPTC "digital source type" for AI media, either in the image's XMP metadata
or inside a C2PA content-credentials manifest (OpenAI, Adobe Firefly,
Google, Microsoft and others). Both store the term as plain text, so a scan
of the file's bytes finds it without parsing either format.

What this can't do: verify a C2PA signature (a forged marker only labels the
uploader's own post as AI, so nothing is gained by forging one), or find AI
images whose metadata is gone (screenshots, most re-saves, many tools) or
that carry only an invisible watermark. A missing marker proves nothing.
"""

from typing import BinaryIO

# IPTC NewsCodes digitalsourcetype terms for media made by generative AI
# (cv.iptc.org/newscodes/digitalsourcetype/). Not plain "algorithmicMedia":
# that is procedural art with no trained model (fractals), not AI.
AI_SOURCE_TYPES = (
    b"trainedAlgorithmicMedia",
    b"compositeWithTrainedAlgorithmicMedia",
)
_CHUNK_BYTES = 1024 * 1024
# Carried between chunks, so a term split across two reads is still found.
_OVERLAP_BYTES = max(len(term) for term in AI_SOURCE_TYPES) - 1


def declares_ai_generated(fileobj: BinaryIO) -> bool:
    """True if the file carries an AI digital-source-type marker. Leaves it at the start."""
    fileobj.seek(0)
    tail = b""
    try:
        while chunk := fileobj.read(_CHUNK_BYTES):
            window = tail + chunk
            if any(term in window for term in AI_SOURCE_TYPES):
                return True
            tail = window[-_OVERLAP_BYTES:]
        return False
    finally:
        fileobj.seek(0)
