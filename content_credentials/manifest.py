"""Build and sign C2PA manifests for AI-generated images.

The manifest layout follows what Adobe Firefly, OpenAI and Google emit in 2026:

* ``claim_generator_info``          -> system name + version (SB 942 (B))
* ``c2pa.actions.v2`` / ``c2pa.created`` with ``digitalSourceType``
  ``trainedAlgorithmicMedia`` (or ``compositeWithTrainedAlgorithmicMedia`` for
  img2img / inpainting) and an object-form ``softwareAgent``  (EU AI Act Art.
  50(2) machine-readable marking; SB 942 (E) "created vs altered")
* ``when`` + RFC 3161 timestamp     -> time and date (SB 942 (C))
* manifest ``urn:uuid`` label + our ``generation_id`` -> unique identifier (SB 942 (D))
* ``org.comfyui.generation``        -> provider name (SB 942 (A)), model, seed, hashes
* ``cawg.training-mining``          -> do-not-train preferences (optional)
* ``c2pa.soft-binding`` + ``c2pa.watermarked`` -> link to the durable watermark
  so the credential can be re-associated after metadata stripping
* ``org.comfyui.private``           -> optional AES-GCM encrypted details
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

IPTC_DST_PREFIX = "http://cv.iptc.org/newscodes/digitalsourcetype/"
DIGITAL_SOURCE_TYPES = {
    "trainedAlgorithmicMedia": "Fully AI-generated (text-to-image)",
    "compositeWithTrainedAlgorithmicMedia": "AI-generated elements composited with other media (img2img, inpainting)",
    "algorithmicallyEnhanced": "Captured/existing media enhanced by AI (upscaling, denoising)",
    "compositeSynthetic": "Composite that includes synthetic elements",
    "digitalCreation": "Human digital creation (no generative AI)",
}
MIME = {"png": "image/png", "jpeg": "image/jpeg", "jpg": "image/jpeg", "webp": "image/webp"}


@dataclass
class ManifestOptions:
    provider_name: str = ""
    system_name: str = "ComfyUI"
    system_version: str = ""
    model_name: str = ""
    digital_source_type: str = "trainedAlgorithmicMedia"
    title: str = ""
    mime: str = "image/png"
    generation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: Optional[str] = None
    do_not_train: bool = True
    watermark_record: Optional[dict] = None       # from DurableWatermarkEmbed (soft binding)
    generation_details: dict = field(default_factory=dict)   # public: seed, sampler, cfg, hashes ...
    prompt: Optional[dict] = None                  # ComfyUI prompt graph (public if include_workflow)
    workflow: Optional[dict] = None
    include_workflow: bool = False
    private_details: Optional[dict] = None         # encrypted with private_key if given
    private_passphrase: Optional[str] = None
    extra_assertions: list = field(default_factory=list)
    is_edit_of_input: bool = False                 # parent ingredient supplied -> c2pa.opened first

    def timestamp(self) -> str:
        if self.created_at:
            return self.created_at
        return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_json(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def build_manifest(opts: ManifestOptions) -> dict:
    when = opts.timestamp()
    dst = opts.digital_source_type
    if not dst.startswith("http"):
        dst = IPTC_DST_PREFIX + dst
    agent = {"name": opts.system_name}
    if opts.system_version:
        agent["version"] = opts.system_version
    action = {
        "action": "c2pa.edited" if opts.is_edit_of_input else "c2pa.created",
        "when": when,
        "digitalSourceType": dst,
        "softwareAgent": agent,
        "parameters": {"org.comfyui.generation_id": opts.generation_id},
    }
    if opts.model_name:
        action["parameters"]["org.comfyui.model"] = opts.model_name
    actions = [action]
    if opts.watermark_record:
        actions.append({
            "action": "c2pa.watermarked",
            "when": when,
            "softwareAgent": {"name": "comfyui-durable-watermark"},
            "parameters": {"description": "Keyed invisible watermark (soft binding) applied to the pixels."},
        })

    generation = {
        "provider": opts.provider_name or None,
        "system": {"name": opts.system_name, "version": opts.system_version or None},
        "model": opts.model_name or None,
        "digital_source_type": dst,
        "created": when,
        "generation_id": opts.generation_id,
        "claims": {
            "ai_generated": dst.endswith("trainedAlgorithmicMedia") or dst.endswith("compositeWithTrainedAlgorithmicMedia"),
            "regulatory_notes": [
                "EU AI Act Art. 50(2) machine-readable marking",
                "California B&P Code 22757.3 latent disclosure fields: provider, system name/version, time, unique id",
            ],
        },
    }
    generation.update({k: v for k, v in (opts.generation_details or {}).items() if v is not None})
    if opts.prompt is not None:
        generation["prompt_sha256"] = _sha256_json(opts.prompt)
    if opts.workflow is not None:
        generation["workflow_sha256"] = _sha256_json(opts.workflow)
    generation = {k: v for k, v in generation.items() if v is not None}

    assertions: list[dict] = [
        {"label": "c2pa.actions.v2", "data": {"actions": actions, "allActionsIncluded": True}},
        {"label": "org.comfyui.generation", "kind": "Json", "data": generation},
    ]
    if opts.include_workflow and (opts.prompt is not None or opts.workflow is not None):
        assertions.append({"label": "org.comfyui.workflow", "kind": "Json",
                           "data": {"prompt": opts.prompt, "workflow": opts.workflow}})
    if opts.do_not_train:
        assertions.append({
            "label": "cawg.training-mining",
            "data": {"entries": {
                "cawg.ai_generative_training": {"use": "notAllowed"},
                "cawg.ai_training": {"use": "notAllowed"},
                "cawg.ai_inference": {"use": "notAllowed"},
                "cawg.data_mining": {"use": "notAllowed"},
            }},
        })
    if opts.watermark_record:
        rec = opts.watermark_record
        value = f"{rec.get('scheme', '')}*{rec.get('payload_hex', '')}*{rec.get('key_fingerprint', '')}"
        assertions.append({
            "label": "c2pa.soft-binding",
            "data": {
                "alg": rec.get("scheme", "org.comfyui.ringmark.v1"),
                "blocks": [{"scope": {}, "value": value}],
                "bindingMetadata": {
                    "description": "Keyed radial/angular spectral watermark; payload and key fingerprint "
                                   "identify the manifest in the provider's registry.",
                },
            },
        })
        assertions.append({"label": "org.comfyui.watermark", "kind": "Json", "data": rec})
    if opts.private_details and opts.private_passphrase:
        from .crypto_box import encrypt_json

        aad = opts.generation_id.encode("utf-8")
        box = encrypt_json(opts.private_details, opts.private_passphrase, aad=aad)
        box["generation_id"] = opts.generation_id
        assertions.append({"label": "org.comfyui.private", "kind": "Json", "data": box})
    assertions.extend(opts.extra_assertions or [])

    manifest = {
        "claim_generator_info": [agent | {"org.comfyui.provider": opts.provider_name}] if opts.provider_name else [agent],
        "title": opts.title or f"{opts.generation_id}.{opts.mime.split('/')[-1]}",
        "format": opts.mime,
        "assertions": assertions,
    }
    return manifest


def sign_image_bytes(image_bytes: bytes, mime: str, manifest: dict, signer,
                     parent_bytes: Optional[bytes] = None, parent_mime: Optional[str] = None) -> tuple[bytes, bytes]:
    """Return (signed asset bytes, manifest store bytes)."""
    import c2pa

    builder = c2pa.Builder.from_json(json.dumps(manifest))
    try:
        if parent_bytes is not None:
            builder.add_ingredient(
                json.dumps({"title": "input image", "relationship": "parentOf",
                            "instance_id": f"xmp.iid:{uuid.uuid4()}"}),
                parent_mime or "image/png", io.BytesIO(parent_bytes))
        src = io.BytesIO(image_bytes)
        dst = io.BytesIO()
        store = builder.sign(signer, mime, src, dst)
        return dst.getvalue(), bytes(store)
    finally:
        try:
            builder.close()
        except Exception:  # pragma: no cover
            pass
