"""The results-queue message, validated before anything is written (rule 5)."""

from pydantic import Field

from app.common.schema import FrozenModel


class VariantResult(FrozenModel):
    """One resized upload: its S3 location, its width and the variant key per width."""

    bucket: str = Field(min_length=1)
    source_key: str = Field(min_length=1)
    # The original's displayed width (after EXIF rotation).
    width: int = Field(gt=0)
    # {"480": "variants/posts/x-480.webp"}; widths are JSON object keys.
    variants: dict[str, str] = Field(min_length=1)
