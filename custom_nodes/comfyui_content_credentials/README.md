# ComfyUI Content Credentials (C2PA)

Custom nodes that save ComfyUI images with **signed C2PA Content Credentials**
declaring them AI-generated, carrying the disclosure fields that the
**EU AI Act (Art. 50(2))** and the **California AI Transparency Act
(SB 942 / AB 853, B&P Code §22757.3)** ask for, an optional **do-not-train**
assertion, a **soft binding** to the companion
[`ComfyUI-DurableWatermark`](https://github.com/mccaffrey-jonathan/ComfyUI-DurableWatermark) mark, and an optional
**encrypted private assertion** for details only the provider may read.

Built on the official [`c2pa-python`](https://github.com/contentauth/c2pa-python)
SDK (MIT/Apache-2.0, c2pa-rs core). Manifests follow the layout used by Adobe
Firefly, OpenAI and Google in 2026 (`c2pa.actions.v2` / `c2pa.created` /
`digitalSourceType: trainedAlgorithmicMedia`, object-form `softwareAgent`,
`cawg.training-mining`). See the [research and design notes](https://github.com/mccaffrey-jonathan/comfyui/tree/claude/ai-watermarking-compliance-0c2ubb/docs/ai-content-compliance)
behind these choices.

> C2PA credentials are **signed, not encrypted**: everything in a manifest is
> public and anyone can strip it by re-encoding the file. That is why the EU
> Code of Practice (June 2026) requires *two* machine-readable layers - signed
> metadata **and** an imperceptible watermark - and why this pack links to the
> durable watermark. Only the optional `org.comfyui.private` assertion is
> encrypted (AES-256-GCM).

## Nodes

| Node | Purpose |
|---|---|
| **C2PA Signer (certificate)** | Loads the PEM certificate chain + private key (path, PEM text, `env:NAME`, `file:PATH`, or `C2PA_SIGN_CERT` / `C2PA_PRIVATE_KEY`, or `config/c2pa_cert_chain.pem` + `config/c2pa_private_key.pem`). Algorithms: es256/384/512, ps256/384/512, ed25519. RFC 3161 timestamping (default DigiCert TSA). Can mint a **test** chain. |
| **C2PA Generate Test Certificate** | Creates a private test root CA and a claim-signing leaf (EC P-256 by default). Development only. |
| **Save Image with Content Credentials (C2PA)** | Output node. Encodes PNG / JPEG / WebP, keeps ComfyUI prompt/workflow PNG metadata (watermark secrets redacted), builds and signs the manifest, writes the file. Must be the **last** writer of the file. |
| **C2PA Read / Verify Manifest** | Reads a file (absolute path or a name in `input/` / `output/`), returns `has_manifest`, `ai_generated`, `validation_state` (`Invalid` / `Valid` / `Trusted`), a compliance summary and the full manifest store JSON. Optional extra trust anchors (your test root) make test manifests `Trusted`. |
| **C2PA Decrypt Private Assertion** | Opens the encrypted `org.comfyui.private` assertion with the provider passphrase. |

### What the save node writes

```
claim_generator_info: [{name: <system_name>, version: <system_version>, org.comfyui.provider: <provider>}]
title, format
assertions:
  c2pa.actions.v2
    - c2pa.created   (or c2pa.edited when a parent_image is connected)
        when: <RFC 3339 UTC>                                   # SB 942 (C) time and date
        digitalSourceType: .../trainedAlgorithmicMedia          # EU Art. 50(2); SB 942 (E) created/altered
        softwareAgent: {name, version}                          # SB 942 (B) system name + version
        parameters: {org.comfyui.generation_id: <uuid>, org.comfyui.model: <model>}
    - c2pa.watermarked   (when a watermark_record is connected)
  org.comfyui.generation  (Json)   provider (SB 942 (A)), system, model, created,
                                   generation_id (SB 942 (D)), image size, prompt/workflow SHA-256
  cawg.training-mining             ai_generative_training / ai_training / ai_inference / data_mining: notAllowed
  c2pa.soft-binding                alg: org.comfyui.ringmark.v1, value: "<scheme>*<payload_hex>*<key_fingerprint>"
  org.comfyui.watermark   (Json)   the watermark record (payload, public parameters, key fingerprint)
  org.comfyui.private     (Json)   AES-256-GCM box {alg, kdf, key_id, nonce, ciphertext}   (optional)
  org.comfyui.workflow    (Json)   redacted prompt + workflow                                 (optional, public!)
signature: your certificate, RFC 3161 timestamp, manifest label urn:c2pa:<uuid>
```

`digital_source_type` choices: `trainedAlgorithmicMedia` (txt2img),
`compositeWithTrainedAlgorithmicMedia` (img2img / inpainting / outpainting),
`algorithmicallyEnhanced` (AI upscaling of existing media), `compositeSynthetic`,
`digitalCreation`.

## Quick start

1. `cd ComfyUI/custom_nodes && git clone https://github.com/mccaffrey-jonathan/ComfyUI-ContentCredentials` (or install from the Comfy Registry /
   ComfyUI-Manager once published), then `pip install -r ComfyUI-ContentCredentials/requirements.txt`
   (`c2pa-python>=0.37`, wheels for Linux x86_64/aarch64, macOS, Windows x64; `cryptography`).
2. Add **C2PA Signer** with `generate_test_certificate` enabled (development), or point it at a real
   certificate (see below).
3. Replace **Save Image** with **Save Image with Content Credentials**. Fill `provider_name`,
   `system_name`, `model_name`.
4. Optionally connect `watermark_record` from **Durable Watermark Embed** (apply the watermark *before*
   saving; the manifest's hard binding hashes the watermarked pixels).
5. Verify with **C2PA Read / Verify Manifest**, `c2patool file.png`, or
   [Content Credentials Verify](https://contentcredentials.org/verify).

### Production certificates

A test chain yields `validation_state = Valid` but `signingCredential.untrusted`
in public verifiers. To be shown as trusted you need a certificate that chains
to the **C2PA Trust List** (issued by a listed CA such as DigiCert, SSL.com or
Tauth Labs to a product that passed the C2PA Conformance Program; Assurance
Level 1 = software keys). Put the chain (end-entity first) and PKCS#8 key in
`config/` or in the environment. Keep `tsa_url` set: a trusted timestamp keeps
manifests valid after the certificate expires.

For HSM/KMS keys, create the signer with `c2pa.Signer.from_callback(...)` in a
small custom node; `content_credentials.manifest.sign_image_bytes` accepts any
`c2pa.Signer`.

### Environment variables

| Variable | Meaning |
|---|---|
| `C2PA_SIGN_CERT` | PEM text or path of the certificate chain |
| `C2PA_PRIVATE_KEY` | PEM text or path of the private key |
| `C2PA_SIGNING_ALG` | default algorithm (`es256`) |
| `C2PA_TSA_URL` | timestamp authority URL |

## Regulatory mapping (summary; not legal advice)

| Requirement | Where it lands |
|---|---|
| EU AI Act Art. 50(2): output "marked in a machine-readable format and detectable as artificially generated" (applies since 2 Aug 2026; Code of Practice: signed metadata **and** imperceptible watermark) | signed manifest + `trainedAlgorithmicMedia`; watermark via the companion pack; soft binding links the two |
| California §22757.3(b) latent disclosure: (A) provider name, (B) system name + version, (C) time/date, (D) unique identifier, (AB 853/SB 1000: created vs altered) | `org.comfyui.generation.provider`, `softwareAgent{name,version}` + `claim_generator_info`, `when` + TSA timestamp, `generation_id` + manifest `urn:uuid`, `c2pa.created` vs `c2pa.edited` + `digitalSourceType` |
| California "permanent or extraordinarily difficult to remove" | metadata alone is not; pair with the durable watermark (payload = provider ID / generation id fragment) |
| China GB 45438-2025 implicit label (`Label`, `ContentProducer`, `ProduceID` XMP) | not written by this pack; the same facts are in `org.comfyui.generation` and can be mirrored into XMP downstream |
| Visible ("manifest") label for deepfakes (EU Art. 50(4), China, Korea, India) | out of scope; burn a label in with an image node when required |

## Limitations

* Any re-encode after saving (another Save Image node, an editor, most social platforms) strips the
  manifest. Recovery then depends on the watermark + your manifest registry (store the
  `manifest_json` output keyed by `generation_id` / watermark payload).
* `c2pa.soft-binding.value` is written as a text string; the C2PA CDDL specifies a byte string. The
  c2pa-rs builder has no typed path for this assertion yet; current validators accept the text form.
* The private assertion is confidential but its *presence* and size are public.
* This is not legal advice; check the current guidance for your jurisdiction.

## Tests

```
python -m pytest -q
```

## License and disclaimer

Apache License 2.0 (see `LICENSE` and `NOTICE`). Provided as is, without warranty or liability,
and **without any promise of regulatory compliance** or that a manifest will be accepted as valid
or trusted by any verifier. Nothing here is legal advice. See `NOTICE`.
