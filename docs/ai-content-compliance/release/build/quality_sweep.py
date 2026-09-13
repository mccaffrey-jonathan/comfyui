"""Effect of image quality (JPEG/WebP quality, resolution, strength) on the watermark."""
import io, json, math, os, sys, time
sys.path.insert(0, "/home/user/comfyui/custom_nodes/comfyui_durable_watermark")
import numpy as np
from PIL import Image
from durable_watermark.core import WatermarkConfig, embed, detect
from bench import pil2np, np2pil, synth_images, psnr

OUT = "/tmp/claude-0/-home-user-comfyui/8eea5e5d-bdca-5080-a9f8-da0d41580005/scratchpad/quality_sweep.json"
PAYLOAD = 0xC0FFEE42
images = {"photo": pil2np(Image.open("/home/user/comfyui/input/example.png"))}
s = synth_images(); images["flat"] = s["flat"]; images["texture"] = s["pink"]

def codec(im, fmt, q):
    b = io.BytesIO(); im.save(b, fmt, quality=q); n = b.tell(); b.seek(0)
    return Image.open(b).convert("RGB"), n

def ssim_gray(a, b):
    # simple global-window SSIM on luminance (8x8 blocks mean)
    from scipy.ndimage import uniform_filter
    A = 0.299*a[...,0]+0.587*a[...,1]+0.114*a[...,2]; B = 0.299*b[...,0]+0.587*b[...,1]+0.114*b[...,2]
    mu_a, mu_b = uniform_filter(A, 7), uniform_filter(B, 7)
    va = uniform_filter(A*A, 7) - mu_a**2; vb = uniform_filter(B*B, 7) - mu_b**2; vab = uniform_filter(A*B, 7) - mu_a*mu_b
    c1, c2 = (0.01)**2, (0.03)**2
    return float(np.mean(((2*mu_a*mu_b + c1)*(2*vab + c2)) / ((mu_a**2 + mu_b**2 + c1)*(va + vb + c2))))

results = {"strength_quality": [], "jpeg": [], "webp": [], "resolution": []}
t0 = time.time()
# 1) Visual quality of the mark vs strength
for name, img in images.items():
    for st in (0.5, 0.75, 1.0, 1.5, 2.0):
        cfg = WatermarkConfig(secret="release-key", strength=st)
        m = embed(img, cfg, PAYLOAD)
        r = detect(pil2np(np2pil(m)), cfg, expected_payload=PAYLOAD)
        results["strength_quality"].append({"image": name, "strength": st, "psnr": round(psnr(img, m), 2),
                                            "ssim": round(ssim_gray(img, m), 4), "z": round(r.z_score, 1), "payload_ok": bool(r.expected_match)})
print("strength done", time.time() - t0)
# 2) JPEG / WebP quality sweep at strengths 1.0 and 1.5
for st in (1.0, 1.5):
    cfg = WatermarkConfig(secret="release-key", strength=st)
    for name, img in images.items():
        m = np2pil(embed(img, cfg, PAYLOAD))
        for fmt, key in (("JPEG", "jpeg"), ("WEBP", "webp")):
            for q in (100, 90, 80, 70, 60, 50, 40, 30, 20):
                t, nbytes = codec(m, fmt, q)
                r = detect(pil2np(t), cfg, expected_payload=PAYLOAD)
                results[key].append({"image": name, "strength": st, "quality": q, "bytes": nbytes, "bpp": round(8*nbytes/(t.width*t.height), 3),
                                     "z": round(r.z_score, 1), "detected": bool(r.detected), "payload_ok": bool(r.expected_match)})
        print(name, st, "codec done", time.time() - t0)
# 3) Resolution (downscale then optional JPEG 85)
for st in (1.0, 1.5):
    cfg = WatermarkConfig(secret="release-key", strength=st)
    for name, img in images.items():
        m = np2pil(embed(img, cfg, PAYLOAD))
        for f in (1.0, 0.8, 0.65, 0.5, 0.4, 0.3, 0.25):
            t = m.resize((max(64, int(m.width*f)), max(64, int(m.height*f))), Image.LANCZOS)
            r = detect(pil2np(t), cfg, expected_payload=PAYLOAD)
            tj, _ = codec(t, "JPEG", 85)
            rj = detect(pil2np(tj), cfg, expected_payload=PAYLOAD)
            results["resolution"].append({"image": name, "strength": st, "factor": f, "side": t.width,
                                          "z": round(r.z_score, 1), "payload_ok": bool(r.expected_match),
                                          "z_jpeg85": round(rj.z_score, 1), "payload_ok_jpeg85": bool(rj.expected_match)})
        print(name, st, "resolution done", time.time() - t0)
json.dump(results, open(OUT, "w"), indent=1)
print("saved", OUT)
