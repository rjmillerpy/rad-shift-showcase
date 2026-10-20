"""Shared constants for the avatar generator.

Centralises the HSL colour ranges and canvas size so the generator itself
reads as intent, not a series of magic numbers.
"""

AVATAR_SIZE = 256
HASH_SEED = "radshift-avatar-v1"

# Hue is derived directly from the hash byte * 360 // 256, so no explicit bounds.
# Saturation and lightness are constrained to visually pleasant ranges.
BG_SATURATION_MIN = 40
BG_SATURATION_RANGE = 40  # exclusive upper bound: 80
BG_LIGHTNESS_MIN = 25
BG_LIGHTNESS_RANGE = 30  # exclusive upper bound: 55

SILHOUETTE_SATURATION_MIN = 20
SILHOUETTE_SATURATION_RANGE = 60  # exclusive upper bound: 80
SILHOUETTE_LIGHTNESS_MIN = 70
SILHOUETTE_LIGHTNESS_RANGE = 25  # exclusive upper bound: 95

HUE_DEGREES = 360
BYTE_MODULO = 256

# Public inputs to the /avatar/preview endpoint are unauthenticated; cap them
# so a caller cannot force megabyte-sized SHA-256 inputs.
MAX_PREVIEW_USERNAME_LEN = 80
MAX_PREVIEW_EMAIL_LEN = 255


RGB = tuple[int, int, int]
