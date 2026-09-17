# AI-content transparency for ComfyUI: design overview

This folder documents the research and design behind two custom node packs:

| Pack | Layer | What it provides |
|---|---|---|
| [`custom_nodes/comfyui_durable_watermark`](../../custom_nodes/comfyui_durable_watermark) | **Latent disclosure** (imperceptible, keyed watermark) | A training-free, pure-numpy spectral watermark that survives rotation, flips, translation/crops, uniform rescaling, colour edits, moderate JPEG, noise and blur, carries up to 64 payload bits, and whose private key is set by the user or the inference provider. |
| [`custom_nodes/comfyui_content_credentials`](../../custom_nodes/comfyui_content_credentials) | **Provenance metadata** (signed C2PA manifest) | Standards-based Content Credentials declaring the output AI-generated, with the fields California SB 942 and the EU AI Act Code of Practice expect, a soft binding to the watermark, do-not-train flags and an optional encrypted private assertion. |

The research reports in this folder:

1. [Legal requirements: EU AI Act Art. 50, California SB 942 / AB 853 / SB 1000, China, Korea, India, Spain, US federal, C2PA & IPTC vocabulary](01-legal-requirements-eu-california-global.md)
2. [Image watermarking state of the art, SynthID-Image and the attacks on it, technique survey with licences](02-image-watermarking-state-of-the-art.md)
3. [C2PA tooling: c2pa-python API, manifest layout for generative media, soft bindings, certificates, verification](03-c2pa-content-credentials-tooling.md)

Research date: 13 September 2026. The reports were compiled with web search from a
sandbox that blocked many primary sources; claims are cited and the caveats are
stated inline. None of this is legal advice. Both node packs are released under the Apache License 2.0
with a NOTICE that disclaims warranty, liability and any promise of regulatory compliance.

## Why two layers

Both regimes that bind image generators in 2026 want the same thing:

* **EU AI Act, Art. 50(2)** (applies since 2 Aug 2026): providers must ensure outputs are
  "marked in a machine-readable format and detectable as artificially generated", with
  solutions that are "effective, interoperable, robust and reliable". The Commission's
  Code of Practice (final, June 2026) operationalises this as **at least two machine-readable
  layers: digitally signed metadata and an imperceptible watermark**, plus a detection
  facility. Fines: up to EUR 15 M or 3 % of turnover.
* **California AI Transparency Act** (SB 942 as amended by AB 853, operative 2 Aug 2026;
  SB 1000 pending would drop the 1 M-user threshold): covered providers must embed a
  **latent disclosure** conveying the provider name, system name and version, time and
  date, and a unique identifier, that is "consistent with widely accepted industry
  standards" and "permanent or extraordinarily difficult to remove", detectable by the
  provider's own free detection tool. $5,000 per violation per day.

Signed metadata (C2PA) satisfies "industry standard" and carries the four fields, but it
is stripped by any re-encode. A robust watermark survives re-encoding but cannot carry
a full manifest. Linking them (the C2PA *soft binding*) gives durability: the watermark
payload identifies the manifest in the provider's registry after the metadata is gone.

## Watermark design ("RingMark", `org.comfyui.ringmark.v1`)

**Requirements** (from the task and the research): imperceptible; keyed by a private value
set by the user or provider; multi-bit; frequency-domain like SynthID but training-free
and auditable; invariant to rotation, translation and colour transforms; robust to
scaling, cropping, JPEG, noise and blur; honest false-positive control.

**Construction** (see `durable_watermark/core.py`):

1. Work on **luminance** only and add the same delta to R, G, B: hue/saturation edits do not
   touch the mark; brightness/contrast/gamma changes are removed by detrending and
   normalisation.
2. Take the 2-D DFT. Its **magnitude is translation-invariant**; cropping does not change
   spatial frequency in cycles/pixel, so the band stays aligned after a crop.
3. Split the mid band (0.05 to 0.36 cycles/pixel) into **77 concentric rings** of width
   0.004 cycles/pixel. Each ring carries:
   * a **radial chip**: the ring's mean log-power is nudged up or down (+/-10 %) by a keyed
     sign. The angle-integrated radial profile is exactly invariant to rotation and flips.
   * six **angular harmonic chips**: the ring's log-power is modulated by
     `s * cos(h*theta + phi)` for even harmonics `h in {2, 6, 10, 14, 18, 22}` (even for Hermitian
     symmetry, not multiples of 4 to avoid axis-aligned image/JPEG structure) with a keyed
     phase `phi` and an antipodal sign `s`. A rotation by `d` shifts each harmonic's phase by
     `h*d`; a mirror conjugates it. Detection reads the chips **coherently** after a cheap
     1-D search over `d` (2 degree steps, mod 180) and a flip hypothesis, so natural image
     anisotropy is zero-mean noise rather than bias.
4. 462 angular chips per image: 25 % are payload-independent **sync** chips (presence
   detection and geometry estimation), 75 % carry the payload through **keyed random block
   codes** (8 info bits per block, soft maximum-likelihood decoding) plus an 8-bit CRC.
   Without the secret the chip positions, signs, phases and codebooks are unknown.
5. The multiplicative modulation is applied to the image's own spectrum (invisible in
   texture); a keyed, band-limited **additive floor** (~1/255 spatial std) keeps flat regions
   detectable after 8-bit quantisation. A very smooth texture-adaptive mask shapes the
   residual. Default strength gives 40 to 47 dB PSNR.
6. **Scale search**: a uniform rescale by `s` moves every ring to `r/s`. All features are
   computed on a fine radial grid once and evaluated for ~700 scale hypotheses (0.4x to 2.5x)
   by cumulative sums; an optional anisotropic (aspect) search is available.
7. **Calibrated statistics**: the detection score is compared against an empirical null of
   96 *wrong* keys run through the *same* search on the *same* image. The reported z-score
   therefore accounts for image-specific spectral structure and for the number of geometric
   hypotheses (the false-positive inflation the classical literature warns about). Default
   threshold z >= 5.

**Measured robustness** (768 px photo-like image, 640 px flat graphic, 640 px 1/f texture;
32-bit payload; ✅ payload decoded and CRC verified, 🟡 presence detected only, ❌ missed;
number = calibrated z):

| Transform | photo s=1.0 | flat s=1.0 | texture s=1.0 | photo s=1.5 | flat s=1.5 | texture s=1.5 |
|---|---|---|---|---|---|---|
| identity / 8-bit PNG | ✅ 15 | ✅ 18 | ✅ 36 | ✅ 20 | ✅ 21 | ✅ 42 |
| JPEG q90 | 🟡 11 | ✅ 12 | ✅ 34 | ✅ 16 | ✅ 25 | ✅ 40 |
| JPEG q75 | 🟡 7 | ❌ 3 | ✅ 22 | ✅ 12 | ✅ 13 | ✅ 29 |
| JPEG q50 | ❌ 4 | ❌ 2 | ✅ 19 | 🟡 10 | ❌ 1 | ✅ 24 |
| resize 0.5x | ✅ 10 | ✅ 11 | ✅ 22 | ✅ 14 | ✅ 22 | ✅ 27 |
| resize 0.75x | ✅ 16 | ✅ 18 | ✅ 31 | ✅ 22 | ✅ 21 | ✅ 37 |
| resize 1.5x | ✅ 10 | ✅ 17 | ✅ 20 | ✅ 15 | ✅ 20 | ✅ 23 |
| rotate 90 | ✅ 15 | ✅ 18 | ✅ 36 | ✅ 20 | ✅ 21 | ✅ 42 |
| rotate 7 (expand) | ✅ 6 | ✅ 7 | ✅ 17 | ✅ 11 | ✅ 11 | ✅ 23 |
| rotate 30 (crop) | ✅ 11 | ✅ 15 | ✅ 21 | ✅ 19 | ✅ 23 | ✅ 26 |
| rotate 30 (expand) | ✅ 8 | ✅ 16 | ✅ 24 | ✅ 15 | ✅ 18 | ✅ 29 |
| horizontal flip | ✅ 15 | ✅ 18 | ✅ 36 | ✅ 20 | ✅ 21 | ✅ 43 |
| centre crop 50 % area | ✅ 12 | ✅ 12 | ✅ 30 | ✅ 17 | ✅ 15 | ✅ 37 |
| centre crop 25 % area | 🟡 10 | ✅ 10 | ✅ 15 | ✅ 15 | ✅ 12 | ✅ 21 |
| hue +60 | 🟡 12 | ✅ 11 | ✅ 32 | ✅ 17 | ✅ 15 | ✅ 37 |
| grayscale | ✅ 15 | ✅ 17 | ✅ 36 | ✅ 20 | ✅ 21 | ✅ 42 |
| brightness 1.3 | ✅ 10 | ✅ 17 | ✅ 35 | ✅ 16 | ✅ 21 | ✅ 42 |
| contrast 0.7 | ✅ 15 | ✅ 18 | ✅ 35 | ✅ 20 | ✅ 21 | ✅ 42 |
| gamma 0.6 | ✅ 13 | ✅ 18 | ✅ 37 | ✅ 18 | ✅ 21 | ✅ 42 |
| saturation 2.0 | 🟡 11 | ✅ 15 | ✅ 35 | ✅ 17 | ✅ 18 | ✅ 41 |
| Gaussian noise sigma 5/255 | ✅ 12 | 🟡 9 | ✅ 35 | ✅ 18 | ✅ 24 | ✅ 42 |
| Gaussian blur r=1 | ✅ 19 | ✅ 16 | ✅ 21 | ✅ 22 | ✅ 22 | ✅ 26 |
| sharpen | ✅ 17 | ✅ 17 | ✅ 26 | ✅ 24 | ✅ 21 | ✅ 33 |
| rotate 15 + resize (net 0.61x) + JPEG q75 | ❌ -0 | ❌ -0 | ✅ 10 | ❌ 4 | ❌ -1 | ✅ 14 |
| anisotropic resize 1.2x horizontal (aspect search on) | 🟡 8 | ✅ 11 | ✅ 19 | ✅ 13 | ✅ 15 | ✅ 25 |

PSNR at s=1.0: photo 43.2 dB, flat 47.3 dB, texture 40.4 dB; at s=1.5: 39.6 / 43.7 / 36.6 dB.
Unmarked images and wrong keys score |z| < 3 in all runs. Detection takes ~1.5 to 2.5 s per
768 px image on one CPU core (embedding ~0.8 s).

**Known limitations** (shared with every post-hoc watermark, see report 2):

* Flat synthetic graphics + JPEG <= 75: the additive floor is quantised away. Use strength 1.5
  or accept presence-only detection.
* Heavy combined edits that net a < 0.65x downscale plus strong JPEG push most rings beyond
  Nyquist / the JPEG cutoff.
* Diffusion regeneration, adversarial spectral optimisation (UnMarker), latent decorrelation
  (MarkNull) and averaging attacks defeat SynthID, TrustMark and this scheme alike; the coding
  limit of Francati et al. rules out any binary watermark surviving >50 % symbol changes.
  Mitigations: rotate keys, derive per-image payloads, keep the C2PA manifest registry.
* Images smaller than ~256 px on a side do not have enough spectral resolution for the
  default ring width; raise `ring_width` for thumbnails.

## Independent reviews (17 September 2026) and what changed

Three Opus reviewers assessed the packs after the first release. Their reports are in
[`reviews/`](reviews/):

* [Image quality on ComfyUI renders](reviews/image-quality-on-generated-images.md): 19 template
  renders, five strengths, ten edits, 380 detections, 29 figures.
* [EU AI Act Art. 50 gap review](reviews/eu-ai-act-review.md): three requirement tables, 12 gaps,
  prioritised recommendations, operator checklist.
* [California AI Transparency Act gap review](reviews/california-ai-transparency-act-review.md):
  requirement tables, 14 gaps, a design for the missing §22757.2 tool, operator checklist.
* [100-render corpus evaluation](reviews/corpus-100-evaluation.md): 100 ComfyUI template
  renders, three keys, strengths 1.0 / 1.5 / adaptive, 39 edits, zero-bit and 64-bit modes,
  1,300 negative detections; 14,700 detections in all, run with `tools/eval_corpus.py`. Written
  after the fixes below, so it measures the revised core. The sandbox could not render new
  images (no GPU, model hosts unreachable); `tools/corpus/prompts.json` and
  `tools/corpus/generate_corpus.py` let a GPU machine render a 100-prompt corpus and rerun the
  same harness.

Findings acted on in the code:

| Finding | Change |
|---|---|
| A literal secret typed into a widget leaked through the front-end workflow JSON in PNG text and manifests (only the API prompt was redacted) | Redaction now covers `EXTRA_PNGINFO`/workflow `widgets_values` and the C2PA passphrase and PEM widgets; local fallback when the watermark pack is absent |
| The signed manifest store was discarded and `manifest_json` was the pre-signing definition | Save node returns the manifest as read back, `registry_records` for a resolver, and can write a `.c2pa` sidecar |
| `c2pa.watermarked` is deprecated since c2pa-rs 0.91 | `c2pa.watermarked.bound` |
| Manifest embedded signed self-assertions of legal compliance that the NOTICE disclaims | Removed; the manifest states facts (`ai_generated`, `created_or_altered`) only |
| Enforce mode pinned only secret/payload/strength; other key-schedule inputs could produce undetectable marks; per-image ids impossible in enforce mode | All KDF inputs pinned; payload template with server-owned high bits and workflow-filled low bits |
| Private-assertion `key_id` and the watermark `key_fingerprint` were cheap offline passphrase oracles | scrypt-derived keys with per-box salts; watermark master key via scrypt, fingerprint via HMAC |
| Z-score extrapolated a Gaussian tail from a max-over-search statistic | Gumbel tail probability reported as `p_value` (threshold still on the calibrated z) |
| Mask halo made skies ripple; small images failed to decode | The wide-blur gain is now capped by a narrow-blur view of the same texture map (flat pixels stay at the floor, thin edges keep their gain) and the additive floor is left unmasked; content-adaptive strength (x1.5 texture-rich, x1.5-2 small images) on by default in the node and CLI |
| AB 853 wrongly credited with a created-vs-altered field | Corrected to pending SB 1000 in docs and code |

Regression check of the revised core against the first release (five keys per image, mean z, 8-bit
round trip / JPEG q75 / rotate 30 with expand; payload = decoded and verified out of five keys):

| image | first release | revised core |
|---|---|---|
| flat cartoon (`example.png`, 768 px) | 17.3 / 8.8 / 9.4, payload 5 / 2 / 5, PSNR 43.0 | 15.3 / 7.1 / 8.2, payload 4 / 2 / 5, PSNR 43.2 |
| sky render (`flux_schnell-1`, 1024 px) | 22.1 / 18.6 / 14.2, payload 5 / 5 / 5, PSNR 37.8 | 20.8 / 17.5 / 13.7, payload 5 / 5 / 5, PSNR 37.9 |
| anime flat graphic (`mixing_controlnets-1`) | 25.4 / 20.7 / 17.4, payload 5 / 5 / 5, PSNR 36.8 | 26.0 / 21.7 / 18.5, payload 5 / 5 / 5, PSNR 36.7 |

The revised mask costs one to two z-points on flat-dominated content and gains one on textured
content, with key-to-key spread roughly halved; the sky render's flat-region peak falls from 31 to
23 of 255. Per-key variance (about two z-points) is larger than the change, which is why single-key
tables such as the one above should be read with that margin in mind.

Findings that remain open because they are outside a node pack: a public detection tool
(Cal. §22757.2; EU detection facility), a manifest registry/resolver behind a permanent URL, a visible
label node, server-side pipeline enforcement, registration of the soft-binding algorithm, adversarial and
print-scan tests. The multi-key robustness corpus now exists (100 renders, three keys, 39 edits, see
[the corpus report](reviews/corpus-100-evaluation.md)); adversarial and print-scan tests are still
open. Both READMEs say so up front.

## Threat model and key handling

* The secret is the only thing standing between an attacker and a forged/removed mark, so it
  is never written to disk by the nodes and is redacted from the PNG `prompt` metadata that
  the C2PA save node writes. Workflows should reference it as `env:NAME` or `file:PATH`.
* Inference providers can pin the secret, payload and strength server-side
  (`COMFYUI_WATERMARK_ENFORCE=1`), so tenants cannot disable or re-key the mark.
* The key fingerprint (SHA-256 derived, 8 bytes) is public and is what the C2PA soft binding
  carries; it identifies *which* key to try, not the key.

## Relationship to SynthID and open-source alternatives

SynthID-Image (Google DeepMind, arXiv 2510.09263) is a closed, jointly trained encoder/decoder
that stamps a 136-bit payload in pixel space with conformal p-values for detection; its weights
are not public, and the 2025-2026 literature shows it can be removed by no-box attacks. Among
permissively licensed alternatives, Adobe TrustMark (MIT, learned, 100 bits, registered as a
C2PA soft-binding algorithm), Meta VideoSeal / Pixel Seal (MIT, learned, 256 bits) and Watermark
Anything (MIT weights) are the strongest learned options but need torch weights and are not
rotation-invariant by construction. Tree-Ring / Gaussian Shading / PRC (MIT) are in-generation
latent watermarks that require the diffusion model and DDIM inversion at detection time.

RingMark is the classical, training-free choice: no weights, milliseconds of numpy, exact
rotation/flip invariance, auditable statistics, and a configurable private key. For maximum
assurance a provider can layer it with TrustMark (pixel-space, 100 bits) by chaining two embed
steps before the C2PA save node; both marks then appear as soft bindings.
