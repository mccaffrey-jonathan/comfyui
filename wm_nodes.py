"""ComfyUI nodes for the durable watermark (V3 node API)."""
from __future__ import annotations

import json
import logging

import numpy as np
import torch
from typing_extensions import override

from comfy_api.latest import ComfyExtension, io

from durable_watermark.core import (
    SCHEME_ID,
    WatermarkConfig,
    detect,
    embed,
    payload_from_string,
    payload_to_hex,
)
from durable_watermark.keys import SecretError, resolve

log = logging.getLogger("durable_watermark")

WatermarkKey = io.Custom("WATERMARK_KEY")


def _config_from_key(key: dict) -> WatermarkConfig:
    return WatermarkConfig(**key["config"])


class DurableWatermarkKey(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="DurableWatermarkKey",
            display_name="Durable Watermark Key",
            category="watermark",
            description=(
                "Private key + payload for the durable watermark. The secret is the source's private value "
                "(user or inference provider). Prefer 'env:NAME' or 'file:PATH' over a literal secret, because "
                "ComfyUI stores widget values in output PNG metadata. Leave empty to use the server-side "
                "COMFYUI_WATERMARK_SECRET / config/watermark_secret.txt."
            ),
            inputs=[
                io.String.Input("secret", default="", placeholder="env:COMFYUI_WATERMARK_SECRET",
                                tooltip="Private value. Literal, 'env:NAME', 'file:PATH', or empty for server config."),
                io.String.Input("payload", default="",
                                tooltip="Payload: decimal or 0x-hex integer, or any string (hashed to payload_bits). "
                                        "E.g. a provider ID, model ID or a per-image UUID fragment."),
                io.Int.Input("payload_bits", default=32, min=0, max=64,
                             tooltip="Payload capacity. Fewer bits = more robust. 0 = presence-only (zero-bit)."),
                io.Float.Input("strength", default=1.0, min=0.25, max=3.0, step=0.05,
                               tooltip="1.0 ~ 41-45 dB PSNR. Use 1.5 if outputs will be recompressed (JPEG q<=75)."),
                io.Float.Input("r_min", default=0.05, min=0.02, max=0.3, step=0.005, optional=True,
                               tooltip="Lowest ring frequency (cycles/pixel)."),
                io.Float.Input("r_max", default=0.36, min=0.1, max=0.5, step=0.005, optional=True,
                               tooltip="Highest ring frequency (cycles/pixel). Lower = more JPEG/blur robust, fewer chips."),
                io.Float.Input("ring_width", default=0.004, min=0.001, max=0.02, step=0.0005, optional=True,
                               tooltip="Ring width (cycles/pixel). Keep >= 2 / (smallest expected image side)."),
                io.Boolean.Input("perceptual_mask", default=True, optional=True,
                                 tooltip="Texture-adaptive spatial masking of the watermark residual."),
                io.Boolean.Input("noise_floor", default=True, optional=True,
                                 tooltip="Keyed additive floor so flat regions still carry the mark."),
            ],
            outputs=[WatermarkKey.Output(display_name="key")],
        )

    @classmethod
    def execute(cls, secret, payload, payload_bits, strength, r_min=0.05, r_max=0.36, ring_width=0.004,
                perceptual_mask=True, noise_floor=True) -> io.NodeOutput:
        try:
            resolved = resolve(secret, payload, strength)
        except SecretError as exc:
            raise RuntimeError(str(exc)) from exc
        cfg = WatermarkConfig(
            secret=resolved.secret, payload_bits=int(payload_bits), strength=float(resolved.strength),
            r_min=float(r_min), r_max=float(r_max), ring_width=float(ring_width),
            perceptual_mask=bool(perceptual_mask), noise_floor=bool(noise_floor),
        )
        payload_int = payload_from_string(resolved.payload_text, cfg.payload_bits)
        key = {
            "config": {
                "secret": cfg.secret, "payload_bits": cfg.payload_bits, "strength": cfg.strength,
                "r_min": cfg.r_min, "r_max": cfg.r_max, "ring_width": cfg.ring_width,
                "perceptual_mask": cfg.perceptual_mask, "noise_floor": cfg.noise_floor,
            },
            "payload": payload_int,
            "payload_text": resolved.payload_text,
            "enforced": resolved.enforced,
            "key_fingerprint": cfg.key_fingerprint(),
        }
        return io.NodeOutput(key)


def _tensor_to_np(img: torch.Tensor) -> np.ndarray:
    return img.detach().cpu().numpy().astype(np.float64)


class DurableWatermarkEmbed(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="DurableWatermarkEmbed",
            display_name="Durable Watermark Embed",
            category="watermark",
            description=(
                "Embeds a keyed, imperceptible watermark in the luminance spectrum of each image. The mark "
                "survives rotation, flips, translation/crops, uniform rescaling, colour/brightness/gamma edits, "
                "moderate JPEG, noise and blur. Feed the 'watermark_record' output to the C2PA save node so the "
                "manifest carries a soft binding to the mark."
            ),
            inputs=[
                io.Image.Input("images"),
                WatermarkKey.Input("key"),
                io.String.Input("payload_override", default="", optional=True,
                                tooltip="Per-image payload override (e.g. a generation UUID fragment). Empty = key payload."),
            ],
            outputs=[
                io.Image.Output(display_name="images"),
                io.String.Output(display_name="payload_hex"),
                io.String.Output(display_name="watermark_record"),
            ],
        )

    @classmethod
    def execute(cls, images: torch.Tensor, key: dict, payload_override: str = "") -> io.NodeOutput:
        cfg = _config_from_key(key)
        payload = key["payload"]
        if payload_override and not key.get("enforced"):
            payload = payload_from_string(payload_override, cfg.payload_bits)
        out = []
        for i in range(images.shape[0]):
            arr = _tensor_to_np(images[i])
            marked = embed(arr, cfg, payload)
            out.append(torch.from_numpy(marked.astype(np.float32)))
        result = torch.stack(out, dim=0).to(images.device)
        record = {
            "scheme": SCHEME_ID,
            "payload_hex": payload_to_hex(payload, cfg.payload_bits),
            "payload_bits": cfg.payload_bits,
            "key_fingerprint": cfg.key_fingerprint(),
            "params": cfg.public_params(),
        }
        return io.NodeOutput(result, record["payload_hex"], json.dumps(record))


class DurableWatermarkDetect(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="DurableWatermarkDetect",
            display_name="Durable Watermark Detect",
            category="watermark",
            description=(
                "Blind detection of the durable watermark with the given key. Reports a calibrated z-score "
                "(null distribution built from wrong keys on the same image), the decoded payload, the "
                "estimated scale / rotation / flip, and whether the payload matches an expected value."
            ),
            inputs=[
                io.Image.Input("images"),
                WatermarkKey.Input("key"),
                io.String.Input("expected_payload", default="", optional=True,
                                tooltip="Optional expected payload (same formats as the key node). Empty = key payload."),
                io.Float.Input("z_threshold", default=5.0, min=2.0, max=20.0, step=0.5,
                               tooltip="Detection threshold on the calibrated z-score (5 ~ p < 3e-7 per image)."),
                io.Float.Input("min_scale", default=0.4, min=0.1, max=1.0, step=0.05),
                io.Float.Input("max_scale", default=2.5, min=1.0, max=8.0, step=0.1),
                io.Boolean.Input("aspect_search", default=False,
                                 tooltip="Also search anisotropic rescaling (0.8-1.25). ~8x slower."),
            ],
            outputs=[
                io.Boolean.Output(display_name="detected"),
                io.Float.Output(display_name="z_score"),
                io.String.Output(display_name="payload_hex"),
                io.Boolean.Output(display_name="payload_matches"),
                io.String.Output(display_name="report_json"),
            ],
        )

    @classmethod
    def execute(cls, images: torch.Tensor, key: dict, expected_payload: str = "", z_threshold: float = 5.0,
                min_scale: float = 0.4, max_scale: float = 2.5, aspect_search: bool = False) -> io.NodeOutput:
        cfg = _config_from_key(key)
        expect = key["payload"]
        if expected_payload:
            expect = payload_from_string(expected_payload, cfg.payload_bits)
        if cfg.payload_bits == 0:
            expect = None
        reports = []
        for i in range(images.shape[0]):
            res = detect(_tensor_to_np(images[i]), cfg, expected_payload=expect,
                         scale_range=(float(min_scale), float(max_scale)), aspect_search=bool(aspect_search),
                         z_threshold=float(z_threshold))
            reports.append(res.to_dict())
        detected = all(r["detected"] for r in reports)
        z = min(r["z_score"] for r in reports)
        payload_hex = reports[0]["payload_hex"]
        matches = all(bool(r["expected_match"]) for r in reports) if expect is not None else detected
        return io.NodeOutput(detected, float(z), payload_hex, bool(matches),
                             json.dumps(reports if len(reports) > 1 else reports[0], indent=2))


class DurableWatermarkExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [DurableWatermarkKey, DurableWatermarkEmbed, DurableWatermarkDetect]


async def comfy_entrypoint() -> DurableWatermarkExtension:
    return DurableWatermarkExtension()
