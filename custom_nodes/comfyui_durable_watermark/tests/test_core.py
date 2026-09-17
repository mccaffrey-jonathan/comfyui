# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the durable watermark core (numpy only; no ComfyUI import)."""
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from durable_watermark.core import (  # noqa: E402
    KeySchedule,
    WatermarkConfig,
    crc8,
    detect,
    embed,
    image_statistics,
    payload_from_string,
    payload_to_hex,
    recommended_strength,
)
from durable_watermark import keys  # noqa: E402

PAYLOAD = 0xC0FFEE42


@pytest.fixture(scope="module")
def image():
    """A 512x512 natural-ish test image: 1/f texture + gradient + a flat patch."""
    rng = np.random.default_rng(7)
    h = w = 512
    f = np.fft.fftfreq(h)[:, None] ** 2 + np.fft.fftfreq(w)[None, :] ** 2
    spec = (rng.standard_normal((h, w)) + 1j * rng.standard_normal((h, w))) / np.maximum(np.sqrt(f), 1e-3)
    tex = np.real(np.fft.ifft2(spec))
    tex = (tex - tex.min()) / (tex.max() - tex.min())
    yy, xx = np.mgrid[0:h, 0:w] / h
    img = np.stack([0.6 * tex + 0.3 * xx, 0.5 * tex ** 1.3 + 0.2 * yy, 0.7 - 0.5 * tex], axis=-1)
    img[380:480, 40:200] = [0.85, 0.85, 0.9]
    return np.clip(img, 0, 1)


@pytest.fixture(scope="module")
def cfg():
    return WatermarkConfig(secret="unit-test-secret", payload_bits=32, strength=1.0)


@pytest.fixture(scope="module")
def marked(image, cfg):
    return embed(image, cfg, PAYLOAD)


def quantize(a):
    return np.clip(np.round(a * 255.0), 0, 255) / 255.0


def test_config_validation():
    with pytest.raises(ValueError):
        WatermarkConfig(payload_bits=65)
    with pytest.raises(ValueError):
        WatermarkConfig(r_min=0.4, r_max=0.3)
    with pytest.raises(ValueError):
        WatermarkConfig(strength=0)
    with pytest.raises(ValueError):
        KeySchedule.from_config(WatermarkConfig(secret="x", payload_bits=64, r_min=0.3, r_max=0.36))


def test_key_schedule_is_deterministic_and_keyed():
    a = KeySchedule.from_config(WatermarkConfig(secret="a"))
    a2 = KeySchedule.from_config(WatermarkConfig(secret="a"))
    b = KeySchedule.from_config(WatermarkConfig(secret="b"))
    assert np.array_equal(a.radial, a2.radial) and np.array_equal(a.phases, a2.phases)
    assert not np.array_equal(a.radial, b.radial)
    assert np.mean(a.signs == b.signs) < 0.7
    assert WatermarkConfig(secret="a").key_fingerprint() != WatermarkConfig(secret="b").key_fingerprint()
    # public params are part of the key material
    assert WatermarkConfig(secret="a").key_fingerprint() != WatermarkConfig(secret="a", r_max=0.3).key_fingerprint()


def test_payload_parsing():
    assert payload_from_string("", 32) == 0
    assert payload_from_string("42", 32) == 42
    assert payload_from_string("0xC0FFEE42", 32) == 0xC0FFEE42
    assert payload_from_string("0xC0FFEE42", 16) == 0xEE42
    h = payload_from_string("my-provider", 32)
    assert 0 <= h < 2 ** 32 and h == payload_from_string("my-provider", 32)
    assert payload_from_string("x", 0) == 0
    assert payload_to_hex(0xC0FFEE42, 32) == "0xc0ffee42"
    assert payload_to_hex(5, 0) == ""
    assert crc8(b"123456789") == 0xF4  # CRC-8 (poly 0x07) check value


def test_embed_is_imperceptible_and_preserves_shape(image, marked):
    assert marked.shape == image.shape
    assert marked.min() >= 0.0 and marked.max() <= 1.0
    mse = np.mean((marked - image) ** 2)
    psnr = 10 * np.log10(1.0 / mse)
    assert psnr > 38.0
    # chroma is preserved: the same delta is added to every channel
    d = marked - image
    assert np.abs(d[..., 0] - d[..., 1]).max() < 1e-6 + 1e-3  # (clipping may break this only at saturation)


def test_roundtrip_and_wrong_key(image, marked, cfg):
    res = detect(quantize(marked), cfg, expected_payload=PAYLOAD)
    assert res.detected and res.crc_ok and res.expected_match
    assert res.payload == PAYLOAD
    assert abs(res.scale - 1.0) < 0.02 and abs(res.rotation_deg) < 3 and not res.flipped

    unmarked = detect(quantize(image), cfg, expected_payload=PAYLOAD)
    assert not unmarked.detected and unmarked.z_score < 4

    wrong = detect(quantize(marked), WatermarkConfig(secret="another-secret", payload_bits=32), expected_payload=PAYLOAD)
    assert not wrong.detected and wrong.z_score < 4


def test_rotation_and_flip_invariance(marked, cfg):
    q = quantize(marked)
    for name, arr in [("rot90", np.rot90(q)), ("rot180", np.rot90(q, 2)), ("flipH", q[:, ::-1]), ("flipV", q[::-1])]:
        res = detect(np.ascontiguousarray(arr), cfg, expected_payload=PAYLOAD)
        assert res.detected and res.expected_match, (name, res.z_score, res.payload_hex)


def test_crop_translation_invariance(marked, cfg):
    q = quantize(marked)
    crop = q[60:460, 90:490]           # 400x400 window, off-centre
    res = detect(np.ascontiguousarray(crop), cfg, expected_payload=PAYLOAD)
    assert res.detected and res.expected_match, (res.z_score, res.payload_hex)


def test_rescale_invariance(marked, cfg):
    from PIL import Image

    im = Image.fromarray((quantize(marked) * 255).astype(np.uint8))
    small = np.asarray(im.resize((384, 384), Image.BICUBIC), dtype=np.float64) / 255.0
    res = detect(small, cfg, expected_payload=PAYLOAD)
    assert res.detected and res.expected_match, (res.z_score, res.payload_hex)
    assert abs(res.scale - 0.75) < 0.03


def test_colour_edits(marked, cfg):
    q = quantize(marked)
    gray = np.repeat(q.mean(axis=-1, keepdims=True), 3, axis=-1)
    bright = np.clip(q * 1.25, 0, 1)
    gamma = q ** 0.7
    for name, arr in [("gray", gray), ("bright", bright), ("gamma", gamma)]:
        res = detect(quantize(arr), cfg, expected_payload=PAYLOAD)
        assert res.detected and res.expected_match, (name, res.z_score)


def test_jpeg(marked, cfg):
    import io

    from PIL import Image

    im = Image.fromarray((quantize(marked) * 255).astype(np.uint8))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    buf.seek(0)
    arr = np.asarray(Image.open(buf).convert("RGB"), dtype=np.float64) / 255.0
    res = detect(arr, cfg, expected_payload=PAYLOAD)
    assert res.detected and res.expected_match, (res.z_score, res.payload_hex)


def test_zero_bit_mode(image):
    cfg0 = WatermarkConfig(secret="zero-bit", payload_bits=0)
    m = embed(image, cfg0, 0)
    res = detect(quantize(m), cfg0)
    assert res.detected and res.payload_hex == ""


def test_secret_resolution(monkeypatch, tmp_path):
    monkeypatch.delenv(keys.ENV_SECRET, raising=False)
    monkeypatch.delenv(keys.ENV_ENFORCE, raising=False)
    monkeypatch.setattr(keys, "SECRET_FILE", str(tmp_path / "nope.txt"))
    monkeypatch.setattr(keys, "CONFIG_JSON", str(tmp_path / "nope.json"))
    with pytest.raises(keys.SecretError):
        keys.resolve_secret("")
    assert keys.resolve_secret("literal") == "literal"
    monkeypatch.setenv("MY_WM", "from-env")
    assert keys.resolve_secret("env:MY_WM") == "from-env"
    p = tmp_path / "s.txt"
    p.write_text("from-file\n")
    assert keys.resolve_secret(f"file:{p}") == "from-file"
    monkeypatch.setenv(keys.ENV_SECRET, "server")
    assert keys.resolve_secret("") == "server"
    # enforcement overrides the widget
    monkeypatch.setenv(keys.ENV_ENFORCE, "1")
    assert keys.resolve_secret("literal") == "server"
    monkeypatch.setenv(keys.ENV_PAYLOAD, "0x1234")
    assert keys.resolve_payload("0xABCD") == "0x1234"


def test_redact_prompt():
    prompt = {"1": {"class_type": "DurableWatermarkKey", "inputs": {"secret": "hunter2", "payload": "x"}},
              "2": {"class_type": "DurableWatermarkKey", "inputs": {"secret": "env:FOO"}},
              "3": {"class_type": "Other", "inputs": {"secret": "keep"}}}
    red = keys.redact_prompt(prompt)
    assert red["1"]["inputs"]["secret"] == "<redacted>"
    assert red["2"]["inputs"]["secret"] == "env:FOO"
    assert red["3"]["inputs"]["secret"] == "keep"
    assert prompt["1"]["inputs"]["secret"] == "hunter2"  # original untouched


def test_p_value_is_gumbel_tail(image, marked, cfg):
    res = detect(quantize(marked), cfg)
    assert 0.0 <= res.p_value < 1e-6
    neg = detect(quantize(image), cfg)
    assert neg.p_value > 0.01


def test_recommended_strength_policy(image):
    st = image_statistics(image)
    assert set(st) >= {"min_side", "band_energy_fraction", "flat_fraction"}
    s, info = recommended_strength(image, 1.0)
    assert s > 0 and info["factor"] in (1.0, 1.5, 2.0)
    small = image[:400, :400]
    s_small, info_small = recommended_strength(small, 1.0)
    assert s_small >= 2.0 and info_small["min_side"] == 400
    flat = np.full((800, 800, 3), 0.5)
    flat[:, :, 0] = np.linspace(0.2, 0.8, 800)[None, :]
    s_flat, info_flat = recommended_strength(flat, 1.0)
    assert s_flat == pytest.approx(1.0) and info_flat["flat_fraction"] > 0.9
    rng = np.random.default_rng(0)
    tex = np.clip(0.5 + 0.2 * rng.standard_normal((800, 800, 3)), 0, 1)
    assert recommended_strength(tex, 1.0)[0] == pytest.approx(1.5)


def test_perceptual_mask_does_not_halo_into_flat_regions():
    from durable_watermark.core import _perceptual_mask

    y = np.full((512, 512), 0.5)
    rng = np.random.default_rng(3)
    y[:, :200] += rng.normal(0, 0.15, (512, 200))     # textured left half
    m = _perceptual_mask(np.clip(y, 0, 1))
    assert m[:, 240:].max() < m[:, :150].mean() * 0.6  # flat side stays well below the textured side
    assert m[:, 300:].max() <= m[:, 300:].min() + 0.05  # and is uniform 100 px from the edge


def test_enforce_pins_key_schedule_params(monkeypatch, tmp_path):
    monkeypatch.setenv(keys.ENV_ENFORCE, "1")
    monkeypatch.setenv(keys.ENV_SECRET, "server")
    monkeypatch.setenv("COMFYUI_WATERMARK_PAYLOAD_BITS", "64")
    monkeypatch.setenv("COMFYUI_WATERMARK_R_MAX", "0.30")
    monkeypatch.setenv("COMFYUI_WATERMARK_PAYLOAD_LOW_BITS", "16")
    monkeypatch.setattr(keys, "CONFIG_JSON", str(tmp_path / "nope.json"))
    r = keys.resolve("typed-secret", "0xABCD", 0.5)
    assert r.enforced and r.secret == "server" and r.params == {"payload_bits": 64, "r_max": 0.30}
    assert r.payload_low_bits == 16


def test_workflow_redaction_helpers():
    prompt = {"1": {"class_type": "DurableWatermarkKey", "inputs": {"secret": "hunter2"}},
              "2": {"class_type": "C2PASaveImage", "inputs": {"private_passphrase": "env:PP"}}}
    assert keys.sensitive_literals(prompt) == {"hunter2"}
    extra = {"workflow": {"nodes": [{"type": "DurableWatermarkKey", "widgets_values": ["hunter2", "acme"]}]}, "note": "hunter2"}
    out = keys.redact_extra_pnginfo(extra, prompt)
    assert out["workflow"]["nodes"][0]["widgets_values"] == ["<redacted>", "acme"] and out["note"] == "<redacted>"


def test_upscale_beyond_2x_is_detected(image, marked, cfg):
    """Regression: the fine-grid ring guard used to reject every ring above 2x upscale."""
    from PIL import Image
    pil = Image.fromarray((quantize(marked) * 255).astype(np.uint8))
    big = pil.resize((int(pil.width * 2.6), int(pil.height * 2.6)), Image.LANCZOS)
    res = detect(np.asarray(big, dtype=np.float64) / 255.0, cfg)
    assert res.detected and abs(res.scale - 2.6) < 0.1
