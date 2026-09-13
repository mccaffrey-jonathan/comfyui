"""Command line interface, so inference providers can mark/verify outside ComfyUI.

    python -m durable_watermark embed  in.png out.png --secret env:WM_SECRET --payload 0xC0FFEE42
    python -m durable_watermark detect out.png --secret env:WM_SECRET [--expect 0xC0FFEE42] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np

from .core import WatermarkConfig, detect, embed, payload_from_string, payload_to_hex
from .keys import resolve_payload, resolve_secret, resolve_strength


def _load(path: str) -> np.ndarray:
    from PIL import Image

    im = Image.open(path)
    mode = "RGBA" if im.mode in ("RGBA", "LA", "P") and "transparency" in im.info or im.mode == "RGBA" else "RGB"
    return np.asarray(im.convert(mode), dtype=np.float64) / 255.0


def _save(path: str, arr: np.ndarray, quality: int) -> None:
    from PIL import Image

    im = Image.fromarray(np.clip(arr * 255.0 + 0.5, 0, 255).astype(np.uint8))
    kw = {}
    if path.lower().endswith((".jpg", ".jpeg", ".webp")):
        kw["quality"] = quality
        if im.mode == "RGBA" and path.lower().endswith((".jpg", ".jpeg")):
            im = im.convert("RGB")
    im.save(path, **kw)


def _cfg(args) -> WatermarkConfig:
    return WatermarkConfig(
        secret=resolve_secret(args.secret),
        payload_bits=args.bits,
        strength=resolve_strength(args.strength),
        r_min=args.r_min,
        r_max=args.r_max,
        ring_width=args.ring_width,
        perceptual_mask=not args.no_mask,
        noise_floor=not args.no_floor,
    )


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="durable_watermark", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--secret", default="", help="literal, env:NAME or file:PATH (default: server config)")
        sp.add_argument("--bits", type=int, default=32, help="payload bits (0-64)")
        sp.add_argument("--strength", type=float, default=1.0)
        sp.add_argument("--r-min", type=float, default=0.05)
        sp.add_argument("--r-max", type=float, default=0.36)
        sp.add_argument("--ring-width", type=float, default=0.004)
        sp.add_argument("--no-mask", action="store_true")
        sp.add_argument("--no-floor", action="store_true")

    e = sub.add_parser("embed", help="embed a watermark")
    e.add_argument("input")
    e.add_argument("output")
    e.add_argument("--payload", default="", help="int, 0xhex, or any string (hashed)")
    e.add_argument("--quality", type=int, default=95, help="JPEG/WebP quality")
    common(e)

    d = sub.add_parser("detect", help="detect / decode a watermark")
    d.add_argument("input")
    d.add_argument("--expect", default=None, help="expected payload (int, 0xhex or string)")
    d.add_argument("--threshold", type=float, default=5.0)
    d.add_argument("--min-scale", type=float, default=0.4)
    d.add_argument("--max-scale", type=float, default=2.5)
    d.add_argument("--aspect", action="store_true", help="also search anisotropic rescaling")
    d.add_argument("--json", action="store_true")
    common(d)

    args = p.parse_args(argv)
    cfg = _cfg(args)

    if args.cmd == "embed":
        payload = payload_from_string(resolve_payload(args.payload), cfg.payload_bits)
        img = _load(args.input)
        out = embed(img, cfg, payload)
        _save(args.output, out, args.quality)
        print(json.dumps({"output": args.output, "payload": payload_to_hex(payload, cfg.payload_bits),
                          "key_fingerprint": cfg.key_fingerprint(), "scheme": "org.comfyui.ringmark.v1"}))
        return 0

    img = _load(args.input)
    expect = payload_from_string(args.expect, cfg.payload_bits) if args.expect is not None else None
    res = detect(img, cfg, expected_payload=expect, scale_range=(args.min_scale, args.max_scale),
                 aspect_search=args.aspect, z_threshold=args.threshold)
    if args.json:
        print(json.dumps(res.to_dict(), indent=2))
    else:
        print(f"detected={res.detected} z={res.z_score:.2f} p={res.p_value:.2e} payload={res.payload_hex} "
              f"crc_ok={res.crc_ok} scale={res.scale:.3f} rotation={res.rotation_deg:.1f}deg flipped={res.flipped}"
              + (f" expected_match={res.expected_match}" if expect is not None else ""))
    return 0 if res.detected else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
