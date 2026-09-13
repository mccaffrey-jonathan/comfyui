# SPDX-License-Identifier: Apache-2.0
"""ComfyUI custom node pack: C2PA Content Credentials for AI-generated images."""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:  # make the `content_credentials` library importable (also used by tests)
    sys.path.insert(0, _HERE)
_WM = os.path.join(os.path.dirname(_HERE), "comfyui_durable_watermark")
if os.path.isdir(_WM) and _WM not in sys.path:  # optional: secret redaction helper from the watermark pack
    sys.path.append(_WM)

try:
    import comfy_api.latest  # noqa: F401  (only available inside ComfyUI)
except ImportError:  # library / CLI / test usage outside ComfyUI
    comfy_entrypoint = None
else:
    from .cc_nodes import comfy_entrypoint  # noqa: E402,F401

__all__ = ["comfy_entrypoint"]
