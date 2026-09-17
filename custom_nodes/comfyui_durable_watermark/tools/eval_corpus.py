# SPDX-License-Identifier: Apache-2.0
"""Image-quality and reliability evaluation of the RingMark watermark over an image corpus.

    python tools/eval_corpus.py --images corpus/sdxl --out results.json --workers 4

For every image the harness measures, per condition (strength x key):
  * fidelity of the marked 8-bit image: PSNR, luma SSIM, MS-SSIM, mean/max abs
    residual, flat-region residual (max, p99.9, mean in the flattest 5 % of
    32x32 blocks), chroma drift;
  * detection z / payload correctness after every transform in TRANSFORMS;
  * key mismatch: z of the marked image under wrong keys;
  * false positives: z of the *unmarked* image (raw and JPEG-75) under the keys;
  * zero-bit and 64-bit modes on a transform subset.

Results are written as one JSON document (see `summarise()` for the roll-up
that the report tooling consumes).  Multiprocessing is per image; each worker
pins BLAS/FFT to one thread.
"""
import argparse, io, json, math, os, sys, time, hashlib
os.environ.setdefault("OMP_NUM_THREADS", "1"); os.environ.setdefault("OPENBLAS_NUM_THREADS", "1"); os.environ.setdefault("MKL_NUM_THREADS", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance, ImageOps
from scipy.ndimage import uniform_filter
from durable_watermark.core import WatermarkConfig, embed, detect, image_statistics, recommended_strength

# --------------------------------------------------------------------------- helpers
def pil2np(im): return np.asarray(im.convert("RGB"), dtype=np.float64) / 255.0
def np2pil(a): return Image.fromarray(np.clip(a * 255 + 0.5, 0, 255).astype(np.uint8))
def luma(a): return 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]

def psnr(a, b):
    mse = float(np.mean((a - b) ** 2)); return 10 * math.log10(1.0 / mse) if mse > 0 else 99.0

def ssim(A, B, win=7):
    mu_a, mu_b = uniform_filter(A, win), uniform_filter(B, win)
    va = uniform_filter(A * A, win) - mu_a ** 2; vb = uniform_filter(B * B, win) - mu_b ** 2
    vab = uniform_filter(A * B, win) - mu_a * mu_b
    c1, c2 = 0.01 ** 2, 0.03 ** 2
    m = ((2 * mu_a * mu_b + c1) * (2 * vab + c2)) / ((mu_a ** 2 + mu_b ** 2 + c1) * (va + vb + c2))
    return m, (2 * vab + c2) / (va + vb + c2)

def ms_ssim(A, B, weights=(0.0448, 0.2856, 0.3001, 0.2363, 0.1333)):
    vals = []
    for i, w in enumerate(weights):
        m, cs = ssim(A, B, 11)
        vals.append(float(np.mean(m)) if i == len(weights) - 1 else float(np.mean(cs)))
        if i < len(weights) - 1:
            if min(A.shape) < 32: break
            A = uniform_filter(A, 2)[::2, ::2]; B = uniform_filter(B, 2)[::2, ::2]
    ws = weights[:len(vals)]
    return float(np.prod([max(v, 1e-6) ** w for v, w in zip(vals, ws)]))

def fidelity(orig8, marked8):
    """orig8/marked8: uint8 RGB arrays."""
    a, b = orig8.astype(np.float64) / 255, marked8.astype(np.float64) / 255
    ya, yb = luma(a), luma(b)
    d = np.abs(orig8.astype(np.int16) - marked8.astype(np.int16))
    dl = np.abs(np.round(ya * 255) - np.round(yb * 255))
    # flattest 5 % of 32x32 blocks by luma std
    H, W = ya.shape; bs = 32
    hh, ww = H // bs, W // bs
    blocks = ya[:hh * bs, :ww * bs].reshape(hh, bs, ww, bs).std(axis=(1, 3))
    dblocks = dl[:hh * bs, :ww * bs].reshape(hh, bs, ww, bs).transpose(0, 2, 1, 3)
    thr = np.quantile(blocks, 0.05)
    flat = dblocks[blocks <= thr]
    chroma = np.abs((orig8[..., 0].astype(np.int16) - orig8[..., 1]) - (marked8[..., 0].astype(np.int16) - marked8[..., 1]))
    return dict(psnr=round(psnr(a, b), 3), ssim_luma=round(float(np.mean(ssim(ya, yb)[0])), 5),
                msssim=round(ms_ssim(ya, yb), 5), mean_abs=round(float(d.mean()), 3), max_abs=int(d.max()),
                frac_ge4=round(float((d.max(-1) >= 4).mean()), 4),
                flat_max=int(flat.max()) if flat.size else 0, flat_mean=round(float(flat.mean()), 3) if flat.size else 0.0,
                flat_p999=float(np.quantile(flat, 0.999)) if flat.size else 0.0, chroma_dev_max=int(chroma.max()))

def jpeg(im, q):
    b = io.BytesIO(); im.save(b, "JPEG", quality=q); b.seek(0); return Image.open(b).convert("RGB")
def webp(im, q):
    b = io.BytesIO(); im.save(b, "WEBP", quality=q); b.seek(0); return Image.open(b).convert("RGB")
def hue_shift(im, deg):
    hsv = np.asarray(im.convert("HSV")).astype(np.int32); hsv[..., 0] = (hsv[..., 0] + int(deg / 360 * 255)) % 256
    return Image.fromarray(hsv.astype(np.uint8), "HSV").convert("RGB")
def noise(im, sigma, seed=0):
    a = pil2np(im); return np2pil(a + np.random.default_rng(seed).normal(0, sigma / 255, a.shape))
def crop_center(im, frac):
    w, h = im.size; cw, ch = int(w * frac), int(h * frac); x0, y0 = (w - cw) // 2, (h - ch) // 2
    return im.crop((x0, y0, x0 + cw, y0 + ch))
def crop_corner(im, frac):
    w, h = im.size; return im.crop((0, 0, int(w * frac), int(h * frac)))
def resize(im, f, rs=Image.BICUBIC): return im.resize((max(32, int(im.width * f)), max(32, int(im.height * f))), rs)
def gamma(im, g): return np2pil(pil2np(im) ** g)
def social(im):
    f = 1080 / max(im.size); return jpeg(resize(im, f, Image.LANCZOS), 80)
def screenshot(im):
    t = resize(im, 0.9, Image.BILINEAR); return jpeg(crop_center(t, 0.95), 85)
def pad_border(im, px=48):
    return ImageOps.expand(im, border=px, fill=(255, 255, 255))
def overlay_text(im):
    from PIL import ImageDraw
    t = im.copy(); d = ImageDraw.Draw(t)
    for y in range(20, t.height, 120): d.text((20, y), "SAMPLE TEXT OVERLAY  1234567890", fill=(255, 255, 255))
    return t

TRANSFORMS = {
    "identity": lambda im: im,
    "jpeg90": lambda im: jpeg(im, 90), "jpeg75": lambda im: jpeg(im, 75), "jpeg60": lambda im: jpeg(im, 60), "jpeg40": lambda im: jpeg(im, 40),
    "webp80": lambda im: webp(im, 80), "webp60": lambda im: webp(im, 60),
    "double_jpeg85_70": lambda im: jpeg(jpeg(im, 85), 70),
    "resize0.5": lambda im: resize(im, 0.5, Image.LANCZOS), "resize0.75": lambda im: resize(im, 0.75),
    "resize1.5": lambda im: resize(im, 1.5), "resize0.35": lambda im: resize(im, 0.35, Image.LANCZOS),
    "rot5_expand": lambda im: im.rotate(5, resample=Image.BICUBIC, expand=True),
    "rot15_expand": lambda im: im.rotate(15, resample=Image.BICUBIC, expand=True),
    "rot45_expand": lambda im: im.rotate(45, resample=Image.BICUBIC, expand=True),
    "rot30_crop": lambda im: im.rotate(30, resample=Image.BICUBIC, expand=False),
    "rot90": lambda im: im.rotate(90, expand=True), "flipH": lambda im: ImageOps.mirror(im),
    "crop50%area": lambda im: crop_center(im, 0.71), "crop25%area": lambda im: crop_center(im, 0.5),
    "crop_corner60%": lambda im: crop_corner(im, 0.6),
    "hue+60": lambda im: hue_shift(im, 60), "grayscale": lambda im: im.convert("L").convert("RGB"),
    "bright1.3": lambda im: ImageEnhance.Brightness(im).enhance(1.3), "contrast0.7": lambda im: ImageEnhance.Contrast(im).enhance(0.7),
    "gamma0.6": lambda im: gamma(im, 0.6), "sat2.0": lambda im: ImageEnhance.Color(im).enhance(2.0),
    "noise5": lambda im: noise(im, 5), "noise10": lambda im: noise(im, 10),
    "blur1": lambda im: im.filter(ImageFilter.GaussianBlur(1.0)), "median3": lambda im: im.filter(ImageFilter.MedianFilter(3)),
    "sharpen": lambda im: im.filter(ImageFilter.SHARPEN), "unsharp": lambda im: im.filter(ImageFilter.UnsharpMask(2, 150, 3)),
    "pad_border48": pad_border, "text_overlay": overlay_text,
    "social(1080+jpeg80)": social, "screenshot(0.9+crop+jpeg85)": screenshot,
    "combo(rot15+resize0.8+jpeg75)": lambda im: jpeg(resize(im.rotate(15, resample=Image.BICUBIC, expand=True), 0.8), 75),
    "aspect(1.2x,1.0y)": lambda im: im.resize((int(im.width * 1.2), im.height), Image.BICUBIC),
}
CORE_SUBSET = ["identity", "jpeg75", "jpeg60", "webp80", "resize0.5", "rot15_expand", "rot45_expand", "flipH",
               "crop50%area", "crop25%area", "hue+60", "noise5", "blur1", "social(1080+jpeg80)", "combo(rot15+resize0.8+jpeg75)"]
ZERO_BIT_SUBSET = ["identity", "jpeg60", "jpeg40", "resize0.5", "resize0.35", "rot15_expand", "crop25%area", "noise10", "combo(rot15+resize0.8+jpeg75)"]
BITS64_SUBSET = ["identity", "jpeg75", "jpeg60", "resize0.5", "rot15_expand", "crop50%area", "social(1080+jpeg80)", "combo(rot15+resize0.8+jpeg75)"]

def key_secret(i): return f"corpus-eval-2026::site-key-{i:02d}"
def payload_for(image_id, key_i, bits):
    h = hashlib.sha256(f"{image_id}|{key_i}".encode()).digest()
    return int.from_bytes(h[:8], "little") & ((1 << bits) - 1) if bits else 0

def run_detect(im_pil, cfg, payload, name):
    t0 = time.time()
    r = detect(pil2np(im_pil), cfg, expected_payload=payload if cfg.payload_bits else None, aspect_search=name.startswith("aspect"))
    return dict(transform=name, z=round(r.z_score, 2), p=float(f"{r.p_value:.3g}"), detected=bool(r.detected), crc_ok=bool(r.crc_ok),
                payload_ok=bool(r.expected_match) if cfg.payload_bits else None, scale=round(r.scale, 3),
                rot=round(r.rotation_deg, 1), flipped=bool(r.flipped), bit_conf=round(r.bit_confidence, 2), seconds=round(time.time() - t0, 2))

def eval_image(task):
    path, image_id, meta, opts = task
    t_start = time.time()
    im = Image.open(path).convert("RGB")
    orig_size = im.size
    if max(im.size) > opts["max_side"]:
        f = opts["max_side"] / max(im.size); im = resize(im, f, Image.LANCZOS)
    orig8 = np.asarray(im, dtype=np.uint8); img = orig8.astype(np.float64) / 255
    out = dict(image=image_id, meta=meta, orig_size=list(orig_size), size=list(im.size), stats={k: round(float(v), 5) for k, v in image_statistics(img).items()},
               conditions=[], key_mismatch=[], unmarked=[], zero_bit=[], bits64=[])
    rec_strength, _ = recommended_strength(img, 1.0)
    conds = [("s1.0", 1.0, k, TRANSFORMS if k == 0 else CORE_SUBSET) for k in range(opts["keys"])]
    conds += [("s1.5", 1.5, 0, TRANSFORMS), ("adaptive", rec_strength, 0, TRANSFORMS)]
    marked_ref = None
    for label, strength, k, names in conds:
        cfg = WatermarkConfig(secret=key_secret(k), strength=strength, payload_bits=32)
        payload = payload_for(image_id, k, 32)
        t0 = time.time(); m = embed(img, cfg, payload); te = time.time() - t0
        mp = np2pil(m); m8 = np.asarray(mp)
        if label == "s1.0" and k == 0: marked_ref = mp
        row = dict(label=label, strength=round(strength, 3), key=k, payload_hex=f"{payload:08x}", embed_s=round(te, 2),
                   fidelity=fidelity(orig8, m8), detections=[])
        for name in names:
            row["detections"].append(run_detect(TRANSFORMS[name](mp), cfg, payload, name))
        out["conditions"].append(row)
    # key mismatch: the s1.0/key0 marked image under wrong keys (raw and jpeg75)
    for k in range(opts["keys"], opts["keys"] + 2):
        cfg = WatermarkConfig(secret=key_secret(k), strength=1.0, payload_bits=32)
        for name in ("identity", "jpeg75"):
            d = run_detect(TRANSFORMS[name](marked_ref), cfg, None, name); d["wrong_key"] = k; out["key_mismatch"].append(d)
    # false positives on the unmarked image under the real keys
    for k in range(opts["keys"]):
        cfg = WatermarkConfig(secret=key_secret(k), strength=1.0, payload_bits=32)
        for name in ("identity", "jpeg75", "resize0.5"):
            d = run_detect(TRANSFORMS[name](im), cfg, None, name); d["key"] = k; out["unmarked"].append(d)
    # zero-bit mode
    cfg = WatermarkConfig(secret=key_secret(0), strength=1.0, payload_bits=0)
    m = np2pil(embed(img, cfg, 0)); fz = fidelity(orig8, np.asarray(m))
    out["zero_bit"] = dict(fidelity=fz, detections=[run_detect(TRANSFORMS[n](m), cfg, None, n) for n in ZERO_BIT_SUBSET],
                           unmarked_z=run_detect(im, cfg, None, "identity")["z"])
    # 64-bit mode
    cfg = WatermarkConfig(secret=key_secret(0), strength=1.0, payload_bits=64); p64 = payload_for(image_id, 0, 64)
    m = np2pil(embed(img, cfg, p64)); f64 = fidelity(orig8, np.asarray(m))
    out["bits64"] = dict(fidelity=f64, payload_hex=f"{p64:016x}", detections=[run_detect(TRANSFORMS[n](m), cfg, p64, n) for n in BITS64_SUBSET])
    out["seconds"] = round(time.time() - t_start, 1)
    return out

def summarise(results):
    """Roll-up used by the report: per-condition fidelity medians and per-transform payload rates."""
    import collections
    S = dict(n_images=len(results), fidelity={}, robustness={}, key_mismatch={}, unmarked={}, zero_bit={}, bits64={})
    fid = collections.defaultdict(lambda: collections.defaultdict(list)); rob = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in results:
        for c in r["conditions"]:
            lab = c["label"] if c["key"] == 0 else f"{c['label']}/key{c['key']}"
            for k, v in c["fidelity"].items(): fid[lab][k].append(v)
            for d in c["detections"]: rob[lab][d["transform"]].append((d["z"], d["detected"], d["payload_ok"]))
    for lab, m in fid.items():
        S["fidelity"][lab] = {k: dict(median=round(float(np.median(v)), 3), min=round(float(np.min(v)), 3), max=round(float(np.max(v)), 3), p10=round(float(np.quantile(v, .1)), 3), p90=round(float(np.quantile(v, .9)), 3)) for k, v in m.items()}
    for lab, m in rob.items():
        S["robustness"][lab] = {t: dict(n=len(v), payload_rate=round(sum(1 for z, d, p in v if p) / len(v), 4), detect_rate=round(sum(1 for z, d, p in v if d) / len(v), 4),
                                        z_median=round(float(np.median([z for z, _, _ in v])), 2), z_min=round(float(min(z for z, _, _ in v)), 2), z_p10=round(float(np.quantile([z for z, _, _ in v], .1)), 2)) for t, v in m.items()}
    km = [d["z"] for r in results for d in r["key_mismatch"]]; un = [d["z"] for r in results for d in r["unmarked"]]
    S["key_mismatch"] = dict(n=len(km), z_max=round(max(km), 2), z_mean=round(float(np.mean(km)), 3), z_std=round(float(np.std(km)), 3), false_alarms=sum(1 for z in km if z >= 5), crc_pass=sum(1 for r in results for d in r["key_mismatch"] if d["crc_ok"]))
    S["unmarked"] = dict(n=len(un), z_max=round(max(un), 2), z_mean=round(float(np.mean(un)), 3), z_std=round(float(np.std(un)), 3), false_alarms=sum(1 for z in un if z >= 5), crc_pass=sum(1 for r in results for d in r["unmarked"] if d["crc_ok"]))
    zb = collections.defaultdict(list); b64 = collections.defaultdict(list)
    for r in results:
        for d in r["zero_bit"]["detections"]: zb[d["transform"]].append((d["z"], d["detected"]))
        for d in r["bits64"]["detections"]: b64[d["transform"]].append((d["z"], d["payload_ok"]))
    S["zero_bit"] = {t: dict(n=len(v), detect_rate=round(sum(1 for _, d in v if d) / len(v), 4), z_median=round(float(np.median([z for z, _ in v])), 2), z_min=round(float(min(z for z, _ in v)), 2)) for t, v in zb.items()}
    S["zero_bit"]["unmarked_z_max"] = round(max(r["zero_bit"]["unmarked_z"] for r in results), 2)
    S["zero_bit"]["fidelity_psnr_median"] = round(float(np.median([r["zero_bit"]["fidelity"]["psnr"] for r in results])), 2)
    S["bits64"] = {t: dict(n=len(v), payload_rate=round(sum(1 for _, p in v if p) / len(v), 4), z_median=round(float(np.median([z for z, _ in v])), 2)) for t, v in b64.items()}
    S["bits64"]["fidelity_psnr_median"] = round(float(np.median([r["bits64"]["fidelity"]["psnr"] for r in results])), 2)
    return S

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--images", required=True, help="directory of images (optionally with manifest.json)")
    ap.add_argument("--out", required=True); ap.add_argument("--workers", type=int, default=max(1, os.cpu_count() or 1))
    ap.add_argument("--keys", type=int, default=3); ap.add_argument("--max-side", type=int, default=1024)
    ap.add_argument("--limit", type=int, default=0); ap.add_argument("--min-side", type=int, default=256)
    a = ap.parse_args()
    mpath = os.path.join(a.images, "manifest.json")
    manifest = json.load(open(mpath)) if os.path.exists(mpath) else None
    if manifest:
        files = [(os.path.join(a.images, m["file"]), m.get("id") or m["file"], {k: v for k, v in m.items() if k not in ("prompt",)}) for m in manifest]
    else:
        files = [(os.path.join(a.images, f), f, {}) for f in sorted(os.listdir(a.images)) if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
    files = [f for f in files if min(Image.open(f[0]).size) >= a.min_side]
    if a.limit: files = files[:a.limit]
    opts = dict(keys=a.keys, max_side=a.max_side)
    tasks = [(p, i, m, opts) for p, i, m in files]
    results = []; t0 = time.time()
    partial = a.out + ".partial"
    if os.path.exists(partial):
        results = json.load(open(partial)); done = {r["image"] for r in results}; tasks = [t for t in tasks if t[1] not in done]
        print(f"resuming: {len(results)} done, {len(tasks)} to go")
    if a.workers > 1 and len(tasks) > 1:
        import multiprocessing as mp
        with mp.get_context("fork").Pool(a.workers) as pool:
            for r in pool.imap_unordered(eval_image, tasks):
                results.append(r); json.dump(results, open(partial, "w"))
                print(f"[{len(results):3d}/{len(files)}] {r['image']} {r['size']} {r['seconds']}s  elapsed {time.time() - t0:.0f}s", flush=True)
    else:
        for t in tasks:
            r = eval_image(t); results.append(r); json.dump(results, open(partial, "w"))
            print(f"[{len(results):3d}/{len(files)}] {r['image']} {r['size']} {r['seconds']}s", flush=True)
    results.sort(key=lambda r: r["image"])
    doc = dict(meta=dict(scheme="org.comfyui.ringmark.v1", date=time.strftime("%Y-%m-%d"), images_dir=os.path.abspath(a.images), n_images=len(results),
                         keys=a.keys, max_side=a.max_side, transforms=list(TRANSFORMS), core_subset=CORE_SUBSET, zero_bit_subset=ZERO_BIT_SUBSET,
                         bits64_subset=BITS64_SUBSET, z_threshold=5.0, payload_bits=32, wall_seconds=round(time.time() - t0, 1)),
               summary=summarise(results), images=results)
    json.dump(doc, open(a.out, "w"), indent=1)
    if os.path.exists(partial): os.remove(partial)
    print("saved", a.out)

if __name__ == "__main__":
    main()
