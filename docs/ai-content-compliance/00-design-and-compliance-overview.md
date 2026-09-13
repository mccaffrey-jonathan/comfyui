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
| identity / 8-bit PNG | ✅ 19 | ✅ 18 | ✅ 41 | ✅ 25 | ✅ 20 | ✅ 42 |
| JPEG q90 | ✅ 15 | ✅ 14 | ✅ 41 | ✅ 21 | ✅ 22 | ✅ 41 |
| JPEG q75 | ✅ 11 | ❌ 2 | ✅ 26 | ✅ 17 | ✅ 15 | ✅ 31 |
| JPEG q50 | 🟡 7 | ❌ 0 | ✅ 21 | ✅ 12 | ❌ 0 | ✅ 26 |
| resize 0.5x | ✅ 12 | ✅ 14 | ✅ 31 | ✅ 17 | ✅ 22 | ✅ 34 |
| resize 0.75x | ✅ 16 | ✅ 15 | ✅ 37 | ✅ 22 | ✅ 18 | ✅ 40 |
| resize 1.5x | ✅ 11 | ✅ 16 | ✅ 22 | ✅ 15 | ✅ 18 | ✅ 24 |
| rotate 90 | ✅ 19 | ✅ 18 | ✅ 41 | ✅ 25 | ✅ 20 | ✅ 42 |
| rotate 7 (expand) | ✅ 10 | ✅ 10 | ✅ 20 | ✅ 15 | ✅ 16 | ✅ 25 |
| rotate 30 (crop) | ✅ 11 | ✅ 15 | ✅ 23 | ✅ 17 | ✅ 21 | ✅ 30 |
| rotate 30 (expand) | ✅ 10 | ✅ 17 | ✅ 24 | ✅ 15 | ✅ 21 | ✅ 30 |
| horizontal flip | ✅ 19 | ✅ 18 | ✅ 42 | ✅ 25 | ✅ 20 | ✅ 42 |
| centre crop 50 % area | ✅ 16 | ✅ 11 | ✅ 36 | ✅ 21 | ✅ 14 | ✅ 35 |
| centre crop 25 % area | ✅ 13 | ✅ 7 | ✅ 22 | ✅ 18 | ✅ 11 | ✅ 26 |
| hue +60 | ✅ 15 | ✅ 13 | ✅ 37 | ✅ 20 | ✅ 18 | ✅ 39 |
| grayscale | ✅ 18 | ✅ 18 | ✅ 41 | ✅ 24 | ✅ 20 | ✅ 42 |
| brightness 1.3 | ✅ 13 | ✅ 17 | ✅ 42 | ✅ 19 | ✅ 19 | ✅ 43 |
| contrast 0.7 | ✅ 19 | ✅ 18 | ✅ 41 | ✅ 24 | ✅ 20 | ✅ 42 |
| gamma 0.6 | ✅ 16 | ✅ 18 | ✅ 42 | ✅ 22 | ✅ 20 | ✅ 43 |
| saturation 2.0 | ✅ 14 | ✅ 15 | ✅ 41 | ✅ 21 | ✅ 18 | ✅ 41 |
| Gaussian noise sigma 5/255 | ✅ 17 | 🟡 10 | ✅ 41 | ✅ 22 | ✅ 22 | ✅ 43 |
| Gaussian blur r=1 | ✅ 19 | ✅ 18 | ✅ 19 | ✅ 24 | ✅ 22 | ✅ 24 |
| sharpen | ✅ 19 | ✅ 18 | ✅ 30 | ✅ 25 | ✅ 20 | ✅ 36 |
| rotate 15 + resize (net 0.61x) + JPEG q75 | ❌ 0 | ❌ 0 | ✅ 10 | ❌ 4 | ❌ -1 | ✅ 16 |
| anisotropic resize 1.2x horizontal (aspect search on) | ✅ 9 | ✅ 11 | ✅ 21 | ✅ 15 | ✅ 14 | ✅ 26 |

PSNR at s=1.0: photo 42.9 dB, flat 47.1 dB, texture 40.3 dB; at s=1.5: 39.3 / 43.5 / 36.6 dB.
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
