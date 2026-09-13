# SPDX-License-Identifier: Apache-2.0
"""ComfyUI nodes: C2PA Content Credentials for generated images (V3 node API)."""
from __future__ import annotations

import io
import json
import logging
import os
import uuid

import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from typing_extensions import override

import folder_paths
from comfy.cli_args import args
from comfy_api.latest import ComfyExtension, io as cio, ui

from content_credentials.manifest import DIGITAL_SOURCE_TYPES, MIME, ManifestOptions, build_manifest, sign_image_bytes
from content_credentials.signing import ALGORITHMS, DEFAULT_TSA, SignerError, load_signer_config, make_signer, CONFIG_DIR
from content_credentials.certs import generate_test_chain
from content_credentials.verify import read_manifest, summarize
from content_credentials.crypto_box import decrypt_json

log = logging.getLogger("content_credentials")

C2PASignerType = cio.Custom("C2PA_SIGNER")


def _comfy_version() -> str:
    try:
        from comfyui_version import __version__

        return str(__version__)
    except Exception:  # pragma: no cover
        return "unknown"


def _expand(value: str) -> str:
    v = (value or "").strip()
    if v.startswith("env:"):
        return os.environ.get(v[4:].strip(), "")
    if v.startswith("file:"):
        try:
            with open(os.path.expanduser(v[5:].strip()), "r", encoding="utf-8") as fh:
                return fh.read().strip()
        except OSError:
            return ""
    return v


def _redact(prompt):
    try:
        from durable_watermark.keys import redact_prompt

        return redact_prompt(prompt)
    except Exception:
        return prompt


class C2PASigner(cio.ComfyNode):
    @classmethod
    def define_schema(cls) -> cio.Schema:
        return cio.Schema(
            node_id="C2PASigner",
            display_name="C2PA Signer (certificate)",
            category="content_credentials",
            description=(
                "Signing identity for Content Credentials. Provide a PEM certificate chain (end-entity first) and "
                "the matching private key as a path, PEM text, 'env:NAME' or 'file:PATH'. Empty values fall back "
                "to C2PA_SIGN_CERT / C2PA_PRIVATE_KEY or config/c2pa_cert_chain.pem + c2pa_private_key.pem. "
                "For development, enable generate_test_certificate (valid but untrusted)."
            ),
            inputs=[
                cio.String.Input("cert_chain", default="", placeholder="path, PEM, env:C2PA_SIGN_CERT or file:..."),
                cio.String.Input("private_key", default="", placeholder="path, PEM, env:C2PA_PRIVATE_KEY or file:..."),
                cio.Combo.Input("algorithm", options=list(ALGORITHMS), default="es256"),
                cio.String.Input("tsa_url", default=DEFAULT_TSA,
                                 tooltip="RFC 3161 timestamp authority. 'none' to disable (not recommended)."),
                cio.Boolean.Input("generate_test_certificate", default=False,
                                  tooltip="Create a self-issued TEST chain in the pack's config/ dir if none is configured."),
                cio.String.Input("test_organization", default="ComfyUI Test", optional=True),
            ],
            outputs=[C2PASignerType.Output(display_name="signer"), cio.String.Output(display_name="signer_info")],
        )

    @classmethod
    def execute(cls, cert_chain, private_key, algorithm, tsa_url, generate_test_certificate,
                test_organization="ComfyUI Test") -> cio.NodeOutput:
        try:
            cfg = load_signer_config(cert=cert_chain, key=private_key, alg=algorithm, tsa_url=tsa_url,
                                     generate_test_if_missing=bool(generate_test_certificate),
                                     test_org=test_organization or "ComfyUI Test")
        except SignerError as exc:
            raise RuntimeError(str(exc)) from exc
        info = cfg.subject() | {"alg": cfg.alg, "tsa_url": cfg.tsa_url, "test_certificate": cfg.is_test_certificate}
        signer = {"cert_chain_pem": cfg.cert_chain_pem, "private_key_pem": cfg.private_key_pem, "alg": cfg.alg,
                  "tsa_url": cfg.tsa_url, "is_test": cfg.is_test_certificate, "info": info}
        return cio.NodeOutput(signer, json.dumps(info, indent=2))


class C2PAGenerateTestCertificate(cio.ComfyNode):
    @classmethod
    def define_schema(cls) -> cio.Schema:
        return cio.Schema(
            node_id="C2PAGenerateTestCertificate",
            display_name="C2PA Generate Test Certificate",
            category="content_credentials",
            description="Creates a private test root CA and a claim-signing certificate (development only).",
            inputs=[
                cio.String.Input("organization", default="ComfyUI Test"),
                cio.String.Input("common_name", default="ComfyUI Test C2PA Signer"),
                cio.Combo.Input("key_type", options=["ec256", "ec384", "rsa", "ed25519"], default="ec256"),
                cio.String.Input("output_dir", default="", tooltip="Empty = the pack's config/ directory."),
                cio.Boolean.Input("overwrite", default=False),
            ],
            outputs=[cio.String.Output(display_name="cert_chain_path"), cio.String.Output(display_name="private_key_path"),
                     cio.String.Output(display_name="root_ca_path")],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, organization, common_name, key_type, output_dir, overwrite) -> cio.NodeOutput:
        out = generate_test_chain(organization=organization, common_name=common_name, key_type=key_type,
                                  out_dir=output_dir or CONFIG_DIR, overwrite=bool(overwrite))
        return cio.NodeOutput(out["cert_chain"], out["private_key"], out["root"])


class C2PASaveImage(cio.ComfyNode):
    @classmethod
    def define_schema(cls) -> cio.Schema:
        return cio.Schema(
            node_id="C2PASaveImage",
            display_name="Save Image with Content Credentials (C2PA)",
            category="content_credentials",
            description=(
                "Encodes each image (PNG/JPEG/WebP), embeds a signed C2PA manifest declaring it AI-generated "
                "(c2pa.created + trainedAlgorithmicMedia), records provider / system / time / unique id "
                "(California SB 942 latent-disclosure fields, EU AI Act Art. 50(2)), optionally a do-not-train "
                "assertion, a soft binding to the durable watermark and an encrypted private assertion. "
                "This node must be the LAST writer of the file: re-saving with another node strips the manifest."
            ),
            inputs=[
                cio.Image.Input("images"),
                C2PASignerType.Input("signer"),
                cio.String.Input("filename_prefix", default="ComfyUI_c2pa"),
                cio.Combo.Input("format", options=["png", "jpeg", "webp"], default="png"),
                cio.Int.Input("quality", default=95, min=1, max=100, tooltip="JPEG/WebP quality."),
                cio.String.Input("provider_name", default="", tooltip="Legal/brand name of the provider (SB 942 (A))."),
                cio.String.Input("system_name", default="ComfyUI", tooltip="GenAI system name (SB 942 (B))."),
                cio.String.Input("system_version", default="", tooltip="Empty = ComfyUI version."),
                cio.String.Input("model_name", default="", optional=True, tooltip="Checkpoint / model identifier."),
                cio.Combo.Input("digital_source_type", options=list(DIGITAL_SOURCE_TYPES.keys()),
                                default="trainedAlgorithmicMedia",
                                tooltip="; ".join(f"{k}: {v}" for k, v in DIGITAL_SOURCE_TYPES.items())),
                cio.Boolean.Input("do_not_train", default=True, tooltip="Add cawg.training-mining 'notAllowed' entries."),
                cio.Boolean.Input("embed_workflow_metadata", default=True,
                                  tooltip="Keep ComfyUI prompt/workflow in PNG text chunks (secrets redacted)."),
                cio.Boolean.Input("workflow_in_manifest", default=False,
                                  tooltip="Also put the (redacted) prompt/workflow inside the signed manifest (public!)."),
                cio.String.Input("watermark_record", default="", optional=True,
                                 tooltip="Connect the 'watermark_record' output of Durable Watermark Embed."),
                cio.String.Input("private_details", default="", multiline=True, optional=True,
                                 tooltip="JSON or free text stored encrypted (needs private_passphrase)."),
                cio.String.Input("private_passphrase", default="", optional=True,
                                 tooltip="Passphrase for the encrypted assertion: literal, env:NAME or file:PATH."),
                cio.Boolean.Input("encrypt_prompt", default=False, optional=True,
                                  tooltip="Include the full prompt/workflow in the encrypted private assertion."),
                cio.Image.Input("parent_image", optional=True,
                                tooltip="Input image for img2img/inpainting; recorded as parent ingredient."),
            ],
            outputs=[cio.String.Output(display_name="file_paths"), cio.String.Output(display_name="manifest_json")],
            hidden=[cio.Hidden.prompt, cio.Hidden.extra_pnginfo],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, images, signer, filename_prefix, format, quality, provider_name, system_name, system_version,
                model_name="", digital_source_type="trainedAlgorithmicMedia", do_not_train=True,
                embed_workflow_metadata=True, workflow_in_manifest=False, watermark_record="", private_details="",
                private_passphrase="", encrypt_prompt=False, parent_image=None) -> cio.NodeOutput:
        try:
            import c2pa  # noqa: F401
        except ImportError as exc:
            raise RuntimeError("c2pa-python is not installed: pip install 'c2pa-python>=0.37'") from exc
        from content_credentials.signing import SignerConfig

        scfg = SignerConfig(signer["cert_chain_pem"], signer["private_key_pem"], signer["alg"], signer.get("tsa_url"))
        ext = "jpg" if format == "jpeg" else format
        mime = MIME[format]
        full_output_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(
            filename_prefix, folder_paths.get_output_directory(), images[0].shape[1], images[0].shape[0])

        prompt = cls.hidden.prompt if cls.hidden else None
        extra = cls.hidden.extra_pnginfo if cls.hidden else None
        red_prompt = _redact(prompt) if prompt is not None else None
        workflow = None
        if extra and isinstance(extra, dict):
            workflow = extra.get("workflow")

        wm = None
        if watermark_record:
            try:
                wm = json.loads(watermark_record)
            except json.JSONDecodeError:
                log.warning("content_credentials: watermark_record is not JSON; ignoring")
        passphrase = _expand(private_passphrase)
        priv = None
        if passphrase and (private_details or encrypt_prompt):
            try:
                priv = {"details": json.loads(private_details)} if private_details.strip().startswith(("{", "[")) else {"details": private_details}
            except json.JSONDecodeError:
                priv = {"details": private_details}
            if encrypt_prompt:
                priv["prompt"] = prompt
                priv["workflow"] = workflow
        elif private_details and not passphrase:
            log.warning("content_credentials: private_details given without private_passphrase; not stored")

        parent_bytes = None
        if parent_image is not None:
            pb = io.BytesIO()
            Image.fromarray(np.clip(255.0 * parent_image[0].cpu().numpy(), 0, 255).astype(np.uint8)).save(pb, "PNG")
            parent_bytes = pb.getvalue()

        results, paths, manifests = [], [], []
        c2pa_signer = make_signer(scfg)
        try:
            for batch_number, image in enumerate(images):
                arr = np.clip(255.0 * image.cpu().numpy(), 0, 255).astype(np.uint8)
                img = Image.fromarray(arr)
                buf = io.BytesIO()
                if format == "png":
                    metadata = None
                    if embed_workflow_metadata and not args.disable_metadata:
                        metadata = PngInfo()
                        if red_prompt is not None:
                            metadata.add_text("prompt", json.dumps(red_prompt))
                        if extra is not None:
                            for k, v in extra.items():
                                metadata.add_text(k, json.dumps(v))
                    img.save(buf, "PNG", pnginfo=metadata, compress_level=4)
                elif format == "jpeg":
                    img.convert("RGB").save(buf, "JPEG", quality=int(quality), optimize=True)
                else:
                    img.save(buf, "WEBP", quality=int(quality))

                gen_id = str(uuid.uuid4())
                file = f"{filename.replace('%batch_num%', str(batch_number))}_{counter:05}_.{ext}"
                opts = ManifestOptions(
                    provider_name=provider_name, system_name=system_name or "ComfyUI",
                    system_version=system_version or _comfy_version(), model_name=model_name or "",
                    digital_source_type=digital_source_type, title=file, mime=mime, generation_id=gen_id,
                    do_not_train=bool(do_not_train), watermark_record=wm,
                    generation_details={"image_width": int(arr.shape[1]), "image_height": int(arr.shape[0]),
                                        "batch_index": batch_number},
                    prompt=red_prompt, workflow=workflow, include_workflow=bool(workflow_in_manifest),
                    private_details=priv, private_passphrase=passphrase or None,
                    is_edit_of_input=parent_bytes is not None,
                )
                manifest = build_manifest(opts)
                signed, _store = sign_image_bytes(buf.getvalue(), mime, manifest, c2pa_signer,
                                                  parent_bytes=parent_bytes, parent_mime="image/png")
                path = os.path.join(full_output_folder, file)
                with open(path, "wb") as fh:
                    fh.write(signed)
                results.append(ui.SavedResult(file, subfolder, cio.FolderType.output))
                paths.append(path)
                manifests.append(manifest)
                counter += 1
        finally:
            try:
                c2pa_signer.close()
            except Exception:  # pragma: no cover
                pass
        return cio.NodeOutput(json.dumps(paths), json.dumps(manifests if len(manifests) > 1 else manifests[0], indent=2),
                              ui=ui.SavedImages(results))


class C2PAReadManifest(cio.ComfyNode):
    @classmethod
    def define_schema(cls) -> cio.Schema:
        return cio.Schema(
            node_id="C2PAReadManifest",
            display_name="C2PA Read / Verify Manifest",
            category="content_credentials",
            description="Reads Content Credentials from an image file and reports validation state and AI-generated status.",
            inputs=[
                cio.String.Input("path", default="", tooltip="Absolute path, or a name inside the input/ or output/ folders."),
                cio.String.Input("trust_anchors", default="", optional=True,
                                 tooltip="Optional PEM (path/env:/file:) of extra trust anchors, e.g. your test root."),
            ],
            outputs=[cio.Boolean.Output(display_name="has_manifest"), cio.Boolean.Output(display_name="ai_generated"),
                     cio.String.Output(display_name="validation_state"), cio.String.Output(display_name="summary_json"),
                     cio.String.Output(display_name="manifest_store_json")],
        )

    @classmethod
    def execute(cls, path, trust_anchors="") -> cio.NodeOutput:
        p = path.strip()
        if not os.path.isabs(p):
            for base in (folder_paths.get_input_directory(), folder_paths.get_output_directory()):
                cand = os.path.join(base, p)
                if os.path.exists(cand):
                    p = cand
                    break
        if not os.path.exists(p):
            raise RuntimeError(f"file not found: {path}")
        anchors = _expand(trust_anchors) if trust_anchors else None
        if anchors and "-----BEGIN" not in anchors and os.path.exists(anchors):
            with open(anchors, "r", encoding="utf-8") as fh:
                anchors = fh.read()
        info = read_manifest(p, trust_anchors_pem=anchors or None)
        s = summarize(info)
        return cio.NodeOutput(bool(s.get("has_manifest")), bool(s.get("ai_generated")), str(s.get("validation_state") or ""),
                              json.dumps(s, indent=2), json.dumps(info.get("store", {}), indent=2))


class C2PADecryptPrivateAssertion(cio.ComfyNode):
    @classmethod
    def define_schema(cls) -> cio.Schema:
        return cio.Schema(
            node_id="C2PADecryptPrivateAssertion",
            display_name="C2PA Decrypt Private Assertion",
            category="content_credentials",
            description="Decrypts the org.comfyui.private assertion of a manifest store JSON with the provider passphrase.",
            inputs=[cio.String.Input("manifest_store_json", default="", multiline=True),
                    cio.String.Input("private_passphrase", default="", tooltip="literal, env:NAME or file:PATH")],
            outputs=[cio.String.Output(display_name="decrypted_json")],
        )

    @classmethod
    def execute(cls, manifest_store_json, private_passphrase) -> cio.NodeOutput:
        store = json.loads(manifest_store_json)
        active = store.get("manifests", {}).get(store.get("active_manifest"), store)
        box = next((a.get("data") for a in active.get("assertions", []) if a.get("label") == "org.comfyui.private"), None)
        if box is None:
            raise RuntimeError("no org.comfyui.private assertion in manifest")
        data = decrypt_json(box, _expand(private_passphrase))
        return cio.NodeOutput(json.dumps(data, indent=2))


class ContentCredentialsExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[cio.ComfyNode]]:
        return [C2PASigner, C2PAGenerateTestCertificate, C2PASaveImage, C2PAReadManifest, C2PADecryptPrivateAssertion]


async def comfy_entrypoint() -> ContentCredentialsExtension:
    return ContentCredentialsExtension()
