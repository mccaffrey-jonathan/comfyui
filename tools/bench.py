# SPDX-License-Identifier: Apache-2.0
import os, sys, time, io, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance, ImageOps
from durable_watermark.core import WatermarkConfig, embed, detect

def pil2np(im): return np.asarray(im.convert("RGB"), dtype=np.float64) / 255.0
def np2pil(a): return Image.fromarray(np.clip(a * 255 + 0.5, 0, 255).astype(np.uint8))

def psnr(a, b):
    mse = np.mean((a - b) ** 2)
    return 10 * math.log10(1.0 / mse) if mse > 0 else 99

def jpeg(im, q):
    b = io.BytesIO(); im.save(b, "JPEG", quality=q); b.seek(0); return Image.open(b).convert("RGB")

def hue_shift(im, deg):
    hsv = np.asarray(im.convert("HSV")).astype(np.int32)
    hsv[..., 0] = (hsv[..., 0] + int(deg / 360 * 255)) % 256
    return Image.fromarray(hsv.astype(np.uint8), "HSV").convert("RGB")

def noise(im, sigma):
    a = pil2np(im) + np.random.default_rng(0).normal(0, sigma / 255, pil2np(im).shape)
    return np2pil(a)

def crop_center(im, frac):
    w, h = im.size; cw, ch = int(w * frac), int(h * frac)
    x0, y0 = (w - cw) // 2, (h - ch) // 2
    return im.crop((x0, y0, x0 + cw, y0 + ch))

def gamma(im, g):
    return np2pil(pil2np(im) ** g)

def synth_images():
    rng = np.random.default_rng(1)
    H = W = 640
    # flat-ish: gradient + shapes
    yy, xx = np.mgrid[0:H, 0:W] / H
    flat = np.stack([0.2 + 0.6 * xx, 0.3 + 0.4 * yy, 0.5 + 0.0 * xx], -1)
    flat[200:400, 150:450] = [0.9, 0.2, 0.2]
    # 1/f texture
    f = np.fft.fftfreq(H)[:, None] ** 2 + np.fft.fftfreq(W)[None, :] ** 2
    spec = (rng.standard_normal((H, W)) + 1j * rng.standard_normal((H, W))) / np.maximum(np.sqrt(f), 1e-3)
    tex = np.real(np.fft.ifft2(spec)); tex = (tex - tex.min()) / (tex.max() - tex.min())
    pink = np.stack([tex, tex ** 1.5, 1 - tex], -1)
    return {"flat": flat, "pink": pink}

TRANSFORMS = {
    "identity": lambda im: im,
    "png8bit": lambda im: im,
    "jpeg90": lambda im: jpeg(im, 90),
    "jpeg75": lambda im: jpeg(im, 75),
    "jpeg50": lambda im: jpeg(im, 50),
    "resize0.5": lambda im: im.resize((im.width // 2, im.height // 2), Image.LANCZOS),
    "resize0.75": lambda im: im.resize((int(im.width * .75), int(im.height * .75)), Image.BICUBIC),
    "resize1.5": lambda im: im.resize((int(im.width * 1.5), int(im.height * 1.5)), Image.BICUBIC),
    "rot90": lambda im: im.rotate(90, expand=True),
    "rot7_expand": lambda im: im.rotate(7, resample=Image.BICUBIC, expand=True),
    "rot30_crop": lambda im: im.rotate(30, resample=Image.BICUBIC, expand=False),
    "rot30_expand": lambda im: im.rotate(30, resample=Image.BICUBIC, expand=True),
    "flipH": lambda im: ImageOps.mirror(im),
    "crop50%area": lambda im: crop_center(im, 0.71),
    "crop25%area": lambda im: crop_center(im, 0.5),
    "hue+60": lambda im: hue_shift(im, 60),
    "grayscale": lambda im: im.convert("L").convert("RGB"),
    "bright1.3": lambda im: ImageEnhance.Brightness(im).enhance(1.3),
    "contrast0.7": lambda im: ImageEnhance.Contrast(im).enhance(0.7),
    "gamma0.6": lambda im: gamma(im, 0.6),
    "sat2.0": lambda im: ImageEnhance.Color(im).enhance(2.0),
    "noise5": lambda im: noise(im, 5),
    "blur1": lambda im: im.filter(ImageFilter.GaussianBlur(1.0)),
    "sharpen": lambda im: im.filter(ImageFilter.SHARPEN),
    "combo(rot15+resize0.8+jpeg75)": lambda im: jpeg(im.rotate(15, resample=Image.BICUBIC, expand=True).resize((int(im.width * .8), int(im.height * .8)), Image.BICUBIC), 75),
    "aspect(1.2x,1.0y)": lambda im: im.resize((int(im.width * 1.2), im.height), Image.BICUBIC),
}

def run(images, cfg, payload, names=None, verbose=True):
    rows = []
    for iname, arr in images.items():
        t0 = time.time(); marked = embed(arr, cfg, payload); te = time.time() - t0
        p = psnr(arr, marked)
        im = np2pil(marked)
        res0 = detect(pil2np(np2pil(arr)), cfg, expected_payload=payload)
        if verbose: print(f"\n== {iname} {arr.shape[1]}x{arr.shape[0]}  PSNR={p:.1f}dB  embed={te:.2f}s  unmarked z={res0.z_score:.2f} crc={res0.crc_ok}")
        for tname, fn in TRANSFORMS.items():
            if names and tname not in names: continue
            t = fn(im)
            t0 = time.time()
            r = detect(pil2np(t), cfg, expected_payload=payload, aspect_search=tname.startswith("aspect"))
            td = time.time() - t0
            ok = "OK " if r.expected_match else ("det" if r.detected else "-- ")
            rows.append((iname, tname, r.z_score, r.expected_match))
            if verbose: print(f"  {ok} {tname:32s} z={r.z_score:6.2f} crc={int(r.crc_ok)} scale={r.scale:.3f} rot={r.rotation_deg:.0f}{'F' if r.flipped else ''} bitconf={r.bit_confidence:.2f} used={r.n_bins_used} {td:.2f}s")
    return rows

if __name__ == "__main__":
    images = {"example": pil2np(Image.open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "input", "example.png")))}
    images.update(synth_images())
    strength = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
    bits = int(sys.argv[2]) if len(sys.argv) > 2 else 32
    cfg = WatermarkConfig(secret="correct horse battery staple", payload_bits=bits, strength=strength)
    payload = 0xC0FFEE42 & ((1 << bits) - 1) if bits else 0
    rows = run(images, cfg, payload)
    n = len(rows); ok = sum(1 for r in rows if r[3])
    print(f"\nTOTAL payload-correct: {ok}/{n}")
