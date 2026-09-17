# ComfyUI Durable Watermark

A **keyed, imperceptible, geometry-robust image watermark** for ComfyUI outputs, built
for AI-content transparency rules (EU AI Act Art. 50(2) "machine-readable marking",
California SB 942 "latent disclosure ... extraordinarily difficult to remove").

* **Private value per source.** A secret string chosen by the user or the inference
  provider drives every pseudo-random choice. Without it the mark is statistically
  invisible; with it you get presence detection with a calibrated z-score and a payload of
  up to 64 bits (provider ID, model ID, generation UUID fragment ...).
* **Frequency-domain, training-free, pure numpy/scipy.** No model weights, no GPU, ~0.8 s to
  embed and ~2 s to detect a 768 px image on one CPU core. Every line is auditable.
* **Invariant / robust to:** rotation (any angle, exact for 90-degree steps), flips,
  translation and cropping, uniform rescaling (0.4x to 2.5x searched), hue / saturation /
  brightness / contrast / gamma / grayscale, JPEG (payload to ~q75, presence to ~q50 at
  default strength), noise, blur, sharpening, and mild anisotropic scaling (optional search).
* **Honest statistics.** The detector builds an empirical null from wrong keys on the same
  image, so the false-positive estimate accounts for the geometric search.
* **Designed to pair with C2PA.** The `watermark_record` output feeds the
  [`ComfyUI-ContentCredentials`](https://github.com/mccaffrey-jonathan/ComfyUI-ContentCredentials) save node, which writes a
  `c2pa.soft-binding` assertion so the signed manifest can be recovered after metadata
  stripping ("durable content credentials").

The scheme is documented in
[the design overview](https://github.com/mccaffrey-jonathan/comfyui/tree/claude/ai-watermarking-compliance-0c2ubb/docs/ai-content-compliance/00-design-and-compliance-overview.md)
(with the legal and state-of-the-art research it is based on). Scheme id:
`org.comfyui.ringmark.v1`.

## Nodes

| Node | Purpose |
|---|---|
| **Durable Watermark Key** | Resolves the secret, payload, bits and strength into a `WATERMARK_KEY`. |
| **Durable Watermark Embed** | Marks a batch of images. `adaptive_strength` (default on) scales the key's strength x1.5 on texture-rich images (measured invisible even at 4x zoom) and x1.5 / x2 below 768 / 640 px so small images still decode. Outputs the images, the payload as hex and a JSON `watermark_record` for the C2PA node. |
| **Durable Watermark Detect** | Blind detection with a key: `detected`, calibrated `z_score`, a Gumbel-tail `p_value`, decoded `payload_hex`, `payload_matches`, and a JSON report with scale / rotation / flip estimates. |

Typical graph: `... -> VAE Decode -> Durable Watermark Embed -> Save Image with Content Credentials`.
Apply the watermark **before** any save node.

## Setting the private value

Precedence (first non-empty wins):

1. The key node's `secret` widget: a literal, `env:NAME` or `file:PATH`.
   **Prefer `env:` / `file:`** - ComfyUI stores every widget value of a workflow in the PNG
   metadata of saved images, so a literal secret would leak. The node logs a warning for
   literals; the C2PA save node redacts them from the metadata it writes.
2. `COMFYUI_WATERMARK_SECRET` (environment).
3. `COMFYUI_WATERMARK_SECRET_FILE` (path in environment).
4. `config/watermark_secret.txt` (git-ignored).
5. `secret` in `config/watermark.json` (git-ignored; see `watermark.json.example`).

**Inference providers**: set `COMFYUI_WATERMARK_ENFORCE=1` (or `"enforce": true` in
`config/watermark.json`). The server-side secret, payload (`COMFYUI_WATERMARK_PAYLOAD`),
strength (`COMFYUI_WATERMARK_STRENGTH`) **and every parameter the key schedule depends on**
(`COMFYUI_WATERMARK_PAYLOAD_BITS`, `_R_MIN`, `_R_MAX`, `_RING_WIDTH`, `_PERCEPTUAL_MASK`,
`_NOISE_FLOOR`, or the same keys in `watermark.json`) then override whatever a tenant's workflow
says, so a workflow can neither disable the mark nor produce one the provider's detector cannot
find. To keep per-image identifiers in enforce mode, set `COMFYUI_WATERMARK_PAYLOAD_LOW_BITS=n`:
the server owns the high bits (provider id, key epoch) and the embed node's `payload_override`
may fill only the low `n` bits (e.g. a generation UUID fragment).

Enforcement is node-level: nothing stops a tenant from wiring stock *Save Image* without the embed
node. A provider must enforce the pipeline server-side (a fixed save path, or a hook that rejects
workflows without the node).

**Key derivation.** The secret goes through scrypt (n=2^14) to a master key; the 8-byte
`key_fingerprint` published in the C2PA soft binding is an HMAC of that key, so confirming a guess
of the secret from the fingerprint costs a scrypt per guess. Use a long random secret anyway.

Payload formats: decimal (`4242`), hex (`0xC0FFEE42`), or any string (SHA-256 truncated to
`payload_bits`, e.g. `payload = "acme-provider"`). `payload_override` on the embed node lets a
workflow stamp a per-image value (e.g. the first 8 hex digits of a generation UUID).

## Strength and capacity

| strength | PSNR (photo / flat graphic / texture) | payload survives | presence survives |
|---|---|---|---|
| 1.0 (default) | 42.9 / 47.1 / 40.3 dB | JPEG q>=75 on photos, all geometric and colour edits | JPEG q50 |
| 1.5 | 39.3 / 43.5 / 36.6 dB | JPEG q>=50 on photos, q75 on flat graphics | heavier combos |

`payload_bits`: 32 by default; 0 makes a zero-bit (presence-only) mark where every chip is
sync; 64 is possible but halves the per-bit margin. A 32-bit identifier collides at ~77k
images (birthday bound); providers that need per-image ids should use 64 bits and strength 1.5. Advanced: `r_min`/`r_max` band,
`ring_width` (keep >= 2 / smallest image side; raise it for thumbnails), `perceptual_mask`,
`noise_floor`.

## Measured robustness (32-bit payload)

✅ payload decoded and CRC verified, 🟡 presence detected only, ❌ missed; number = z-score.

| Transform | photo s=1.0 | flat s=1.0 | texture s=1.0 | photo s=1.5 | flat s=1.5 | texture s=1.5 |
|---|---|---|---|---|---|---|
| identity / 8-bit PNG | ✅ 19 | ✅ 18 | ✅ 41 | ✅ 25 | ✅ 20 | ✅ 42 |
| JPEG q90 | ✅ 15 | ✅ 14 | ✅ 41 | ✅ 21 | ✅ 22 | ✅ 41 |
| JPEG q75 | ✅ 11 | ❌ 2 | ✅ 26 | ✅ 17 | ✅ 15 | ✅ 31 |
| JPEG q50 | 🟡 7 | ❌ 0 | ✅ 21 | ✅ 12 | ❌ 0 | ✅ 26 |
| resize 0.5x / 0.75x / 1.5x | ✅ 12 / 16 / 11 | ✅ 14 / 15 / 16 | ✅ 31 / 37 / 22 | ✅ 17 / 22 / 15 | ✅ 22 / 18 / 18 | ✅ 34 / 40 / 24 |
| rotate 90 / 7 / 30 | ✅ 19 / 10 / 11 | ✅ 18 / 10 / 15 | ✅ 41 / 20 / 23 | ✅ 25 / 15 / 17 | ✅ 20 / 16 / 21 | ✅ 42 / 25 / 30 |
| horizontal flip | ✅ 19 | ✅ 18 | ✅ 42 | ✅ 25 | ✅ 20 | ✅ 42 |
| centre crop 50 % / 25 % area | ✅ 16 / 13 | ✅ 11 / 7 | ✅ 36 / 22 | ✅ 21 / 18 | ✅ 14 / 11 | ✅ 35 / 26 |
| hue +60 / grayscale / saturation 2x | ✅ 15 / 18 / 14 | ✅ 13 / 18 / 15 | ✅ 37 / 41 / 41 | ✅ 20 / 24 / 21 | ✅ 18 / 20 / 18 | ✅ 39 / 42 / 41 |
| brightness 1.3 / contrast 0.7 / gamma 0.6 | ✅ 13 / 19 / 16 | ✅ 17 / 18 / 18 | ✅ 42 / 41 / 42 | ✅ 19 / 24 / 22 | ✅ 19 / 20 / 20 | ✅ 43 / 42 / 43 |
| noise sigma 5/255 / blur r1 / sharpen | ✅ 17 / 19 / 19 | 🟡 10 / ✅ 18 / ✅ 18 | ✅ 41 / 19 / 30 | ✅ 22 / 24 / 25 | ✅ 22 / 22 / 20 | ✅ 43 / 24 / 36 |
| rotate 15 + net 0.61x resize + JPEG q75 | ❌ 0 | ❌ 0 | ✅ 10 | ❌ 4 | ❌ -1 | ✅ 16 |
| anisotropic 1.2x horizontal (aspect search) | ✅ 9 | ✅ 11 | ✅ 21 | ✅ 15 | ✅ 14 | ✅ 26 |

Unmarked images and wrong keys score |z| < 3. Reproduce with `python tools/bench.py [strength] [payload_bits]` (add your own images to the
`images` dict) or via the CLI.

**Independent evaluation on ComfyUI renders.** An Opus-reviewed evaluation on 19 renders from
ComfyUI's bundled workflow templates (Flux, SDXL, SD 3.5, ControlNet outputs at 1024 px) is in
`docs/ai-content-compliance/reviews/image-quality-on-generated-images.md`: mean PSNR 39.9 dB /
SSIM 0.968 at strength 1.0, presence detected in 89-100 % of images across ten edits, payload
recovered in 63-95 % (100 % on most edits at strength 1.5), zero false positives in 38 negatives
and zero wrong payloads that passed the CRC in 380 detections. It found the mark visible at 4x
zoom in one image's sky at default strength; the perceptual mask has since been changed (the wide-blur
gain is capped by a narrow-blur view of the texture map, and the additive floor is no longer masked)
which cut that image's flat-region peak from 31 to 23 of 255 at unchanged robustness. PSNR mis-ranks this scheme: the residual scales with the
host's own in-band energy, so the lowest-PSNR images are the ones where it is least visible.

**Limitations.** Like every post-hoc watermark (SynthID and TrustMark included) it does not
survive diffusion regeneration, adversarial spectral attacks, or averaging many images marked
with one key; rotate keys and use per-image payloads. Flat synthetic graphics lose the
payload under JPEG <= 75 at default strength; WebP q80 is the worst lossy codec tested. Images
below ~640 px need strength 2 (the adaptive default does this). Extreme combined edits (net
< 0.65x downscale plus strong JPEG) exceed the band. This pack provides no public detection
service and no manifest registry (see the C2PA pack README); it is not a substitute for the
C2PA manifest: use both.

## Command line (for providers, CI and detection services)

```
cd ComfyUI/custom_nodes/ComfyUI-DurableWatermark
python -m durable_watermark embed  in.png out.png --secret env:WM_SECRET --payload acme-provider --adaptive
python -m durable_watermark detect out.png        --secret env:WM_SECRET --expect acme-provider --json
```

Exit code 0 = detected. The library API is two functions:

```python
from durable_watermark import WatermarkConfig, embed, detect, payload_from_string
cfg = WatermarkConfig(secret="...", payload_bits=32, strength=1.0)
marked = embed(rgb_float_hwc, cfg, payload_from_string("acme-provider", 32))
result = detect(marked, cfg)   # .detected, .z_score, .p_value (Gumbel tail), .payload_hex, .scale, .rotation_deg, .flipped
# recommended_strength(rgb, base) returns the content-adaptive strength the Embed node uses
```

## Install

Clone into `ComfyUI/custom_nodes/` (or install from the Comfy Registry / ComfyUI-Manager once
published). No dependencies beyond ComfyUI's numpy, scipy and Pillow.

```
cd ComfyUI/custom_nodes && git clone https://github.com/mccaffrey-jonathan/ComfyUI-DurableWatermark
```

## Tests

```
python -m pytest -q
```

## License and disclaimer

Apache License 2.0 (see `LICENSE` and `NOTICE`). Pure numpy/scipy; no third-party watermark
code or weights. The software is provided as is, without warranty or liability, and **without any
promise of regulatory compliance**: it does not make you compliant with the EU AI Act, SB 942 or
any other rule, it does not guarantee the mark cannot be removed or forged, and its statistics
are not guaranteed correct for any particular image. See `NOTICE`.
