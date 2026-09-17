# RingMark on a 100-image corpus: fidelity, robustness and false-positive review

Scheme under test: `org.comfyui.ringmark.v1`
(`custom_nodes/comfyui_durable_watermark/durable_watermark/core.py`, pure numpy/scipy).
Date: 2026-09-17. CPU only, 4 workers. No watermark code was modified for this evaluation.

Raw numbers: [`corpus-100-results.json`](corpus-100-results.json) (per image, per condition, per
transform). Corpus list: [`corpus-100-manifest.json`](corpus-100-manifest.json). Harness:
`custom_nodes/comfyui_durable_watermark/tools/eval_corpus.py`, which is the normative definition of
every metric and transform named below.

---

## 1. Summary

* **Fidelity at the default strength 1.0 is stable across 100 images**: PSNR median 39.0 dB
  (p10 35.1, worst 29.6), SSIM-Y median 0.962, MS-SSIM median 0.992, mean absolute residual
  1.98 LSB. The spread is driven almost entirely by content, not by resolution.
* **Presence detection is strong, payload recovery is not.** Over 38 transforms (excluding the
  one that is outside the detector's search range), strength 1.0 gives 91.7 % detection and
  81.9 % exact-payload recovery; strength 1.5 gives 97.4 % and 94.4 %.
* **Zero false positives in 1300 negative detections.** 900 unmarked images under the correct
  keys peaked at z = 3.86, 400 marked images under wrong keys peaked at z = 2.45, against a
  threshold of 5. Across 14 700 positive detections there was no case where a detection at
  z >= 5 passed CRC-8 with the wrong payload.
* **The detector has a hard scale ceiling at exactly 2.0x, not the 2.5x its `scale_range`
  default advertises.** A marked image upscaled 2.05x is undetectable (z ~ 0) while 2.00x is
  fine. This is the real reason the "social(1080+jpeg80)" transform scores 0 % on the 400 px
  tier: 400 -> 1080 is a 2.7x upscale.
* **Widening `scale_range` to (0.3, 3.0) partly recovers 0.35x downscale** (detection 9/12
  instead of 0/12, payload 4/12) at a 25 % detection-time cost, and does nothing for the
  upscale case, because that failure is not a search-range failure.
* **The content-adaptive policy in `recommended_strength()` improves robustness materially**
  (81.9 % -> 92.5 % payload) but it raises strength on exactly the images where the mark is
  most visible, because it keys on in-band energy and ignores the flat-region fraction that
  `image_statistics()` already computes.
* **Visual inspection of the five worst-scoring images** shows the mark is invisible on
  photographic and painterly content even at PSNR 31.5 dB, and plainly visible on synthetic
  line art and high-contrast greyscale graphics.
* **64-bit payloads are not usable at default strength**: 76 % recovery on a clean round trip,
  19 % after a rotate plus resize plus JPEG combination.

---

## 2. Method

### What the corpus is, and what it is not

The original request was to render 100 new images from diverse prompts. **This sandbox has no
GPU and cannot reach any model host, so that could not be done here.** What was evaluated
instead is a corpus of 100 renders that ComfyUI's own workflow-template packages ship as
example outputs, collected by unpacking 73 published versions of the `comfyui-workflow-templates`
family of PyPI packages and taking the union of distinct images (11 of those wheels contributed
at least one unique image). Two tiers:

| tier | n | size | what they are |
|---|---|---|---|
| `full` | 70 | 512 to 3000 px on the long side, 5 of them downscaled to 1024 for the evaluation | 53 primary template outputs plus 17 secondary images, the latter including a few control inputs (depth maps, canny edge maps, pose skeletons) |
| `thumb` | 30 | 400x400 | primary outputs of image-generation templates that the newer packages ship only as 400 px thumbnails, many of them API-model templates (Flux Kontext, GPT-image, Recraft, Stability SD3/SD3.5, Seedream, Qwen-Image, Z-Image) |

Contact sheet: [`figures/corpus100/corpus_contact_sheet.jpg`](figures/corpus100/corpus_contact_sheet.jpg).

Two consequences must be kept in view when reading the results:

1. The `thumb` tier is **not** a sample of native 400 px renders. These are downsampled versions
   of larger renders, so their spectra are unusually clean (median in-band energy 0.118 against
   0.061 for the full tier) and their flat fraction is low (0.247 against 0.480). They are a fair
   proxy for "a small image arriving at the watermarker", not for "a small render".
2. Prompt diversity is whatever the template authors happened to choose, which skews towards
   portraits, product shots and fantasy illustration, plus a tail of control maps. A 100-prompt
   set spanning ten content categories (`tools/corpus/prompts.json`) and a generation harness
   (`tools/corpus/generate_corpus.py`) were written so the same evaluation can be re-run on a
   prompt-diverse corpus on a GPU machine.

### Protocol

Each image is decoded to RGB float, downscaled to a maximum side of 1024 if larger, and marked.
**Every measurement and every detection is done on the 8-bit quantised marked image**
(`round(x*255)` clipped), which is what a PNG save hands downstream. Conditions per image:
strength 1.0 under three independent keys (`corpus-eval-2026::site-key-00/01/02`, per-image and
per-key 32-bit payloads from SHA-256 of `"{image_id}|{key}"`), key 0 over all 39 transforms and
keys 1 and 2 over a 15-transform core subset; strength 1.5 and the adaptive strength from
`recommended_strength()`, key 0, all 39 transforms; zero-bit and 64-bit modes on their own
subsets; and negatives, meaning the unmarked image under all three keys (identity, JPEG 75, 0.5x
resize) and the marked image under two keys that were never used to embed (identity, JPEG 75).

Detection uses library defaults: `z_threshold=5.0`, `n_null=96`, `scale_range=(0.4, 2.5)`,
`aspect_search` only for the aspect-distortion transform. "Detected" means z >= 5. "Payload" means
`expected_match`, which requires detection **and** CRC-8 pass **and** an exact payload match. The
fidelity metrics are defined in `fidelity()` in the harness. Note that the flat-region statistic
here is the residual inside the **flattest 5 % of 32x32 blocks**, a different estimator from the
"7x7 local std below 2/255" used in the earlier 19-image report; the two are not comparable.

Scale: 700 embeds and 17 700 detections, 9.1 CPU-hours, 8268 s wall on 4 workers. Median embed
0.72 s at 1024 px and 0.14 s at 400 px; median detection about 1.9 s.

---

## 3. Fidelity

[`figures/corpus100/fidelity_hist.png`](figures/corpus100/fidelity_hist.png)

| condition | PSNR median (p10..p90) | SSIM-Y median | MS-SSIM median | mean abs | max abs (max) | flat p99.9 median (max) | chroma max |
|---|---|---|---|---|---|---|---|
| s1.0 | 39.0 (35.1..42.8) | 0.962 | 0.9920 | 1.98 | 27 (92) | 6 (13) | 35 |
| s1.5 | 35.2 (31.4..39.2) | 0.920 | 0.9810 | 3.05 | 42 (139) | 9 (21) | 55 |
| adaptive | 35.0 (29.1..42.7) | 0.907 | 0.9780 | 3.07 | 42 (139) | 9 (28) | 63 |

By tier, at strength 1.0: full 39.4 dB median, thumb 37.0 dB. The 2.4 dB gap is content, not size:
the thumbnails carry proportionally more in-band energy.

**The adaptive row mixes tiers and should not be read as a fidelity number.**
`recommended_strength()` picks 2.0 for every one of the 30 thumbnails (min side below 640) and for
17 full-tier images, 1.5 for 11 images (in-band energy above 0.15), and leaves 1.0 for 42. Split by
what it chose, its PSNR medians are 41.4 dB (chose 1.0), 32.7 dB (chose 1.5) and 31.2 dB (chose
2.0). See [`figures/corpus100/adaptive_strength.png`](figures/corpus100/adaptive_strength.png).

### PSNR tracks host spectrum, not visibility

[`figures/corpus100/psnr_vs_band_energy.png`](figures/corpus100/psnr_vs_band_energy.png)

PSNR against the fraction of luma energy in the mark's 0.05 to 0.36 c/px band: Pearson -0.50,
Spearman -0.73 over all 100 images (-0.77 within the full tier). The mark is a multiplicative
modulation of the log-magnitude spectrum, so its residual energy is proportional to the host's own
in-band energy, and PSNR therefore penalises exactly the textured images where the mark hides best.
Flat-region p99.9 correlates *positively* with in-band energy (Spearman +0.53) and *negatively*
with flat area (-0.30), which points at the mask-skirt mechanism: the worst flat-region excursions
sit next to texture, not in the middle of large flat areas.

### The five worst images, inspected

Lowest PSNR at strength 1.0, and highest flat-region p99.9, overlap in one image. All five were
re-embedded at strength 1.0 and cropped at 4x nearest-neighbour zoom, original beside marked, for
the highest-residual window and the highest-residual window inside the flattest 10 %.

| image | size | PSNR | in-band | flat frac | flat p99.9 | verdict at 4x |
|---|---|---|---|---|---|---|
| `sd3.5_large_canny_controlnet_example-2` (canny edge map) | 1024 | 29.6 | 0.523 | 0.335 | 13 | **visible**: grey speckle over the black field, grey smudges between lines |
| `area_composition_square_area_for_subject-1` (black and white graphic) | 1024 | 30.1 | 0.175 | 0.480 | 11.8 | **visible**: wavy streaking in the flat dark background, mottling across the stripes |
| `sdxl_revision_text_prompts-1` (pencil-sketch cityscape) | 1024 | 31.5 | 0.363 | 0.153 | 9 | invisible on texture; faint grain in the flat sky |
| `flux_canny_model_example-2` (canny edge map) | 1024 | 37.9 | 0.575 | 0.910 | 12 | **visible** near lines; pure black far from lines only reaches 9 LSB and is not visible |
| `api_bfl_flux_1_kontext_pro_image-1` | 400 | 35.9 | 0.154 | 0.205 | 13 | invisible: worst window indistinguishable, flat floor shows only faint grain |

Figures:
[`figures/corpus100/zoom_sd3.5_large_canny_controlnet_example-2.png`](figures/corpus100/zoom_sd3.5_large_canny_controlnet_example-2.png),
[`figures/corpus100/zoom_area_composition_square_area_for_subject-1.png`](figures/corpus100/zoom_area_composition_square_area_for_subject-1.png),
[`figures/corpus100/zoom_sdxl_revision_text_prompts-1.png`](figures/corpus100/zoom_sdxl_revision_text_prompts-1.png),
[`figures/corpus100/zoom_flux_canny_model_example-2.png`](figures/corpus100/zoom_flux_canny_model_example-2.png),
[`figures/corpus100/zoom_api_bfl_flux_1_kontext_pro_image-1.png`](figures/corpus100/zoom_api_bfl_flux_1_kontext_pro_image-1.png).

The pattern is consistent: **low PSNR does not predict visibility; synthetic near-binary content
does.** Two of the three visible cases are control-input maps rather than renders, but the third
is a genuine template output, a high-contrast greyscale composition. All three would have their
strength *raised* to 1.5 by the current adaptive policy, because their in-band energy is high.

---

## 4. Robustness

Payload recovery per transform (exact 32-bit match), 100 images per cell. Full table:
[`figures/corpus100/payload_rate_by_transform.png`](figures/corpus100/payload_rate_by_transform.png),
presence scores: [`figures/corpus100/z_by_transform_s1.png`](figures/corpus100/z_by_transform_s1.png).

| transform | s1.0 key0 | s1.0 key1 | s1.0 key2 | s1.5 | adaptive | z median s1.0 | z p10 s1.0 |
|---|---|---|---|---|---|---|---|
| identity | 98% | 96% | 95% | 100% | 100% | 19.7 | 12.3 |
| jpeg90 | 90% | · | · | 100% | 97% | 18.1 | 9.5 |
| jpeg75 | 82% | 80% | 78% | 98% | 93% | 14.3 | 6.5 |
| jpeg60 | 69% | 64% | 62% | 95% | 85% | 11.7 | 4.8 |
| jpeg40 | 55% | · | · | 84% | 80% | 9.6 | 3.1 |
| webp80 | 59% | 58% | 48% | 87% | 80% | 10.4 | 2.6 |
| webp60 | 32% | · | · | 71% | 67% | 7.2 | 1.0 |
| double_jpeg85_70 | 83% | · | · | 96% | 93% | 15.9 | 6.4 |
| resize0.5 | 84% | 77% | 78% | 98% | 95% | 12.0 | 6.3 |
| resize0.75 | 96% | · | · | 100% | 99% | 18.8 | 9.9 |
| resize1.5 | 95% | · | · | 100% | 98% | 14.8 | 8.2 |
| resize0.35 | 0% | · | · | 0% | 0% | -0.9 | -1.6 |
| rot5_expand | 89% | · | · | 99% | 97% | 13.7 | 6.4 |
| rot15_expand | 87% | 88% | 83% | 99% | 96% | 13.0 | 5.9 |
| rot45_expand | 91% | 85% | 86% | 100% | 98% | 11.3 | 6.4 |
| rot30_crop | 87% | · | · | 98% | 97% | 12.0 | 5.3 |
| rot90 | 98% | · | · | 100% | 100% | 19.7 | 12.3 |
| flipH | 98% | 95% | 95% | 100% | 100% | 19.7 | 12.3 |
| crop50%area | 80% | 72% | 71% | 95% | 96% | 14.7 | 7.4 |
| crop25%area | 51% | 49% | 50% | 74% | 83% | 10.9 | 4.3 |
| crop_corner60% | 54% | · | · | 84% | 92% | 11.1 | 3.7 |
| hue+60 | 97% | 95% | 94% | 99% | 100% | 19.6 | 12.0 |
| grayscale | 98% | · | · | 100% | 100% | 19.7 | 12.3 |
| bright1.3 | 95% | · | · | 99% | 97% | 18.6 | 9.8 |
| contrast0.7 | 98% | · | · | 100% | 100% | 19.9 | 12.0 |
| gamma0.6 | 99% | · | · | 100% | 100% | 22.5 | 15.2 |
| sat2.0 | 95% | · | · | 100% | 100% | 19.3 | 11.3 |
| noise5 | 95% | 91% | 93% | 100% | 99% | 17.5 | 9.3 |
| noise10 | 87% | · | · | 97% | 93% | 15.2 | 8.1 |
| blur1 | 100% | 100% | 100% | 100% | 100% | 16.4 | 11.2 |
| median3 | 74% | · | · | 94% | 89% | 10.3 | 6.3 |
| sharpen | 97% | · | · | 100% | 100% | 19.4 | 10.9 |
| unsharp | 91% | · | · | 99% | 96% | 18.2 | 10.6 |
| pad_border48 | 91% | · | · | 100% | 98% | 17.9 | 8.6 |
| text_overlay | 68% | · | · | 89% | 83% | 10.4 | 2.0 |
| social(1080+jpeg80) | 51% | 48% | 47% | 58% | 53% | 9.4 | -1.0 |
| screenshot(0.9+crop+jpeg85) | 65% | · | · | 93% | 86% | 11.5 | 4.2 |
| combo(rot15+resize0.8+jpeg75) | 50% | 48% | 44% | 85% | 79% | 6.8 | 1.9 |
| aspect(1.2x,1.0y) | 83% | · | · | 97% | 95% | 13.3 | 6.5 |

Aggregates over the 38 transforms that are inside the detector's search range:

| condition | detect rate | payload rate | full tier payload | thumb tier payload |
|---|---|---|---|---|
| s1.0 | 91.7 % | 81.9 % | 83.9 % | 77.3 % |
| s1.5 | 97.4 % | 94.4 % | 95.4 % | 92.2 % |
| adaptive | 96.5 % | 92.5 % | 91.0 % | 95.9 % |

Geometry recovery is accurate: median estimated scale 0.499 / 0.749 / 1.500 for the three resize
factors, median estimated rotation 14 deg for 15 deg and 46 deg for 45 deg (2 deg search grid),
and the mirror flag is correct on 100/100 horizontally flipped images.

### Key-to-key agreement

Over the 15-transform core subset, 1046 of 1500 image-transform cells recovered the payload under
all three keys, 247 under none and 207 were mixed, so **86.2 % of cells are unanimous**. Per-key
payload rates are 79.5 %, 76.4 % and 74.9 %. The 5 point spread between keys is real: a single
key's result on one image reflects the interaction between that key's ring schedule and that
image's spectrum, and is not a deterministic property of the image.

### Tier breakdown, and what actually fails

| group | n | PSNR med | identity | jpeg75 | jpeg60 | resize0.5 | rot15 | crop25% | social | combo |
|---|---|---|---|---|---|---|---|---|---|---|
| tier=full | 70 | 39.4 | 97% | 80% | 69% | 86% | 87% | 73% | 73% | 54% |
| tier=thumb | 30 | 37.0 | 100% | 87% | 70% | 80% | 87% | **0%** | **0%** | 40% |

Four distinct failure mechanisms, in order of importance:

**1. The scale ceiling is 2.0, not 2.5.** The two thumb-tier zeros are the same bug. A 400 px
image cropped to 25 % area is 200 px, and a 400 px image resized to 1080 px is a 2.7x upscale.
Bracketing the upscale factor on four images shows a hard cliff: z is healthy at 1.80, 1.95 and
2.00 and collapses to noise at 2.05, 2.10 and 2.30, with the estimated scale becoming random.
This is not JPEG: a pure Lanczos upscale with no compression fails identically, on both tiers.
The cause is in `_features()`. The fine radial grid has step `ring_width / _OVERSAMPLE`, which is
**fixed in cycles per pixel and independent of the candidate scale**, while a ring at candidate
scale `s` spans `ring_width / s`, that is `_OVERSAMPLE / s` grid steps. The guard
`ring_ok = sn >= 0.5 * _OVERSAMPLE` therefore rejects every ring once `s > 2.0`. The interval
`(2.0, 2.5]` of the advertised default range is dead code.

**2. Downscale below 0.4 is outside the search range, and partly outside Nyquist.** At 0.35x the
mark band 0.05 to 0.36 c/px maps to 0.14 to 1.03 c/px, so everything above 0.5 c/px has been
low-passed away and only the inner third of the band survives. The scale-range experiment
(12 full-tier images) shows what widening buys:

| transform | range | detections | payload | mean detect time |
|---|---|---|---|---|
| resize0.35 | (0.4, 2.5) default | 0/12 | 0/12 | 1.48 s |
| resize0.35 | (0.3, 3.0) | 9/12 | 4/12 | 1.85 s (+25 %) |
| social 400->1080 | (0.4, 2.5) default | 0/8 | 0/8 | 1.56 s |
| social 400->1080 | (0.3, 3.0) | 0/8 | 0/8 | 1.94 s (+24 %) |
| crop25% on 400 px | (0.4, 2.5) | 4/8 at z>=5 | 0/8 | 1.43 s |

**Recommendation on the default: change the lower bound to 0.3, leave the upper bound alone until
the ring guard is fixed.** Lowering the floor converts a total blackout into three quarters
detection and a third payload recovery on 0.35x downscales, for a 25 % time cost on an operation
that already takes about 1.5 s. Raising the upper bound is currently pointless, since everything
above 2.0 is rejected by the ring guard before the score is computed; raising it only buys search
cost. Once the guard is fixed, (0.3, 3.0) becomes worth shipping as the default.

**3. Lossy codecs and heavy recompression.** WebP is consistently worse than JPEG at nominally
comparable quality (59 % at q80 against 82 % for JPEG q75, 32 % at q60). JPEG 60 and below, and
any combination of rotation with resize and recompression, fall below 70 % at strength 1.0 and
recover to 85 to 95 % at strength 1.5.

**4. Small crops.** Retaining 25 % of the area halves the payload rate at strength 1.0. Presence
holds up much better than payload (96 % against 73 % on the full tier), the expected behaviour
when the score is still above threshold but chips have been lost.

Only two images failed to recover their payload on a clean 8-bit round trip at strength 1.0. Both
had healthy presence scores (z 6.3 and 9.7) and failed on CRC with bit confidence 2.44 and 2.59
against a corpus median of 5.53 for successful decodes, and both are recovered at strength 1.5 and
by the adaptive policy. The failure mode is bit confidence, not presence. Within the full tier,
resolution costs what it cost before: the 17 images below 640 px recover 71.4 % of payloads
against 89.2 % for the 51 images at 768 px or more.

### Zero-bit and 64-bit modes

| mode | transform | n | rate | z median | z min |
|---|---|---|---|---|---|
| zero-bit (detect) | identity | 100 | 100% | 32.4 | 10.9 |
| zero-bit (detect) | jpeg60 | 100 | 96% | 20.3 | 1.1 |
| zero-bit (detect) | jpeg40 | 100 | 93% | 16.4 | 0.1 |
| zero-bit (detect) | resize0.5 | 100 | 100% | 24.2 | 5.8 |
| zero-bit (detect) | resize0.35 | 100 | 0% | 0.2 | -1.7 |
| zero-bit (detect) | rot15_expand | 100 | 100% | 25.2 | 7.6 |
| zero-bit (detect) | crop25%area | 100 | 99% | 19.2 | 4.4 |
| zero-bit (detect) | noise10 | 100 | 98% | 25.9 | 3.5 |
| zero-bit (detect) | combo(rot15+resize0.8+jpeg75) | 100 | 88% | 13.8 | -0.8 |
| 64-bit (payload) | identity | 100 | 76% | 19.4 | · |
| 64-bit (payload) | jpeg75 | 100 | 39% | 14.0 | · |
| 64-bit (payload) | jpeg60 | 100 | 30% | 11.5 | · |
| 64-bit (payload) | resize0.5 | 100 | 31% | 12.5 | · |
| 64-bit (payload) | rot15_expand | 100 | 56% | 12.2 | · |
| 64-bit (payload) | crop50%area | 100 | 41% | 14.0 | · |
| 64-bit (payload) | social(1080+jpeg80) | 100 | 29% | 8.4 | · |
| 64-bit (payload) | combo(rot15+resize0.8+jpeg75) | 100 | 19% | 7.1 | · |

Zero-bit mode costs the same fidelity (PSNR median 38.96 dB against 38.99 for 32-bit) and roughly
doubles the presence score, because all chips carry the sync pattern rather than payload bits. It
is the only mode that is genuinely robust at the default strength. 64-bit is the opposite: 76 % on
a clean round trip, and on the 400 px tier it collapses to 0 % on 0.5x resize, 50 % crops and the
social pipeline. **64-bit payloads are a large-image, light-processing option only.**

---

## 5. False positives

[`figures/corpus100/z_separation.png`](figures/corpus100/z_separation.png)

| negative set | n | mean | sd | max z | at z >= 5 | CRC-8 passes |
|---|---|---|---|---|---|---|
| unmarked images, correct keys (identity, JPEG 75, 0.5x resize, 3 keys) | 900 | -0.121 | 0.989 | **3.86** | **0** | 7 |
| marked images, two never-used keys (identity, JPEG 75) | 400 | -0.032 | 0.807 | **2.45** | **0** | 1 |
| zero-bit mode, unmarked | 100 | · | · | **3.46** | **0** | · |

Both null distributions are centred just below zero with close to unit spread, which is what the
96-null-key empirical calibration is supposed to produce, and the largest excursion in 1300
negative detections leaves 1.14 of headroom to the threshold.

**Tail estimate.** The z score is already a maximum over the scale, rotation and mirror grid
relative to 96 null keys, so its null distribution is an extreme-value statistic and a Gaussian
assumption is optimistic. Four estimates of the per-query false-alarm probability at z >= 5, from
the 1300 pooled negatives:

| model | P(z >= 5) | 1 in |
|---|---|---|
| Gaussian, fitted mean and sd | 2.8e-8 | 36 million |
| generalised Pareto, exceedances over 1.5 (n = 72, shape -0.02) | 1.8e-5 | 55 000 |
| generalised Pareto, exceedances over 1.0 (n = 171, shape -0.11) | 1.0e-6 | 980 000 |
| Gumbel fitted to the whole sample | 1.3e-3 | 760 |

The whole-sample Gumbel fit is badly conservative: it predicts 5.1e-3 at z >= 3.86 where the
empirical rate is 7.7e-4. Both peaks-over-threshold fits have a slightly negative shape parameter,
meaning a bounded tail, and they bracket the honest answer at roughly **1e-6 to 2e-5 per detection
query**. That supports a per-image check but not a scan of hundreds of millions of images, and it
rests on 1300 samples, so it must be re-measured on a much larger negative set before anyone
relies on it for a compliance threshold.

**CRC-8 chance passes do not create false alarms.** Among the 1300 negatives, 8 passed CRC-8, a
rate of 0.62 % with a 95 % interval of 0.27 % to 1.21 %, entirely consistent with the 1/256 =
0.39 % expected by chance from a random 8-bit check. None of those 8 was reported, because
`expected_match` requires z >= 5 first and none of them reached it. The joint probability of a
false attribution is therefore the product of the two, of order 1e-8 per query even on the
pessimistic tail estimate.

A subtler point worth recording: among the 1226 **positive** detections that fell below the z
threshold, 126 passed CRC-8, a rate of 10.3 %, far above chance. That is expected, since a
partially recovered payload is not a random bit string, and it is the reason the z gate matters:
**CRC alone would be an unsafe acceptance criterion for this scheme.** With the gate in place, all
14 700 positive detections produced zero CRC-passing wrong payloads at z >= 5. Every payload
shortfall in section 4 is a silent failure, never a false attribution.

---

## 6. What changed since the 19-image report

[`image-quality-on-generated-images.md`](image-quality-on-generated-images.md) measured 19 images
at five strengths and 10 transforms. This evaluation is 100 images, 39 transforms, 3 keys and
three payload widths.

**Held up:**

* Fidelity at strength 1.0: PSNR median 39.0 here against 39.8 there, SSIM-Y 0.962 against 0.971,
  MS-SSIM 0.992 against 0.990. On a corpus five times larger the headline numbers moved by less
  than half a dB.
* PSNR is driven by host in-band energy and therefore mis-ranks perceptibility. The rank
  correlation weakened from -0.93 to -0.73 (-0.77 within the full tier), as expected when a small
  corpus is replaced by a broader one, but the sign and the mechanism are unchanged.
* The resolution penalty: 71 % payload recovery below 640 px against 89 % above 768 px.
* Bit confidence, not presence, fails first. Both clean-round-trip failures had z above 6 and bit
  confidence below 2.6.
* No false positives and no false attributions. The earlier report had 38 negatives peaking at
  z = 1.09; with 1300 negatives the peak is 3.86.
* Detection is much more robust than payload recovery.

**Changed or new:**

* **The scale ceiling at 2.0** was not visible in a 10-transform matrix that contained no upscale
  beyond 1.5x and no small-image social pipeline. It is the single most actionable defect found
  here.
* **Visibility is about synthetic line art, not about low PSNR.** The earlier report flagged a
  painterly sky as the one visible case. Here the three visible cases are all near-binary,
  high-contrast graphics, and the lowest-PSNR photographic image in the corpus is invisible at 4x.
* **The adaptive policy now exists in the library** (`recommended_strength()`) and it works:
  payload recovery rises from 81.9 % to 92.5 %. But it implements only two of the three rules that
  were recommended. The earlier report asked for flat-heavy images to be marked *more gently*; the
  shipped policy keys on in-band energy and min side only, and `flat_fraction` is computed by
  `image_statistics()` and then discarded. Every one of the three visibly-marked images in this
  corpus gets its strength raised by it.
* **Flat-region numbers are not comparable** between the two reports because the estimator changed
  (flattest 5 % of 32x32 blocks here, 7x7 local std below 2/255 there). Do not read the drop from
  a median flat max of 20 to 8 as an improvement in the scheme.
* **WebP is now measured and is the weakest common codec**, worse than JPEG at similar quality
  settings.

---

## 7. Recommendations

### For the maintainers, in priority order

1. **Fix the ring-validity guard so the scale search reaches its advertised range.** In
   `_features()`, `ring_ok = sn >= 0.5 * _OVERSAMPLE` combined with a scale-independent radial
   step makes every candidate scale above 2.0 unreachable. Either make the guard scale-aware
   (compare against `0.5 * _OVERSAMPLE / s`) or resample the fine radial grid per candidate scale.
   This is what costs the whole 400 px tier its social-resize result, and it will cost real users
   every time a thumbnail is upscaled for display.
2. **Change the default `scale_range` lower bound to 0.3.** Measured: 0/12 to 9/12 detections on
   0.35x downscales, 25 % more detection time. Leave the upper bound at 2.5 until item 1 lands,
   then move to (0.3, 3.0) and re-measure.
3. **Make `recommended_strength()` use `flat_fraction`.** Suppress the in-band-energy boost when
   the flat fraction is above roughly 0.3, and consider stepping down to 0.75 when the flat
   fraction is above 0.5 and in-band energy is below 0.08. That would have spared all three
   visibly-marked images here at negligible robustness cost, since those images have high presence
   scores anyway.
4. **Attack the mask skirt rather than the global strength.** The visible artefacts are grey
   speckle in black fields *adjacent to* lines, which is the 24 px Gaussian bleeding high gain out
   of textured regions. Eroding the local-std map before the blur is still the cheapest fix, and
   the evidence for it is stronger now than it was at 19 images.
5. **Document the modes in the README.** Zero-bit is robust at strength 1.0; 32-bit needs 1.5 for
   dependable attribution; 64-bit is a clean-channel option only. Document the effective scale
   range once item 1 lands.
6. **Re-run this harness on a prompt-diverse GPU-rendered corpus** using `tools/corpus/prompts.json`
   and `tools/corpus/generate_corpus.py`, checking the flat-graphic and text/signage categories in
   particular, which are under-represented here and are where the visible failures live.
7. **Enlarge the negative set before quoting a false-positive rate.** 1300 negatives support "no
   false alarms observed" and a tail of order 1e-6 to 2e-5; a compliance claim needs 10^5 or more.

### For operators, by use case

| use case | recommended setting | why |
|---|---|---|
| "is this ours?" presence check, images 768 px and larger | zero-bit mode at strength 1.0 | 100 % detection on a clean round trip, 88 to 100 % under every transform inside the search range, and the best fidelity of any mode |
| attribution, 32-bit payload, large images, light processing | strength 1.0 | 98 % clean, 82 to 98 % under common single transforms |
| attribution where the image will be recompressed, cropped or reposted | strength 1.5, or the adaptive policy with the flat-fraction guard from item 3 | 94.4 % payload against 81.9 % at strength 1.0 |
| any image below 768 px | strength 1.5, below 640 px strength 2.0 | 71 % against 89 % payload recovery at strength 1.0; this is what the adaptive policy already does |
| flat-graphic, line art, logos, UI screenshots, text-heavy images | strength 1.0 at most, and inspect before shipping; do not let the adaptive policy raise it | the only visible artefacts in this corpus are on this content class |
| 64-bit payloads | only for images at 1024 px or larger that will not be resized or recompressed | 76 % clean recovery, 0 % on several transforms at 400 px |

Two operational notes. A failed payload check is never a wrong attribution here, since the CRC
gate behind the z gate held on all 14 700 positive detections, so a system can safely treat
"detected but no payload" as "ours, source unknown". And presence and attribution should be
configured separately: the gap between 91.7 % detection and 81.9 % payload recovery at strength
1.0 is the whole design space, and one setting for both wastes either fidelity or reliability.
