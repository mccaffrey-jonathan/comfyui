# SPDX-License-Identifier: Apache-2.0
"""Render the 100-prompt evaluation corpus through a running ComfyUI server.

The sandbox this pack was developed in has no GPU and cannot reach any model
host, so the corpus is rendered on the user's machine:

    python tools/corpus/generate_corpus.py --server http://127.0.0.1:8188 \
        --preset sdxl --checkpoint sd_xl_base_1.0.safetensors --out corpus/sdxl
    python tools/corpus/generate_corpus.py --preset flux --unet flux1-dev.safetensors \
        --clip1 clip_l.safetensors --clip2 t5xxl_fp16.safetensors --vae ae.safetensors --out corpus/flux
    python tools/corpus/generate_corpus.py --preset sd35 --checkpoint sd3.5_large.safetensors \
        --clip1 clip_l.safetensors --clip2 clip_g.safetensors --clip3 t5xxl_fp16.safetensors --out corpus/sd35

Then evaluate the renders with tools/eval_corpus.py.

Every prompt is submitted as an API-format workflow to POST /prompt, the history
is polled, and the first output image is fetched through GET /view and saved as
PNG (lossless) as <id>.png with a manifest.json next to it.  Seeds are fixed per
prompt so renders are reproducible for a given model.
"""
import argparse, json, os, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


def wf_sdxl(a, prompt, seed):
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": a.checkpoint}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": a.negative, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": a.width, "height": a.height, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": a.steps, "cfg": a.cfg, "sampler_name": a.sampler,
                                                    "scheduler": a.scheduler, "denoise": 1.0, "model": ["1", 0],
                                                    "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0]}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": a.prefix}},
    }


def wf_sd35(a, prompt, seed):
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": a.checkpoint}},
        "8": {"class_type": "TripleCLIPLoader", "inputs": {"clip_name1": a.clip1, "clip_name2": a.clip2, "clip_name3": a.clip3}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["8", 0]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": a.negative, "clip": ["8", 0]}},
        "4": {"class_type": "EmptySD3LatentImage", "inputs": {"width": a.width, "height": a.height, "batch_size": 1}},
        "9": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 3.0}},
        "5": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": a.steps, "cfg": a.cfg, "sampler_name": a.sampler,
                                                    "scheduler": a.scheduler, "denoise": 1.0, "model": ["9", 0],
                                                    "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0]}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": a.prefix}},
    }


def wf_flux(a, prompt, seed):
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": a.unet, "weight_dtype": "default"}},
        "8": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": a.clip1, "clip_name2": a.clip2, "type": "flux"}},
        "10": {"class_type": "VAELoader", "inputs": {"vae_name": a.vae}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["8", 0]}},
        "11": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["2", 0], "guidance": 3.5}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["8", 0]}},
        "4": {"class_type": "EmptySD3LatentImage", "inputs": {"width": a.width, "height": a.height, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": a.steps, "cfg": 1.0, "sampler_name": "euler",
                                                    "scheduler": "simple", "denoise": 1.0, "model": ["1", 0],
                                                    "positive": ["11", 0], "negative": ["3", 0], "latent_image": ["4", 0]}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["10", 0]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": a.prefix}},
    }


PRESETS = {"sdxl": wf_sdxl, "sd15": wf_sdxl, "sd35": wf_sd35, "flux": wf_flux}
DEFAULTS = {"sdxl": (1024, 1024, 25, 6.0), "sd15": (512, 512, 25, 7.0), "sd35": (1024, 1024, 28, 4.5), "flux": (1024, 1024, 20, 1.0)}


def api(server, path, data=None):
    req = urllib.request.Request(server + path, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def wait_for(server, prompt_id, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        hist = api(server, f"/history/{prompt_id}")
        if prompt_id in hist:
            h = hist[prompt_id]
            if h.get("status", {}).get("status_str") == "error":
                raise RuntimeError(json.dumps(h["status"].get("messages", []))[:2000])
            for node in h.get("outputs", {}).values():
                for im in node.get("images", []):
                    if im.get("type") == "output":
                        return im
        time.sleep(1.0)
    raise TimeoutError(prompt_id)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--server", default="http://127.0.0.1:8188")
    p.add_argument("--preset", choices=sorted(PRESETS), default="sdxl")
    p.add_argument("--checkpoint"); p.add_argument("--unet"); p.add_argument("--vae")
    p.add_argument("--clip1"); p.add_argument("--clip2"); p.add_argument("--clip3")
    p.add_argument("--prompts", default=os.path.join(HERE, "prompts.json"))
    p.add_argument("--out", required=True)
    p.add_argument("--width", type=int); p.add_argument("--height", type=int)
    p.add_argument("--steps", type=int); p.add_argument("--cfg", type=float)
    p.add_argument("--sampler", default="dpmpp_2m"); p.add_argument("--scheduler", default="karras")
    p.add_argument("--negative", default="blurry, low quality, watermark, text artefacts")
    p.add_argument("--seed-base", type=int, default=20260917)
    p.add_argument("--limit", type=int, default=0, help="render only the first N prompts")
    p.add_argument("--timeout", type=float, default=600.0)
    a = p.parse_args()
    w, h, st, cfg = DEFAULTS[a.preset]
    a.width = a.width or w; a.height = a.height or h; a.steps = a.steps or st; a.cfg = a.cfg if a.cfg is not None else cfg
    a.prefix = f"durable_watermark_corpus/{a.preset}"
    if a.preset in ("sdxl", "sd15", "sd35") and not a.checkpoint: sys.exit("--checkpoint is required for this preset")
    if a.preset == "flux" and not (a.unet and a.clip1 and a.clip2 and a.vae): sys.exit("flux needs --unet --clip1 --clip2 --vae")
    if a.preset == "sd35" and not (a.clip1 and a.clip2 and a.clip3): sys.exit("sd35 needs --clip1 --clip2 --clip3")
    prompts = json.load(open(a.prompts))
    if a.limit: prompts = prompts[:a.limit]
    os.makedirs(a.out, exist_ok=True)
    manifest_path = os.path.join(a.out, "manifest.json")
    manifest = json.load(open(manifest_path)) if os.path.exists(manifest_path) else []
    done = {m["id"] for m in manifest}
    build = PRESETS[a.preset]
    for i, row in enumerate(prompts):
        if row["id"] in done: continue
        seed = (a.seed_base + i) & 0xFFFFFFFFFFFF
        wf = build(a, row["prompt"], seed)
        t0 = time.time()
        pid = api(a.server, "/prompt", {"prompt": wf})["prompt_id"]
        im = wait_for(a.server, pid, a.timeout)
        q = urllib.parse.urlencode({"filename": im["filename"], "subfolder": im.get("subfolder", ""), "type": "output"})
        with urllib.request.urlopen(a.server + "/view?" + q, timeout=120) as r:
            data = r.read()
        fn = f"{row['id']}.png"
        with open(os.path.join(a.out, fn), "wb") as f: f.write(data)
        manifest.append({"id": row["id"], "file": fn, "category": row["category"], "prompt": row["prompt"],
                         "preset": a.preset, "model": a.checkpoint or a.unet, "seed": seed,
                         "size": [a.width, a.height], "steps": a.steps, "cfg": a.cfg, "seconds": round(time.time() - t0, 1)})
        json.dump(manifest, open(manifest_path, "w"), indent=1)
        print(f"[{len(manifest):3d}/{len(prompts)}] {row['id']}  {time.time() - t0:.1f}s")
    print("done:", len(manifest), "images in", a.out)


if __name__ == "__main__":
    main()
