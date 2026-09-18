# License, trademark, patent and export review of the two node packs

Scope: `custom_nodes/comfyui_durable_watermark`, `custom_nodes/comfyui_content_credentials`, the
standalone branches split from them, and `docs/ai-content-compliance/`. Date: 2026-09-18.

**This is an engineering review of the licensing position, not legal advice and not a
freedom-to-operate opinion.** Patent databases, c2pa.org and github.com issue threads were not
reachable from the review environment, so patent status is stated from filing dates and the
20-year term, and two items below are explicitly left for counsel and for the maintainer to
check on the live pages.

## 1. Summary

| area | finding | action taken |
|---|---|---|
| Own licence | Both packs are Apache-2.0 with a NOTICE that disclaims any compliance warranty; every `.py` file carries an SPDX header; `pyproject.toml` declares `license = "Apache-2.0"` and ships LICENSE and NOTICE. | none needed |
| Runtime dependencies | numpy (BSD-3 and others), scipy (BSD-3), Pillow (MIT-CMU), cryptography (Apache-2.0 OR BSD-3), c2pa-python 0.37.10 (MIT OR Apache-2.0). All permissive and Apache-2.0 compatible. Nothing is vendored. | none needed |
| GPL-3.0 host | ComfyUI is GPL-3.0. The maintainers have not ruled on custom-node licensing (issue #3362 has no maintainer reply; the "must be GPL" statement in discussion #14346 is a community member's). Apache-2.0 is one-way compatible with GPL-3.0, so distributing the packs under Apache-2.0 and running them inside ComfyUI is permitted either way; the pure libraries `durable_watermark/` and `content_credentials/` import nothing from ComfyUI. | NOTICE wording tightened (section 3) |
| Trademarks | "C2PA" and "Content Credentials" are marks of the Coalition for Content Provenance and Authenticity, which publishes trademark guidelines (not reachable here). The C2PA pack uses "Content Credentials" in its name and node titles. "SynthID" (Google) and "TrustMark" (Adobe) appear descriptively in the docs. The Content Credentials icon is not used. | trademark notice added to both NOTICE files and the C2PA README; **maintainer to read the guidelines before registry publication, rename option below** |
| Third-party images | The corpus figures and the release page reproduce renders shipped by Comfy-Org's `comfyui-workflow-templates` packages. The GitHub repository licence is MIT (Comfy Org, 2023-present); the PyPI wheel's metadata says MIT while the bundled LICENSE file is GPL-3.0 text, a packaging inconsistency on their side. Both permit reproduction in this GPL-3.0 fork with attribution. | attribution added to the figures directory, the report and the release page |
| Model output licences | Some template renders come from models with output terms (Flux.1 dev, API models). Their licences permit use of outputs; the images are reproduced only as evaluation figures. | noted, no action |
| Patents | Rotation/scale-invariant Fourier-magnitude watermarking is old, heavily published and the foundational patents have expired; Digimarc and others hold later families that could not be checked here. | landscape in section 4; **FTO opinion recommended before commercial deployment** |
| Export controls | The C2PA pack uses AES-256-GCM, scrypt and HMAC-SHA256 through `cryptography`; the watermark pack uses scrypt and HMAC only (authentication, no confidentiality). Both are standard algorithms. Publicly available source implementing standard cryptography needs no BIS notification under 15 CFR 742.15(b) as currently written. | noted in section 5 |
| Prompt set | One prompt named a film studio ("Studio-Ghibli-like"). | reworded |

## 2. Copyright and licence inventory

Files authored in this branch: everything under the two pack directories and
`docs/ai-content-compliance/`. No code was copied from third-party projects; the ring-template
detector, the block codes, the perceptual mask and the C2PA manifest builder were written from the
published literature cited in `02-watermarking-state-of-the-art.md` and the c2pa-python API docs.

Dependency licences as installed (importlib metadata):

| package | version | licence |
|---|---|---|
| numpy | 2.4.6 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| scipy | 1.17.1 | BSD-3-Clause |
| Pillow | 12.3.0 | MIT-CMU |
| cryptography | 50.0.1 | Apache-2.0 OR BSD-3-Clause (bundles OpenSSL, Apache-2.0) |
| c2pa-python | 0.37.10 | MIT OR Apache-2.0 (wraps c2pa-rs, MIT OR Apache-2.0) |

The packs depend on these at run time and do not redistribute them, so no notice files need to be
carried. If a wheel of the packs is ever built with bundled dependencies, the c2pa-rs, OpenSSL and
numpy notices must be added.

The docs directory sits inside a GPL-3.0 repository fork. The documents are original prose and data;
they carry no separate licence header, so they follow the fork's licence. If the docs are ever moved
to the standalone repositories, mark them Apache-2.0 or CC-BY-4.0 explicitly.

## 3. The GPL-3.0 host question

The GNU FAQ treats a plugin that is dynamically loaded and shares data structures with the main
program as part of one combined program. A ComfyUI custom node imports `comfy_api.latest` and
receives torch tensors from the host, which fits that description; a community member in
Comfy-Org discussion #14346 states the "must be GPL" conclusion, but the maintainers have not
adopted it, the registry accepts MIT and Apache packs, and most published packs are permissively
licensed.

The position taken here:

* The packs are licensed Apache-2.0. Apache-2.0 is compatible with GPL-3.0 (FSF and ASF both say
  so), so a user who combines them with ComfyUI receives the combination under GPL-3.0 terms and
  the pack files under Apache-2.0. Nothing in Apache-2.0 restricts that.
* The core libraries (`durable_watermark/core.py`, `keys.py`, `cli.py`; `content_credentials/*`)
  import only numpy, scipy, Pillow, c2pa-python and cryptography and can be used outside ComfyUI
  under Apache-2.0 alone. Only `wm_nodes.py` and `cc_nodes.py` touch the ComfyUI API.
* If the maintainers ever state that node packs must be GPL-3.0, the packs can be relicensed
  GPL-3.0-or-later by the copyright holder without touching dependencies.

## 4. Patent landscape (not a clearance)

What the watermark does, in patent terms: modulates the magnitude of the 2-D DFT of luminance
along concentric rings with a keyed pseudo-random pattern, uses the rotation and scale behaviour of
the Fourier magnitude for geometric synchronisation (rotation search on angular harmonics, scale
search on ring radius), masks the residual with a local-texture measure, and carries a payload in
keyed block codes with a CRC.

Foundational public disclosures and patents, all older than twenty years:

| reference | what it covers | status |
|---|---|---|
| Cox, Kilian, Leighton, Shamoon, "Secure spread spectrum watermarking" (1997); NEC US 5,930,369 | spread-spectrum modulation of transform coefficients | patent expired |
| O'Ruanaidh and Pun, "Rotation, scale and translation invariant spread spectrum digital image watermarking" (1998) | RST invariance via Fourier-Mellin (log-polar) magnitude | academic; no patent |
| Pereira and Pun, "Robust template matching for affine resistant image watermarks" (2000) | peaks in the DFT magnitude as a synchronisation template | academic |
| Solachidis and Pitas, "Circularly symmetric watermark embedding in 2-D DFT domain" (2001) | ring-shaped, circularly symmetric DFT-magnitude watermarks | academic |
| Digimarc US 6,408,082 "Watermark detection using a Fourier-Mellin transform" (filed 1999) | log-polar correlation to recover rotation and scale | expired (20 years from filing) |
| Digimarc US 6,993,153 "Self-orienting watermarks" (priority 2000) | orientation signal in the transform domain | expired |
| NEC US 6,282,300 "RST resilient public watermarking using a log-polar Fourier transform" (filed 2000) | log-polar Fourier magnitude embedding | expired |
| US 7,376,241 "Discrete Fourier transform (DFT) watermark" (early 2000s) | DFT-domain watermark | expired or expiring; check |

Everything the packs do at the algorithmic level is in that expired or academic prior art:
DFT-magnitude modulation, circular symmetry for rotation handling, radial scale search, perceptual
masking, keyed pseudo-random carriers, CRC-protected payloads. That is a strong position on the
core mechanism.

What could not be checked and is the reason to get a freedom-to-operate opinion before a
commercial deployment:

* Digimarc holds hundreds of later patents (2005 to the present) on synchronisation signals,
  "sparse" and "signal-rich art" marks, detector implementations, and detection of multiple encoded
  signals, some with claims narrow enough to read on specific implementation details (for example
  particular rotation-search or scale-search procedures, or combinations with lossy encoding).
  Their status and claims were not reviewable from here.
* Google's SynthID and similar latent-space and learned watermarks are patented, but this pack does
  not touch the diffusion model or latents and does not use a neural encoder or decoder.
* The C2PA specification is published under a royalty-free patent commitment by its members
  through the Joint Development Foundation; implementing it through c2pa-rs is the intended path.
  The private encrypted assertion added here (AES-GCM box with scrypt key derivation) is ordinary
  cryptography, not a C2PA-specified structure.

Nothing in this review identified a live claim that the packs read on, and nothing in it should be
taken to say that none exists.

## 5. Export controls

The C2PA pack encrypts an assertion with AES-256-GCM and derives keys with scrypt and HMAC-SHA256,
all through the `cryptography` package; the watermark pack uses scrypt and HMAC-SHA256 to derive
keys for the watermark and never encrypts content. Under 15 CFR 742.15(b) as currently written,
publicly available encryption source code is not subject to the EAR, and the e-mail notification to
BIS and the ENC coordinator is required only for source implementing "non-standard cryptography".
AES-GCM, scrypt and HMAC are standard, so no notification is expected to be required for publishing
these repositories. A packaged product built on them should be classified on its own.

## 6. Trademarks

* "C2PA" and "Content Credentials" are marks of the Coalition for Content Provenance and
  Authenticity, which publishes trademark guidelines on c2pa.org and contentcredentials.org (not
  reachable from the review environment). The pack name `ComfyUI-ContentCredentials`, its display
  name and its node titles use "Content Credentials" descriptively for the standard it implements,
  it uses no logo or icon, and it claims no C2PA conformance or membership. A trademark notice now
  says so in the NOTICE files and README. **Before publishing the pack to the Comfy Registry or
  naming a product after it, read the guidelines.** If they reserve "Content Credentials" for
  members or conformant products, rename the pack (for example `ComfyUI-ProvenanceManifest` with
  "C2PA manifest" in the description; the c2pa-python and c2pa-rs projects show that "c2pa" in a
  project name is established practice).
* "SynthID" (Google) and "TrustMark" (Adobe) are named in the docs and README only to compare
  approaches; the notice covers them.
* "ComfyUI" is the host project's name and appears in pack names in the same way as every other
  registry pack.

## 7. Third-party images in the docs

`docs/ai-content-compliance/reviews/figures/corpus100/` and the release page reproduce, as
contact-sheet thumbnails and 4x zoom crops, renders that Comfy-Org ships as example outputs in the
`comfyui-workflow-templates` packages (MIT, Copyright (c) 2023-present Comfy Org). The 19-image
review figures reproduce the same source. An attribution README now sits in the figures directory.
The evaluation corpus itself is not committed.

## 8. Recommendations for the maintainer, in order

1. Read the C2PA trademark guidelines and decide whether to keep the "Content Credentials" name
   before publishing to the registry (section 6).
2. Replace "Copyright 2026 the contributors" in NOTICE with the actual holder's name before the
   first release, and add a CONTRIBUTING note on the inbound licence (Apache-2.0 with DCO or CLA).
3. Obtain a freedom-to-operate opinion on the watermark detector before commercial deployment,
   focused on Digimarc's post-2005 families (section 4).
4. If the packs are ever distributed as wheels with bundled dependencies, add the c2pa-rs,
   OpenSSL and numpy notices.
5. If the docs move out of the GPL-3.0 fork, give them an explicit licence.
