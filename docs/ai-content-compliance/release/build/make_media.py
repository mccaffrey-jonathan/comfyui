"""Produce the release-page media by running the node classes inside ComfyUI (CPU)."""
import base64, io, json, os, sys
os.environ["COMFYUI_WATERMARK_SECRET"] = "release-demo-secret"
sys.argv = ["main.py", "--cpu"]
sys.path.insert(0, "/home/user/comfyui")
import comfy.options; comfy.options.enable_args_parsing()
import asyncio, numpy as np, torch
from PIL import Image, ImageFilter, ImageEnhance, ImageOps
import nodes
asyncio.run(nodes.init_external_custom_nodes())
M = nodes.NODE_CLASS_MAPPINGS
sys.path.insert(0, "/home/user/comfyui/custom_nodes/comfyui_durable_watermark")
from durable_watermark.core import to_luma, WatermarkConfig, KeySchedule

OUT = "/tmp/claude-0/-home-user-comfyui/8eea5e5d-bdca-5080-a9f8-da0d41580005/scratchpad/media"
os.makedirs(OUT, exist_ok=True)
media = {}

def to_data_uri(pil, fmt="WEBP", quality=82, max_side=640):
    im = pil.copy()
    if max(im.size) > max_side:
        im.thumbnail((max_side, max_side), Image.LANCZOS)
    b = io.BytesIO(); im.save(b, fmt, quality=quality) if fmt != "PNG" else im.save(b, "PNG", optimize=True)
    mime = {"WEBP": "image/webp", "PNG": "image/png", "JPEG": "image/jpeg"}[fmt]
    return f"data:{mime};base64," + base64.b64encode(b.getvalue()).decode()

def t2pil(t): return Image.fromarray(np.clip(t[0].numpy() * 255 + 0.5, 0, 255).astype(np.uint8))
def pil2t(im): return torch.from_numpy(np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0)[None]

src = Image.open("/home/user/comfyui/input/example.png").convert("RGB")
img = pil2t(src)
Key, Emb, Det = M["DurableWatermarkKey"], M["DurableWatermarkEmbed"], M["DurableWatermarkDetect"]
key = Key.execute("env:COMFYUI_WATERMARK_SECRET", "acme-image-studio", 32, 1.0).args[0]
marked_t, payload_hex, record = Emb.execute(img, key).args
marked = t2pil(marked_t)
media["original"] = to_data_uri(src)
media["marked"] = to_data_uri(marked)
media["original_png"] = to_data_uri(src, "PNG", max_side=768)
media["marked_png"] = to_data_uri(marked, "PNG", max_side=768)
media["payload_hex"] = payload_hex
media["record"] = json.loads(record)
# zoom crops (2x) of a textured region
box = (300, 200, 428, 328)
media["zoom_original"] = to_data_uri(src.crop(box).resize((384, 384), Image.NEAREST), "PNG")
media["zoom_marked"] = to_data_uri(marked.crop(box).resize((384, 384), Image.NEAREST), "PNG")
# amplified difference map
d = (np.asarray(marked, dtype=np.float32) - np.asarray(src, dtype=np.float32)).mean(axis=-1)
amp = np.clip(128 + d * 24, 0, 255).astype(np.uint8)
media["diff"] = to_data_uri(Image.fromarray(amp), "PNG")
media["diff_stats"] = {"mean_abs_delta_8bit": float(np.abs(d).mean()), "max_abs_delta_8bit": float(np.abs(d).max()),
                       "psnr": float(10 * np.log10(255 ** 2 / np.mean(d ** 2)))}
# spectra: log magnitude (shifted) of luminance for original, marked, and ratio marked/original (rings)
def logspec(im):
    y = to_luma(np.asarray(im, dtype=np.float64) / 255.0); y = y - y.mean()
    F = np.fft.fftshift(np.fft.fft2(y)); return np.log(np.abs(F) ** 2 + 1e-6)
So, Sm = logspec(src), logspec(marked)
def norm(a, lo=None, hi=None):
    lo = np.percentile(a, 1) if lo is None else lo; hi = np.percentile(a, 99.5) if hi is None else hi
    return Image.fromarray(np.clip((a - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8))
media["spec_original"] = to_data_uri(norm(So), "PNG", max_side=512)
media["spec_marked"] = to_data_uri(norm(Sm), "PNG", max_side=512)
ratio = Sm - So
# smooth the ratio angularly a little for display: show the ring band clearly
media["spec_ratio"] = to_data_uri(norm(ratio, -0.6, 0.6), "PNG", max_side=512)
# ring layout of the key (which radii carry which chips) for an explanatory figure
cfg = WatermarkConfig(**key["config"]); ks = KeySchedule.from_config(cfg)
media["key_layout"] = {"n_rings": int(ks.n_bins), "n_harm": int(ks.n_harm), "n_chips": int(ks.n_chips),
                       "n_sync": int((ks.roles < 0).sum()), "n_payload": int((ks.roles >= 0).sum()),
                       "r_min": cfg.r_min, "r_max": cfg.r_max, "ring_width": cfg.ring_width,
                       "groups": [int(len(g)) for g in ks.group_chips], "radial": [int(x) for x in ks.radial[:20]]}

# transforms with detection reports
def jpeg(im, q):
    b = io.BytesIO(); im.save(b, "JPEG", quality=q); b.seek(0); return Image.open(b).convert("RGB")
def hue_shift(im, deg):
    hsv = np.asarray(im.convert("HSV")).astype(np.int32); hsv[..., 0] = (hsv[..., 0] + int(deg / 360 * 255)) % 256
    return Image.fromarray(hsv.astype(np.uint8), "HSV").convert("RGB")
w, h = marked.size
transforms = [
    ("Untouched PNG", marked),
    ("Rotated 30°, canvas expanded", marked.rotate(30, resample=Image.BICUBIC, expand=True)),
    ("Rotated 90°", marked.rotate(90, expand=True)),
    ("Mirrored", ImageOps.mirror(marked)),
    ("Centre crop, 40 % of area", marked.crop((int(w * .18), int(h * .18), int(w * .82), int(h * .82)))),
    ("Downscaled to 50 %", marked.resize((w // 2, h // 2), Image.LANCZOS)),
    ("JPEG quality 75", jpeg(marked, 75)),
    ("JPEG quality 50", jpeg(marked, 50)),
    ("Hue +60°, saturation ×1.6", ImageEnhance.Color(hue_shift(marked, 60)).enhance(1.6)),
    ("Grayscale, gamma 0.6", Image.fromarray((255 * (np.asarray(marked.convert("L"), dtype=np.float32) / 255) ** 0.6).astype(np.uint8)).convert("RGB")),
    ("Gaussian blur r=1, sharpened", marked.filter(ImageFilter.GaussianBlur(1.0)).filter(ImageFilter.SHARPEN)),
    ("Rot 15° + resize to 61 % + JPEG 75", jpeg(marked.rotate(15, resample=Image.BICUBIC, expand=True).resize((int(w * .8), int(h * .8)), Image.BICUBIC), 75)),
]
gallery = []
for name, im in transforms:
    r = Det.execute(pil2t(im), key)
    rep = json.loads(r.args[4])
    gallery.append({"name": name, "img": to_data_uri(im, max_side=360), "size": f"{im.width}×{im.height}",
                    "detected": bool(r.args[0]), "z": round(r.args[1], 1), "payload": r.args[2], "matches": bool(r.args[3]),
                    "scale": round(rep["scale"], 2), "rotation": round(rep["rotation_deg"], 1), "flipped": rep["flipped"],
                    "crc_ok": rep["crc_ok"]})
    print(name, r.args[:4])
media["gallery"] = gallery
r_un = Det.execute(img, key); media["unmarked_z"] = round(r_un.args[1], 2)
wrong = Key.execute("another-secret", "acme-image-studio", 32, 1.0).args[0]
r_wrong = Det.execute(marked_t, wrong); media["wrong_key_z"] = round(r_wrong.args[1], 2)

# C2PA: sign the marked image (PNG) with a test chain, read it back
Sg, Sv, Rd = M["C2PASigner"], M["C2PASaveImage"], M["C2PAReadManifest"]
signer = Sg.execute("", "", "es256", "none", True, "Acme Image Studio").args[0]
from comfy_api.latest._io import HiddenHolder
Sv.hidden = HiddenHolder.from_dict({"PROMPT": {"3": {"class_type": "KSampler", "inputs": {"seed": 4242, "steps": 28, "cfg": 3.5, "sampler_name": "euler"}},
                                               "9": {"class_type": "DurableWatermarkKey", "inputs": {"secret": "env:COMFYUI_WATERMARK_SECRET", "payload": "acme-image-studio"}}},
                                    "EXTRA_PNGINFO": {"workflow": {"nodes": [{"id": 3, "type": "KSampler"}], "links": []}}})
res = Sv.execute(marked_t, signer, "release_demo", "png", 95, "Acme Image Studio", "ComfyUI", "", "flux1-dev.safetensors",
                 "trainedAlgorithmicMedia", True, True, False, record, '{"tenant": "studio-7", "job": "batch-2026-09-13-0042"}',
                 "env:COMFYUI_WATERMARK_SECRET", True, None)
paths = json.loads(res.args[0]); manifest_def = json.loads(res.args[1])
rd = Rd.execute(paths[0]); summary = json.loads(rd.args[3]); store = json.loads(rd.args[4])
rd_t = Rd.execute(paths[0], "file:/home/user/comfyui/custom_nodes/comfyui_content_credentials/config/c2pa_test_root.pem")
media["c2pa"] = {"file": os.path.basename(paths[0]), "file_size": os.path.getsize(paths[0]),
                 "manifest_definition": manifest_def, "summary": summary, "store": store,
                 "state_untrusted_anchor": rd.args[2], "state_with_root": rd_t.args[2], "signer_info": signer["info"]}
Dc = M["C2PADecryptPrivateAssertion"]
media["c2pa"]["decrypted_private"] = json.loads(Dc.execute(rd.args[4], "env:COMFYUI_WATERMARK_SECRET").args[0])
# JPEG signed too, for size comparison
res_j = Sv.execute(marked_t, signer, "release_demo", "jpeg", 90, "Acme Image Studio", "ComfyUI", "", "flux1-dev.safetensors",
                   "trainedAlgorithmicMedia", True, True, False, record, "", "", False, None)
pj = json.loads(res_j.args[0])[0]
b = io.BytesIO(); marked.save(b, "JPEG", quality=90)
media["c2pa"]["jpeg_signed_size"] = os.path.getsize(pj); media["c2pa"]["jpeg_plain_size"] = b.tell()
b = io.BytesIO(); marked.save(b, "PNG", compress_level=4); media["c2pa"]["png_plain_size"] = b.tell()
json.dump(media, open(os.path.join(OUT, "media.json"), "w"))
print("media saved", os.path.join(OUT, "media.json"))
