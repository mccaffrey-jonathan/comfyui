# Visual quality and robustness of the durable watermark on real ComfyUI renders

Scheme under test: `org.comfyui.ringmark.v1`
(`custom_nodes/comfyui_durable_watermark/durable_watermark/core.py`, pure numpy/scipy).
Date: 2026-09-17. CPU only (4 cores). Raw per-image numbers: [`image-quality-results.json`](image-quality-results.json).

The ComfyUI nodes in `wm_nodes.py` call `embed()` / `detect()` directly, so measuring the
library is measuring the node. **No watermark code was modified for this evaluation.**

---

## 1. Method

### Corpus

28 WebP renders produced from ComfyUI's bundled workflow templates. After inspecting each
one, 9 were excluded and **19 genuine generated images** were kept:

* Excluded as *control inputs*, not renders: `controlnet_example-2` (canny line art),
  `depth_controlnet-2`, `depth_t2i_adapter-2`, `flux_depth_lora_example-2` (depth maps),
  `flux_canny_model_example-2`, `sd3.5_large_canny_controlnet_example-2` (canny edge maps),
  `mixing_controlnets-2` (OpenPose skeleton + scribble).
* Excluded as *near-duplicates* of a kept image: `flux_fill_inpaint_example-2`,
  `inpaint_example-2`.

The kept set spans Flux dev/schnell/fill, SDXL base/refiner/revision/turbo, SD3.5-large,
ControlNet and T2I-adapter conditioned renders, and inpaint/outpaint outputs. 17 are
1024x1024, two are 1024x799 (outpaints), one is 512x512 (`sdxlturbo_example-1`).
Content ranges from photoreal portraits through painterly illustration, anime flat-graphic,
architectural renders with large flat skies, and a pencil-sketch cityscape.

### Protocol

Images are decoded to RGB float in [0,1]. A fixed 32-bit payload `0xC0FFEE42` is embedded
with a fixed secret at strengths 0.5 / 0.75 / 1.0 / 1.5 / 2.0:

```python
cfg = WatermarkConfig(secret=SECRET, payload_bits=32, strength=s)
marked = embed(rgb_float, cfg, 0xC0FFEE42)
```

**Every measurement and every detection is done on the 8-bit quantised result**
(`round(x*255)` clipped to [0,255]), i.e. exactly what a PNG save would hand downstream.
That matters: the residual is small enough that quantisation is a material part of the
channel, and reporting float-domain metrics would flatter the scheme.

Metrics per image and strength:

| metric | definition |
|---|---|
| PSNR | on 8-bit RGB, `10 log10(255^2 / MSE)` over all three channels |
| SSIM-Y | `skimage.metrics.structural_similarity`, `win_size=7`, `data_range=255`, on 8-bit BT.601 luma |
| SSIM-RGB | same, `channel_axis=2` (mean over channels) |
| MS-SSIM | 5-scale product with the standard Wang weights `[0.0448, 0.2856, 0.3001, 0.2363, 0.1333]`, win 7 |
| mean/max abs delta | on the 8-bit per-pixel max over RGB |
| %px >= 2, >= 4 | fraction of pixels whose max-over-RGB 8-bit delta reaches 2 / 4 LSB |
| **flat-region visibility** | max / mean / p99.9 of the 8-bit delta restricted to pixels whose **7x7 local std of the original luma is below 2/255** — sky, walls, backdrops, where ring texture has nothing to hide behind |

Caveat on MS-SSIM: this is a 5-scale product of *full* SSIM values rather than the
canonical CS-only terms at coarse scales. It tracks the same ordering but is slightly
pessimistic; treat the absolute number as indicative and the ranking as sound.

Detection uses `detect(rgb, cfg, expected_payload=...)` with the library defaults
(`z_threshold=5.0`, `n_null=96`, `scale_range=(0.4, 2.5)`). "Detected" means `z >= 5`;
"payload" means `expected_match` is true, which requires detection **and** CRC-8 pass
**and** an exact 32-bit payload match.

### Timing

| | mean | max |
|---|---|---|
| `embed` (1024x1024) | 0.47 s | 0.58 s |
| `detect` (1024x1024, clean) | 1.38 s | — |
| `detect` (rotated, 1290x1290 canvas) | 1.56 s | — |

Embedding is cheap enough to sit unconditionally at the end of a save pipeline; a full
380-detection robustness matrix ran in ~9 minutes across 4 processes.

---

## 2. Quality vs strength

All figures are means/medians/mins over the 19 images.

| strength | PSNR mean | PSNR median | PSNR min | SSIM-Y mean | SSIM-Y median | SSIM-Y min | SSIM-RGB mean | MS-SSIM mean | MS-SSIM min |
|---|---|---|---|---|---|---|---|---|---|
| 0.5 | 45.83 | 45.74 | 38.32 | 0.9908 | 0.9919 | 0.9809 | 0.9908 | 0.9974 | 0.9944 |
| 0.75 | 42.40 | 42.27 | 34.79 | 0.9808 | 0.9830 | 0.9606 | 0.9808 | 0.9942 | 0.9879 |
| **1.0** | **39.91** | **39.76** | **32.25** | **0.9678** | **0.9711** | **0.9351** | **0.9678** | **0.9900** | **0.9793** |
| 1.5 | 36.28 | 36.12 | 28.60 | 0.9345 | 0.9390 | 0.8748 | 0.9345 | 0.9784 | 0.9570 |
| 2.0 | 33.60 | 33.42 | 25.91 | 0.8938 | 0.8997 | 0.8085 | 0.8939 | 0.9628 | 0.9293 |

SSIM-Y and SSIM-RGB agree to four decimals, which is the first confirmation that the
residual is achromatic (section 4).

Pixel-domain amplitude and flat-region visibility:

| strength | mean abs delta | max abs delta (median / max) | %px >= 2 (mean / max) | %px >= 4 (mean / max) | **flat max (median / max)** | flat mean | flat p99.9 (median) |
|---|---|---|---|---|---|---|---|
| 0.5 | 0.91 | 13 / 24 | 19.2 / 57.5 | 3.7 / 23.4 | 10 / 15 | 0.60 | 5.0 |
| 0.75 | 1.40 | 20 / 35 | 31.8 / 70.3 | 9.4 / 40.4 | 15 / 23 | 0.96 | 7.0 |
| **1.0** | **1.90** | **26 / 47** | **42.2 / 77.4** | **15.6 / 52.2** | **20 / 31** | **1.31** | **10.0** |
| 1.5 | 2.92 | 40 / 69 | 57.3 / 84.9 | 27.6 / 66.5 | 30 / 46 | 2.02 | 15.0 |
| 2.0 | 3.99 | 54 / 91 | 66.9 / 88.9 | 38.1 / 74.8 | 42 / 62 | 2.77 | 21.0 |

Scaling is close to linear in `strength` for the amplitude statistics (mean abs delta
0.91 -> 1.90 -> 3.99 across a 4x strength range) and PSNR falls at a clean ~6 dB per
doubling, as expected for a residual whose amplitude is proportional to `strength`.

The flat-region row is the one that should worry an imaging engineer. At the default
strength the *median* worst-case excursion inside a genuinely flat region is 20 LSB, and
the 99.9th percentile there is 10 LSB. Those are not typos: the perceptual mask's floor is
`0.45` (see `_perceptual_mask`, gain clipped to `[0.45, 1.8]` then mean-normalised), so a
dead-flat sky still receives ~45% of nominal amplitude, and the mask is Gaussian-blurred
with `sigma=24 px`, which deliberately bleeds high gain from adjacent texture into flat
areas over a ~70 px skirt. The maxima are concentrated in exactly those skirts.

---

## 3. Perceptual inspection

Four representative images. For each, the 128x128 window with the highest mean |delta|
("worst") and the highest-|delta| window that is >90% flat ("flat") were located
automatically at strength 1.0, then cropped identically from the original, strength 1.0 and
strength 1.5, at 2x and 4x nearest-neighbour zoom, plus a x16-amplified difference map.

| role | image | worst-window local max | flat-window local max |
|---|---|---|---|
| smooth / painterly | `flux_schnell-1` (angel statues, large graded sky) | 34 | 21 |
| photoreal portrait | `flux_dev_checkpoint_example-1` (freckled face, teal backdrop) | 21 | 8 |
| high-frequency texture | `sdxl_revision_text_prompts-1` (pencil-sketch city, red car) | 47 | 10 |
| flat-graphic | `mixing_controlnets-1` (anime, flat red vending machine) | 42 | 11 |

Figures (all under `figures/`):

* [`figures/smooth_painterly_worst_4x.png`](figures/smooth_painterly_worst_4x.png),
  [`figures/smooth_painterly_flat_4x.png`](figures/smooth_painterly_flat_4x.png),
  [`figures/smooth_painterly_flat_2x.png`](figures/smooth_painterly_flat_2x.png),
  [`figures/smooth_painterly_flat_diff16.png`](figures/smooth_painterly_flat_diff16.png),
  [`figures/smooth_painterly_fullframe_diff16.png`](figures/smooth_painterly_fullframe_diff16.png)
* [`figures/photoreal_portrait_worst_4x.png`](figures/photoreal_portrait_worst_4x.png),
  [`figures/photoreal_portrait_flat_4x.png`](figures/photoreal_portrait_flat_4x.png)
* [`figures/highfreq_texture_worst_4x.png`](figures/highfreq_texture_worst_4x.png),
  [`figures/highfreq_texture_flat_4x.png`](figures/highfreq_texture_flat_4x.png),
  [`figures/highfreq_texture_fullframe_diff16.png`](figures/highfreq_texture_fullframe_diff16.png)
* [`figures/flat_graphic_worst_4x.png`](figures/flat_graphic_worst_4x.png),
  [`figures/flat_graphic_flat_4x.png`](figures/flat_graphic_flat_4x.png),
  [`figures/flat_graphic_flat_2x.png`](figures/flat_graphic_flat_2x.png)

(2x, 4x and diff16 variants exist for every image and window; the list above is the subset
worth opening first.)

### What is actually visible

I looked at each of these.

**High-frequency texture — invisible, masking works perfectly.** In
`highfreq_texture_worst_4x.png` the worst 128x128 window in the entire corpus by mean
delta (local max 47 LSB, on the pencil-sketched building facade) is, at 4x zoom and in
side-by-side comparison, *indistinguishable* between original, strength 1.0 and strength
1.5. Every cornice, window reveal and hatch line reads identically. This is the scheme
working as designed: it dumps its largest excursions where the eye has no reference.

**Photoreal portrait — invisible in content, faint grain in the backdrop.** The worst
window is the subject's eye (`photoreal_portrait_worst_4x.png`); lashes, iris texture and
skin are visually identical at 1.0 and 1.5. The flat teal backdrop
(`photoreal_portrait_flat_4x.png`) is the honest weak spot: at strength 1.0 there is a very
faint fine-grain mottle visible at 4x when A/B'd against the original, and at 1.5 it is
clearly a grain field. At 1x it is not something anyone would notice. This image has the
best flat-window number in the set (local max 8 LSB) because the backdrop is far from any
texture, so the sigma-24 mask skirt never reaches it.

**Flat-graphic (anime) — visible ripple at 1.5, marginal at 1.0.** In
`flat_graphic_flat_4x.png` the flat red vending-machine panel picks up a low-frequency
horizontal/wavy banding at strength 1.0 and an unmistakable one at 1.5. At 2x
(`flat_graphic_flat_2x.png`) the 1.0 case is only just detectable side-by-side and the 1.5
case is still visible. The textured half of `flat_graphic_worst_4x.png` (shelves, packaging
artwork) shows nothing; all the visible damage is on the flat red.

**Smooth/painterly — this is the failure case at default strength.**
`smooth_painterly_worst_4x.png` shows sky sandwiched between two heavily textured statues.
At strength 1.0 the sky is visibly mottled with a ripple/ring texture; at 1.5 it is
obviously dirty. `smooth_painterly_flat_4x.png` (sky adjacent to a wing) shows a diagonal
streak pattern at 1.0 that follows the direction of the neighbouring edge, and a stronger
one at 1.5. Even at 2x (`smooth_painterly_flat_2x.png`) the 1.0 ripple is perceptible as a
faint cirrus-like striation in what should be a clean gradient. **This is the one image in
the corpus where I would call the mark visible at default strength** on close inspection
of a clean gradient region — call it a "would fail a picky art director at 100% zoom"
rather than a "visible at thumbnail size" failure.

The mechanism is legible in `smooth_painterly_fullframe_diff16.png`: the residual is
strongly content-shaped (the statues glow, the sky is dim) — the mask is clearly doing
real work — but the mask's `sigma=24 px` Gaussian smears the statues' high gain tens of
pixels out into the surrounding sky, and those skirts are where the sky ripple lives.
`highfreq_texture_fullframe_diff16.png` shows the complementary picture: a dense, roughly
uniform residual with visible concentric ring structure around the car's wheel, which is
the DFT ring basis expressing itself around a strong compact feature.

### Colour: verified, with one caveat

`embed()` computes a scalar luminance delta and adds the *same* value to R, G and B, so in
principle chroma is untouched. Measured:

* SSIM-Y and SSIM-RGB agree to four decimal places at every strength.
* Across all 19 images at strengths 1.0 and 1.5, **1.63% of pixels** show any per-channel
  difference in the float-domain residual. **Every single one of them** (0 exceptions out
  of ~40 M pixels) is a pixel where the final `np.clip(rgb + delta, 0.0, 1.0)` actually
  clipped a channel at 0 or 1.
* In 8-bit, ~4.2% of pixels show a per-channel delta difference; ~2/3 of those are at or
  adjacent to 0/255 saturation, and the remainder is ordinary independent rounding of three
  channels that received an identical sub-LSB float delta.

So the claim "only luminance changes" is true up to output clipping. The practical
consequence: in blown highlights and crushed blacks the mark *does* produce a local chroma
nudge (up to 35 LSB of channel-to-channel deviation at strength 1.5 in the worst case).
That is least visible where it happens — a clipped highlight has no colour detail to
disturb — but it is a real effect and the graphic-heavy images with large saturated areas
(`mixing_controlnets-1` at 7.1% of pixels, `controlnet_example-1` at 3.2%) are the ones
that show it most.

---

## 4. Robustness

19 images x 2 strengths x 10 transforms = 380 detections, all against the 8-bit marked
image. "det%" is `z >= 5`; "pay%" is `expected_match` (detected AND CRC-8 OK AND exact
payload).

| transform | s=1.0 det% | pay% | median z | min z | s=1.5 det% | pay% | median z | min z |
|---|---|---|---|---|---|---|---|---|
| clean 8-bit round trip | 100 | 95 | 21.1 | 8.1 | 100 | **100** | 26.0 | 13.9 |
| JPEG q90 | 100 | 89 | 18.4 | 6.6 | 100 | **100** | 23.9 | 12.3 |
| JPEG q75 | 95 | 84 | 15.6 | 4.9 | 100 | **100** | 20.9 | 10.1 |
| JPEG q60 | 95 | 79 | 12.5 | 4.6 | 100 | 95 | 17.0 | 9.4 |
| WebP q90 | 100 | 84 | 16.5 | 6.2 | 100 | **100** | 22.5 | 11.8 |
| WebP q80 | 89 | 63 | 11.1 | 2.9 | 100 | 89 | 16.6 | 8.4 |
| downscale 0.5x (Lanczos) | 100 | 84 | 13.7 | 8.3 | 100 | **100** | 19.2 | 12.5 |
| rotate 15 deg (expand) | 95 | 89 | 15.5 | 4.2 | 100 | **100** | 20.7 | 9.7 |
| centre crop, 50% area | 100 | 84 | 18.0 | 5.5 | 100 | 89 | 23.0 | 10.3 |
| JPEG q80 + downscale 0.75x | 95 | 84 | 15.0 | 5.0 | 100 | **100** | 19.4 | 9.7 |

Geometry recovery is accurate: median estimated scale 0.499 for 0.5x, 0.749 for 0.75x,
1.000 for rotation and crop; median estimated rotation 16 deg for the 15 deg rotation
(the search grid is 2 deg, so 16 is one step off and within tolerance).

### False positives

| set | n | max z | median z | mean +- sd | detections at z>=5 | CRC passes |
|---|---|---|---|---|---|---|
| unmarked originals, correct key | 19 | **1.09** | -0.79 | -0.72 +- 0.74 | **0** | **0** |
| marked images, wrong key | 19 | **0.71** | -0.65 | -0.72 +- 0.61 | **0** | **0** |

Both negative sets are centred slightly below zero with unit-ish spread — the empirical
null calibration is behaving — and the largest excursion anywhere is z = 1.09, a factor of
~4.6 below the threshold. (Both sets exceed the 5 requested by the brief; all 19 were run.)

### CRC integrity

Across all 380 positive detections there were **zero cases where the CRC passed and the
payload was wrong**. 344/380 passed CRC; the 36 failures all correctly refused to report a
payload. Every "pay%" shortfall in the table above is a *silent* failure, not a false
attribution. That is the behaviour you want from an attribution system.

### Where the payload failures concentrate

Per-image, at strength 1.0, out of 10 transforms:

| image | size | clean z @1.0 | median z @1.0 | payload @1.0 | clean z @1.5 | payload @1.5 |
|---|---|---|---|---|---|---|
| `controlnet_example-1` | 1024x1024 | 33.7 | 24.8 | 10/10 | 43.6 | 10/10 |
| `sdxl_revision_text_prompts-1` | 1024x1024 | 25.4 | 23.0 | 10/10 | 32.1 | 10/10 |
| `mixing_controlnets-1` | 1024x1024 | 25.4 | 21.0 | 10/10 | 29.9 | 10/10 |
| `depth_t2i_adapter-1` | 1024x1024 | 24.9 | 17.7 | 10/10 | 31.0 | 10/10 |
| `flux_dev_checkpoint_example-1` | 1024x1024 | 24.0 | 18.9 | 10/10 | 29.4 | 10/10 |
| `flux_canny_model_example-1` | 1024x1024 | 23.6 | 17.6 | 10/10 | 28.3 | 10/10 |
| `flux_fill_outpaint_example-1` | 1024x1024 | 23.0 | 20.6 | 10/10 | 28.8 | 10/10 |
| `flux_schnell-1` | 1024x1024 | 22.7 | 17.8 | 10/10 | 29.4 | 10/10 |
| `inpaint_model_outpainting-2` | 1024x799 | 22.8 | 15.5 | 9/10 | 26.9 | 10/10 |
| `sdxl_refiner_prompt_example-1` | 1024x1024 | 21.1 | 18.2 | 10/10 | 26.0 | 10/10 |
| `inpaint_model_outpainting-1` | 1024x1024 | 19.9 | 14.0 | 10/10 | 26.0 | 10/10 |
| `flux_depth_lora_example-1` | 1024x1024 | 19.6 | 12.1 | 8/10 | 25.8 | 9/10 |
| `sdxl_simple_example-1` | 1024x1024 | 18.7 | 14.9 | 10/10 | 23.5 | 10/10 |
| `inpaint_example-1` | 1024x1024 | 17.0 | 11.9 | 9/10 | 21.3 | 10/10 |
| `sd3.5_large_canny_controlnet_example-1` | 1024x1024 | 16.8 | 12.6 | **4/10** | 22.9 | 10/10 |
| `flux_fill_inpaint_example-1` | 1024x1024 | 16.7 | 9.4 | 8/10 | 21.7 | 10/10 |
| `flux_fill_outpaint_example-2` | 1024x799 | 13.1 | 11.1 | 10/10 | 18.6 | 10/10 |
| `depth_controlnet-1` | 1024x1024 | 13.0 | 8.9 | **1/10** | 17.2 | 9/10 |
| `sdxlturbo_example-1` | **512x512** | 8.1 | 5.2 | **0/10** | 13.9 | 7/10 |

Three images account for almost all the strength-1.0 payload loss.
`sdxlturbo_example-1` fails to decode even on a **clean 8-bit round trip** at the default
strength. A controlled size sweep isolates the cause:

| image | resolution | s=1.0 | s=1.5 | s=2.0 |
|---|---|---|---|---|
| `flux_dev_checkpoint` | 1024 | z 23.95, min bit conf 7.21 | z 29.39, 7.49 | z 32.43, 7.57 |
| `flux_dev_checkpoint` | 768 | z 19.94, 6.75 | z 25.20, 7.39 | z 28.51, 7.66 |
| `flux_dev_checkpoint` | 512 | z 17.46, 5.57 | z 24.93, 6.67 | z 30.06, 7.08 |
| `sdxlturbo` (native) | 512 | z 8.07, **2.94, CRC fail** | z 13.90, 4.53 OK | z 18.09, 5.89 OK |

Resolution costs roughly 6.5 z-points from 1024 to 512 (fewer DFT samples per ring, so
lower per-chip SNR); content costs a further ~9 points on this particular image, which is
a shallow-depth-of-field bokeh photo with very little energy in the 0.05-0.36 c/px band
(6.8%) and almost none above it (0.21%) — a smooth image gives the ring modulation less
host energy to ride on and less texture to hide the noise floor in.

---

## 5. Quality vs content

Ranking the 19 images by PSNR at strength 1.0 (full table in section 2) against image
statistics:

| predictor | Pearson r vs PSNR | Spearman vs PSNR |
|---|---|---|
| fraction of luma spectral energy in 0.05-0.36 c/px (the mark's band) | **-0.821** | **-0.930** |
| fraction of energy above 0.36 c/px | -0.442 | -0.744 |
| fraction of pixels in flat regions (7x7 std < 2/255) | +0.501 | +0.419 |
| luma std | -0.226 | -0.221 |

**In-band spectral energy is almost a perfect rank predictor of PSNR.** This is a direct
consequence of the design: the mark is a *multiplicative* modulation of the log-magnitude
of the existing spectrum (`Fm = F * exp(s_map)`), so the residual amplitude in each ring is
proportional to the host's own energy in that ring. An image with 36% of its luma energy
in the watermark band (`sdxl_revision_text_prompts-1`, the pencil-sketch cityscape) gets a
residual ~13x larger in energy than one with 2.8% (`inpaint_example-1`), which is exactly
the 32.2 dB vs 42.3 dB PSNR spread observed.

That means **PSNR is a bad proxy for visibility in this scheme, and it is systematically
pessimistic for the images that look best.** The two lowest-PSNR images are:

* `sdxl_revision_text_prompts-1`, PSNR 32.25 dB, mean abs delta 4.74 LSB — and visually
  **indistinguishable** at 4x zoom (section 3). It is dense pencil hatching; the mark
  hides completely.
* `mixing_controlnets-1`, PSNR 36.38, SSIM-Y 0.9351 (the worst SSIM in the set) — anime
  flat-graphic. Here the low score *is* meaningful, because 41.6% of its pixels are flat,
  and the ripple on the red panel is visible at 4x.

Conversely `flux_schnell-1` sits mid-table on PSNR (37.29 dB) yet is the one image I would
flag as visibly marked at default strength, because it combines 61.2% flat pixels with
sharply textured statues whose mask gain bleeds into them.

The predictor that actually tracks what I saw is not PSNR and not SSIM but
**flat-region max delta combined with flat-region area**:

| image | flat max @1.0 | flat % of px | visible at 4x? |
|---|---|---|---|
| `flux_schnell-1` | 29 | 61.2 | **yes, clearly** — ripple in sky |
| `inpaint_example-1` | 28 | 46.1 | faint grain at 1.0, visible grain at 1.5 ([`figures/illustration_flat_4x.png`](figures/illustration_flat_4x.png)) |
| `mixing_controlnets-1` | 26 | 41.6 | **yes, banding on flat red** |
| `sdxl_revision_text_prompts-1` | 31 | 15.3 | no (flat region is car bodywork; faint streaks only) |
| `flux_dev_checkpoint_example-1` | 12 | 43.8 | no (faint grain only) |

(I opened each of these; `inpaint_example-1` was checked with a fifth figure rendered the
same way as the four in section 3. Its 28 LSB maximum sits in a flat patch adjacent to
texture; the *largest* flat region — the green backdrop shown in the figure — peaks at
only 8 LSB, again consistent with the halo mechanism.)

Note `flatmax` correlates with in-band energy (r = +0.40) but **not** with flat area
(r = -0.05) — confirming the skirt mechanism: the worst flat-region excursions come from
textured neighbours leaking gain through the sigma-24 blur, not from the flat area itself.

### Is the perceptual mask doing its job?

Partly yes, materially. The evidence for:

* The worst *absolute* excursions in the corpus (47 LSB) land on dense texture and are
  invisible even at 4x.
* Full-frame difference maps are strongly content-shaped (see
  `smooth_painterly_fullframe_diff16.png`).
* Flat-region mean delta at default strength is 1.31 LSB against an overall mean of 1.90 —
  the mask is holding flat regions ~30% below average.

The evidence against:

* The gain floor is 0.45 (`np.clip(gain, 0.45, 2.5)` before mean-normalisation, then
  `np.clip(gain, 0.45, 1.8)`). A dead-flat sky cannot be attenuated below 45% of nominal.
  Combined with the keyed additive noise floor (`_FLOOR_STD = 1/255` per unit strength,
  which is explicitly there so flat regions survive quantisation), flat areas are
  *guaranteed* a ~1 LSB RMS injection by design. That is a deliberate robustness/quality
  trade, not a bug — but it is the trade that produces the sky ripple.
* `sigma=24 px` is a very wide blur, chosen (per the docstring) so that multiplying the
  residual by the mask "barely smears the ring structure in the frequency domain". The
  cost is a ~70 px halo of elevated gain around every textured object, projected into
  adjacent flat areas. The measured flat-region maxima (median 20 LSB at default) live
  almost entirely in those halos.

So the mask trades flat-region fidelity for frequency-domain purity, and the frequency-domain
purity is what buys the rotation/scale/crop robustness in section 4. It is a coherent
design, but the flat-region cost is real and is the scheme's main perceptual limit.

---

## 6. Findings

1. **Default strength 1.0 is close to the right place, but it is not uniformly safe.**
   Mean PSNR 39.9 dB / SSIM-Y 0.968 / MS-SSIM 0.990, detection 89-100% and payload
   recovery 63-95% depending on transform. 12 of 19 images recover the payload under every
   one of the 10 transforms tested, and of the 5 images I inspected pixel-for-pixel at 4x
   zoom, 3 show nothing and 2 show flat-region artefacts.
2. **Detection presence is much more robust than payload recovery.** At strength 1.0
   detection holds at >= 89% everywhere, while payload recovery drops to 63% under WebP
   q80. If the deployment question is "is this ours?" the default is fine; if it is "which
   job produced this?" the default is not enough.
3. **Strength 1.5 is where payload recovery becomes dependable** — 100% on 7 of 10
   transforms, >= 89% on all — but it is also where the mark becomes visible on flat
   gradients and flat-graphic content.
4. **The mark is visible at default strength on exactly one corpus image**
   (`flux_schnell-1`, sky between textured statues), and marginally on flat-graphic panels
   (`mixing_controlnets-1`). Both are flat-region failures caused by the mask's 0.45 gain
   floor plus its 24 px blur skirt.
5. **Luminance-only is confirmed**, with the single documented exception of output clipping
   at already-saturated pixels (1.63% of pixels, all provably clip-caused).
6. **Below ~768 px the default strength is under-powered.** A 512x512 render loses ~6.5
   z-points to resolution alone and can fail CRC on a clean round trip.
7. **No false positives and no false attributions.** 38 negative detections peaked at
   z = 1.09 against a threshold of 5; 380 positive detections produced zero CRC-passing
   wrong payloads.
8. **PSNR mis-ranks this scheme.** Because the modulation is multiplicative in the
   spectrum, PSNR tracks host in-band energy (Spearman -0.93) rather than perceptibility.
   The lowest-PSNR image in the corpus is among the most visually clean.

## 7. Recommendations

**Default strength.** Keep 1.0 as the shipped default for images >= 768 px. It is the right
balance for the presence-detection use case and it is imperceptible on the large majority
of generated content. Do not raise the global default to 1.5 — the flat-region cost on
skies and flat-graphic art is a real regression and would be noticed.

**Adopt content-adaptive strength.** The cheapest high-value change. Compute, before
embedding, the two statistics this evaluation shows are predictive, and pick strength from
them (all obtainable from one 7x7 local-std pass and one FFT, i.e. a few hundred ms):

| condition | suggested strength | rationale |
|---|---|---|
| flat fraction > 40% **and** in-band energy < 8% | 0.75-1.0, and cap the mask skirt (below) | smooth/painterly and flat-graphic: visibility-limited |
| in-band energy > 15% | 1.5 | texture-rich: measured invisible at 4x even at 1.5; buy the robustness for free |
| min side < 768 px | 1.5; min side < 640 px, use 2.0 | compensates the ~6.5 z-point resolution penalty |
| otherwise | 1.0 | |

Under this policy every image in the corpus would have recovered its payload on a clean
round trip, and the two visible-at-1.0 images would have been marked more gently.

**If payload attribution (not just presence) is the product requirement**, either ship
strength 1.5 by default and accept the flat-region cost, or reduce `payload_bits` from 32.
Bit confidence, not presence z, is what fails first: `sdxlturbo` at strength 1.0 had a
healthy z of 8.1 but a minimum bit confidence of 2.94. Fewer payload bits means more chips
per bit and a proportionally larger margin at the same visual cost.

**Fix the flat-region skirt, not the strength.** Two targeted changes to
`_perceptual_mask` would address the only genuine visibility failures found, without
touching the frequency-domain design that the robustness depends on:

* Use a min-filter (erosion) of the local-std map before the Gaussian blur, so the smoothed
  gain in a flat region reflects the *flat* neighbourhood rather than the textured one
  ~24 px away. This kills the halo that produced the `flux_schnell-1` sky ripple.
* Consider lowering the gain floor from 0.45 toward ~0.30 for images with a large flat
  fraction, compensating with a higher global strength so total mark energy (and therefore
  z) is unchanged. This moves energy out of skies and into texture where it is free.

(Both are code changes to the library and were deliberately **not** made or measured here.)

**Documented limits.**

* Flat gradients (skies, studio backdrops, flat-colour graphic panels) are the perceptual
  limit. At 4x zoom the mark is visible there at strength >= 1.5 on most content and at 1.0
  on the worst case.
* Images below ~640 px should not be marked at default strength if the payload matters.
* WebP q80 is the worst lossy codec tested for payload survival (63% at strength 1.0);
  JPEG is gentler at nominally comparable quality settings.
* Clipped highlights/shadows receive a small local chroma perturbation.
* Not tested here and still open: repeated re-encoding chains, aspect-ratio distortion
  (`aspect_search=False` was used throughout), heavy denoise/sharpen filters, and — as the
  library's own docstring states — diffusion regeneration, which no post-hoc pixel
  watermark survives.

---

### Reproduction

Scripts used (scratchpad, not checked in):
`quality.py` (metrics), `robust.py` (transform matrix + negatives), `figures.py` (crops and
difference maps), `chroma.py` (luminance-only verification). All raw per-image, per-strength
and per-transform records are in
[`image-quality-results.json`](image-quality-results.json).
