# SPDX-License-Identifier: Apache-2.0
"""Tests for the Content Credentials helpers (no ComfyUI import; needs c2pa-python + cryptography)."""
import io
import json
import os
import sys

import numpy as np
import pytest
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

c2pa = pytest.importorskip("c2pa")

from content_credentials.certs import generate_test_chain  # noqa: E402
from content_credentials.crypto_box import decrypt_json, encrypt_json  # noqa: E402
from content_credentials.manifest import ManifestOptions, build_manifest, sign_image_bytes  # noqa: E402
from content_credentials.signing import SignerConfig, load_signer_config, make_signer  # noqa: E402
from content_credentials.verify import read_manifest, summarize  # noqa: E402


@pytest.fixture(scope="module")
def chain(tmp_path_factory):
    d = tmp_path_factory.mktemp("certs")
    return generate_test_chain(organization="Unit Test Org", out_dir=str(d))


@pytest.fixture(scope="module")
def signer_cfg(chain):
    return load_signer_config(cert=chain["cert_chain"], key=chain["private_key"], alg="es256", tsa_url="none")


@pytest.fixture(scope="module")
def png_bytes():
    rng = np.random.default_rng(0)
    arr = (rng.random((96, 128, 3)) * 255).astype(np.uint8)
    buf = io.BytesIO()
    from PIL.PngImagePlugin import PngInfo

    meta = PngInfo()
    meta.add_text("prompt", json.dumps({"1": {"class_type": "KSampler", "inputs": {"seed": 1}}}))
    Image.fromarray(arr).save(buf, "PNG", pnginfo=meta)
    return buf.getvalue()


def test_generate_chain_has_two_certs(chain):
    pem = open(chain["cert_chain"]).read()
    assert pem.count("BEGIN CERTIFICATE") == 2
    assert "BEGIN PRIVATE KEY" in open(chain["private_key"]).read()
    assert chain["alg"] == "es256"


def test_signer_config_from_env(chain, monkeypatch):
    monkeypatch.setenv("C2PA_SIGN_CERT", chain["cert_chain"])
    monkeypatch.setenv("C2PA_PRIVATE_KEY", chain["private_key"])
    cfg = load_signer_config()
    assert cfg.alg == "es256" and cfg.is_test_certificate
    assert cfg.subject()["organization"] == "Unit Test Org"
    pem_cfg = load_signer_config(cert=open(chain["cert_chain"]).read(), key=open(chain["private_key"]).read())
    assert pem_cfg.cert_chain_pem == cfg.cert_chain_pem


def test_manifest_shape():
    opts = ManifestOptions(provider_name="Acme AI", system_name="ComfyUI", system_version="0.3.x",
                           model_name="flux1-dev", mime="image/png", title="x.png",
                           watermark_record={"scheme": "org.comfyui.ringmark.v1", "payload_hex": "0xc0ffee42",
                                             "key_fingerprint": "abcd", "payload_bits": 32},
                           private_details={"user": "u-1"}, private_passphrase="pp")
    m = build_manifest(opts)
    labels = [a["label"] for a in m["assertions"]]
    assert labels[0] == "c2pa.actions.v2"
    act = m["assertions"][0]["data"]["actions"][0]
    assert act["action"] == "c2pa.created"
    assert act["digitalSourceType"].endswith("/trainedAlgorithmicMedia")
    assert act["softwareAgent"] == {"name": "ComfyUI", "version": "0.3.x"}
    assert "org.comfyui.generation" in labels and "cawg.training-mining" in labels
    assert "c2pa.soft-binding" in labels and "org.comfyui.private" in labels
    gen = next(a["data"] for a in m["assertions"] if a["label"] == "org.comfyui.generation")
    assert gen["provider"] == "Acme AI" and gen["generation_id"] == opts.generation_id
    assert gen["ai_generated"] is True and gen["created_or_altered"] == "created"
    assert "regulatory_notes" not in gen and "claims" not in gen
    assert m["assertions"][0]["data"]["actions"][1]["action"] == "c2pa.watermarked.bound"
    assert m["claim_generator_info"][0]["name"] == "ComfyUI"
    box = next(a["data"] for a in m["assertions"] if a["label"] == "org.comfyui.private")
    assert decrypt_json(box, "pp") == {"user": "u-1"} or decrypt_json(box, "pp")["user"] == "u-1"


def test_crypto_box_roundtrip_and_tamper():
    box = encrypt_json({"a": 1}, "secret", aad=b"id")
    assert decrypt_json(box, "secret") == {"a": 1}
    with pytest.raises(Exception):
        decrypt_json(box, "wrong")
    tampered = dict(box)
    tampered["aad"] = ""
    with pytest.raises(Exception):
        decrypt_json(tampered, "secret")


@pytest.mark.parametrize("fmt,mime", [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")])
def test_sign_and_verify(signer_cfg, png_bytes, fmt, mime, chain):
    im = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    buf = io.BytesIO()
    im.save(buf, fmt, **({"quality": 90} if fmt != "PNG" else {}))
    opts = ManifestOptions(provider_name="Acme AI", system_version="0.3.x", mime=mime, title=f"t.{fmt.lower()}",
                           watermark_record={"scheme": "org.comfyui.ringmark.v1", "payload_hex": "0x01",
                                             "key_fingerprint": "ff", "payload_bits": 32})
    signer = make_signer(signer_cfg)
    signed, store = sign_image_bytes(buf.getvalue(), mime, build_manifest(opts), signer)
    assert len(store) > 1000 and len(signed) > len(buf.getvalue())
    info = read_manifest(data=signed, mime=mime)
    assert info["has_manifest"]
    s = summarize(info)
    assert s["ai_generated"] is True
    assert s["validation_state"] in ("Valid", "Trusted")
    assert "signingCredential.untrusted" in s["failures"]  # test cert is not on the C2PA trust list
    assert s["generation"]["provider"] == "Acme AI"
    assert s["soft_bindings"][0]["alg"] == "org.comfyui.ringmark.v1"
    assert s["software_agents"][0].startswith("ComfyUI")
    # with our root as a user trust anchor the manifest becomes Trusted
    info_t = read_manifest(data=signed, mime=mime, trust_anchors_pem=open(chain["root"]).read())
    assert info_t["validation_state"] == "Trusted", info_t.get("validation_results")


def test_png_text_chunks_survive_signing(signer_cfg, png_bytes):
    signer = make_signer(signer_cfg)
    signed, _ = sign_image_bytes(png_bytes, "image/png", build_manifest(ManifestOptions(title="a.png")), signer)
    im = Image.open(io.BytesIO(signed))
    assert "prompt" in im.info and "KSampler" in im.info["prompt"]


def test_tamper_detection(signer_cfg, png_bytes):
    signer = make_signer(signer_cfg)
    signed, _ = sign_image_bytes(png_bytes, "image/png", build_manifest(ManifestOptions(title="a.png")), signer)
    im = Image.open(io.BytesIO(signed)).convert("RGB")
    arr = np.array(im)
    arr[0, 0] = 255 - arr[0, 0]
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, "PNG")  # re-encoding strips the manifest entirely
    assert not read_manifest(data=buf.getvalue(), mime="image/png")["has_manifest"]


def test_unsigned_image_has_no_manifest(png_bytes):
    assert read_manifest(data=png_bytes, mime="image/png") == {"has_manifest": False}
    assert summarize({"has_manifest": False})["ai_generated"] is None


def test_crypto_box_scrypt_and_legacy():
    box = encrypt_json({"a": 1}, "pw")
    assert box["kdf"] == "scrypt" and box["salt"] and len(box["key_id"]) == 16
    assert decrypt_json(box, "pw") == {"a": 1}
    # two boxes with the same passphrase publish different key ids (per-box salt)
    assert encrypt_json({"a": 1}, "pw")["key_id"] != box["key_id"]
    # boxes written by 0.1.0 (HKDF, fixed salt) still open
    import base64
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"comfyui-c2pa-private-v1",
               info=b"comfyui-content-credentials/private-assertion/v1").derive(b"pw")
    nonce = b"\x01" * 12
    ct = AESGCM(key).encrypt(nonce, b'{"legacy":true}', None)
    legacy = {"alg": "A256GCM", "kdf": "HKDF-SHA256", "nonce": base64.b64encode(nonce).decode(),
              "ciphertext": base64.b64encode(ct).decode(), "aad": ""}
    assert decrypt_json(legacy, "pw") == {"legacy": True}


def test_redaction_fallback_covers_workflow_format():
    from content_credentials.redact import redact_extra_pnginfo, redact_prompt, sensitive_literals

    prompt = {"9": {"class_type": "DurableWatermarkKey", "inputs": {"secret": "hunter2", "payload": "acme"}},
              "12": {"class_type": "C2PASaveImage", "inputs": {"private_passphrase": "pp-literal", "provider_name": "Acme"}},
              "13": {"class_type": "C2PASigner", "inputs": {"private_key": "config/key.pem"}}}
    assert sensitive_literals(prompt) == {"hunter2", "pp-literal"}
    red = redact_prompt(prompt)
    assert red["9"]["inputs"]["secret"] == "<redacted>" and red["12"]["inputs"]["private_passphrase"] == "<redacted>"
    assert red["13"]["inputs"]["private_key"] == "config/key.pem"
    extra = {"workflow": {"nodes": [{"id": 9, "type": "DurableWatermarkKey", "widgets_values": ["hunter2", "acme", 32, 1.0]},
                                    {"id": 12, "type": "C2PASaveImage", "widgets_values": ["x", "png", 95, "Acme", "pp-literal"]}]}}
    out = redact_extra_pnginfo(extra, prompt)
    assert out["workflow"]["nodes"][0]["widgets_values"][0] == "<redacted>"
    assert out["workflow"]["nodes"][1]["widgets_values"][4] == "<redacted>"
    assert out["workflow"]["nodes"][1]["widgets_values"][3] == "Acme"
    assert extra["workflow"]["nodes"][0]["widgets_values"][0] == "hunter2"  # input untouched
