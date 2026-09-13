"""ComfyUI custom node pack: durable, keyed, geometry-robust image watermarking."""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:  # make the `durable_watermark` library importable (also used by the CLI/tests)
    sys.path.insert(0, _HERE)

try:
    import comfy_api.latest  # noqa: F401  (only available inside ComfyUI)
except ImportError:  # library / CLI / test usage outside ComfyUI
    comfy_entrypoint = None
else:
    from .wm_nodes import comfy_entrypoint  # noqa: E402,F401

__all__ = ["comfy_entrypoint"]
