# SPDX-License-Identifier: Apache-2.0
"""Durable, keyed, rotation/scale/translation-robust image watermark (pure numpy)."""
from .core import (  # noqa: F401
    SCHEME_ID,
    DetectionResult,
    KeySchedule,
    WatermarkConfig,
    crc8,
    detect,
    embed,
    image_statistics,
    payload_from_string,
    payload_to_hex,
    recommended_strength,
)
from .keys import (  # noqa: F401
    SecretError,
    redact_extra_pnginfo,
    redact_prompt,
    redact_values,
    resolve,
    resolve_payload,
    resolve_secret,
    resolve_strength,
)

__version__ = "0.1.0"
