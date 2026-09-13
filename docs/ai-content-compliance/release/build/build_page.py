"""Assemble the release page from media.json + quality_sweep.json."""
import json, os, html

S = os.environ.get("RELEASE_WORK", os.path.dirname(os.path.abspath(__file__)))
media = json.load(open(f"{S}/media/media.json"))
sweep = json.load(open(f"{S}/quality_sweep.json"))
OUT = f"{S}/release/index.html"
os.makedirs(os.path.dirname(OUT), exist_ok=True)

c2 = media["c2pa"]
store = c2["store"]
active = store["manifests"][store["active_manifest"]]
# trimmed manifest for display: assertions without the workflow blobs, signature info
display_manifest = {
    "label": active.get("label"),
    "title": active.get("title"),
    "format": active.get("format"),
    "claim_generator_info": active.get("claim_generator_info"),
    "assertions": [a for a in active.get("assertions", []) if a.get("label") not in ("c2pa.thumbnail.claim", "c2pa.hash.data")],
    "signature_info": active.get("signature_info"),
}
def trim(o, depth=0):
    if isinstance(o, dict):
        return {k: trim(v, depth + 1) for k, v in o.items() if k not in ("thumbnail",)}
    if isinstance(o, list):
        return [trim(v, depth + 1) for v in o]
    if isinstance(o, str) and len(o) > 160:
        return o[:157] + "…"
    return o
manifest_json = json.dumps(trim(display_manifest), indent=2)
summary_json = json.dumps(c2["summary"], indent=2)
private_json = json.dumps(c2["decrypted_private"], indent=2)

g = media["gallery"]
ok = sum(1 for x in g if x["matches"]); det = sum(1 for x in g if x["detected"])

def badge(x):
    if x["matches"]:
        return '<span class="pill good">payload verified</span>'
    if x["detected"]:
        return '<span class="pill warn">presence only</span>'
    return '<span class="pill bad">not detected</span>'

gallery_html = "\n".join(f'''
<figure class="tile">
  <img src="{x['img']}" alt="{html.escape(x['name'])}" loading="lazy">
  <figcaption>
    <div class="tile-head"><span class="tile-name">{html.escape(x['name'])}</span>{badge(x)}</div>
    <dl class="kv">
      <div><dt>z-score</dt><dd class="mono">{x['z']:.1f}</dd></div>
      <div><dt>decoded</dt><dd class="mono">{x['payload']}</dd></div>
      <div><dt>scale · rotation</dt><dd class="mono">{x['scale']:.2f} · {x['rotation']:.0f}°{' · mirrored' if x['flipped'] else ''}</dd></div>
      <div><dt>size</dt><dd class="mono">{x['size']}</dd></div>
    </dl>
  </figcaption>
</figure>''' for x in g)

fs = c2
size_row = f'''<tr><td>PNG, watermarked, unsigned</td><td class="num">{fs['png_plain_size']/1024:.0f} KB</td></tr>
<tr><td>PNG + signed manifest (with thumbnail, encrypted assertion)</td><td class="num">{fs['file_size']/1024:.0f} KB</td></tr>
<tr><td>JPEG q90, unsigned</td><td class="num">{fs['jpeg_plain_size']/1024:.0f} KB</td></tr>
<tr><td>JPEG q90 + signed manifest</td><td class="num">{fs['jpeg_signed_size']/1024:.0f} KB</td></tr>'''

kl = media["key_layout"]
data_js = json.dumps({"sweep": sweep, "gallery": [{k: v for k, v in x.items() if k != "img"} for x in g]})

page = f'''<title>Durable Watermark & Content Credentials</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Condensed:wght@500;600;700&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root {{
  --bg:#F6F7F9; --surface:#FFFFFF; --surface-2:#EEF1F5; --line:#D9DEE6; --line-2:#C3CAD5;
  --ink:#14181F; --ink-2:#3C4655; --muted:#5A6472; --faint:#8B95A3;
  --accent:#0E8A7E; --accent-ink:#0B6F66; --accent-soft:#D9F0EC;
  --seal:#B7791F; --seal-ink:#8F5D14; --seal-soft:#F6EAD3;
  --good:#2E7D4F; --good-soft:#DDF0E4; --warn:#9A6A12; --warn-soft:#F6EBD0; --bad:#B23A3A; --bad-soft:#F5DEDE;
  --s1:#0A9686; --s2:#B7791F; --s3:#3B5BA5; --grid:#E4E8EE;
  --display:"IBM Plex Sans Condensed", "Arial Narrow", sans-serif; --body:"IBM Plex Sans", "Helvetica Neue", Arial, sans-serif; --mono:"IBM Plex Mono", "SFMono-Regular", Menlo, monospace;
  color-scheme: light dark;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg:#0F1216; --surface:#171B21; --surface-2:#1F252D; --line:#2B333D; --line-2:#3A4451;
  --ink:#E8ECF1; --ink-2:#C4CBD5; --muted:#98A2B0; --faint:#6F7A89;
  --accent:#3FBFB1; --accent-ink:#7ADCD0; --accent-soft:#12312E;
  --seal:#E0A33A; --seal-ink:#F0C46F; --seal-soft:#332711;
  --good:#5FC38A; --good-soft:#12301E; --warn:#E0B24C; --warn-soft:#33270D; --bad:#E07070; --bad-soft:#3A1717;
  --s1:#2FA89B; --s2:#B8822A; --s3:#6A8AD6; --grid:#232A33;
}} }}
:root[data-theme="dark"] {{
  --bg:#0F1216; --surface:#171B21; --surface-2:#1F252D; --line:#2B333D; --line-2:#3A4451;
  --ink:#E8ECF1; --ink-2:#C4CBD5; --muted:#98A2B0; --faint:#6F7A89;
  --accent:#3FBFB1; --accent-ink:#7ADCD0; --accent-soft:#12312E;
  --seal:#E0A33A; --seal-ink:#F0C46F; --seal-soft:#332711;
  --good:#5FC38A; --good-soft:#12301E; --warn:#E0B24C; --warn-soft:#33270D; --bad:#E07070; --bad-soft:#3A1717;
  --s1:#2FA89B; --s2:#B8822A; --s3:#6A8AD6; --grid:#232A33;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font-family:var(--body); font-size:16px; line-height:1.55; padding-inline:16px; padding-block:0 64px; }}
a {{ color:var(--accent-ink); }}
a:focus-visible, button:focus-visible, summary:focus-visible, input:focus-visible {{ outline:2px solid var(--accent); outline-offset:2px; }}
.wrap {{ max-width:1080px; margin:0 auto; }}
.prose {{ max-width:68ch; }}
h1,h2,h3 {{ font-family:var(--display); text-wrap:balance; line-height:1.1; margin:0; }}
h1 {{ font-size:clamp(2.2rem, 5vw, 3.6rem); font-weight:700; letter-spacing:-0.01em; }}
h2 {{ font-size:clamp(1.6rem, 3vw, 2.2rem); font-weight:600; margin-block:0 12px; }}
h3 {{ font-size:1.2rem; font-weight:600; margin-block:0 8px; }}
p {{ margin:0 0 14px; }}
.eyebrow {{ font-family:var(--mono); font-size:0.74rem; letter-spacing:0.12em; text-transform:uppercase; color:var(--muted); }}
.mono, code, pre {{ font-family:var(--mono); }}
code {{ font-size:0.9em; background:var(--surface-2); padding:1px 5px; border-radius:3px; }}
pre {{ background:var(--surface-2); border:1px solid var(--line); border-radius:6px; padding:14px; overflow-x:auto; font-size:0.8rem; line-height:1.45; margin:0; max-height:520px; }}
.num {{ font-variant-numeric:tabular-nums; text-align:right; }}

/* header / rail */
header.top {{ position:sticky; top:0; z-index:5; background:var(--bg); border-bottom:1px solid var(--line); margin-inline:-16px; padding-inline:16px; }}
header.top .wrap {{ display:flex; align-items:center; gap:18px; height:52px; overflow-x:auto; }}
header.top .brand {{ font-family:var(--display); font-weight:700; white-space:nowrap; }}
header.top nav {{ display:flex; gap:16px; white-space:nowrap; }}
header.top nav a {{ color:var(--ink-2); text-decoration:none; font-size:0.9rem; padding-block:4px; border-bottom:2px solid transparent; }}
header.top nav a:hover {{ border-bottom-color:var(--accent); }}
.version {{ margin-left:auto; font-family:var(--mono); font-size:0.75rem; color:var(--muted); white-space:nowrap; }}

/* hero */
.hero {{ padding-block:44px 28px; display:grid; grid-template-columns:minmax(0,1.05fr) minmax(0,1fr); gap:32px; align-items:start; }}
.hero .lede {{ font-size:1.12rem; color:var(--ink-2); max-width:56ch; }}
.hero .facts {{ display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:12px; margin-top:22px; }}
.fact {{ border-top:2px solid var(--line-2); padding-top:8px; }}
.fact .v {{ font-family:var(--display); font-size:1.7rem; font-weight:600; line-height:1; }}
.fact .l {{ font-size:0.8rem; color:var(--muted); margin-top:4px; }}
.compare {{ position:relative; aspect-ratio:1/1; max-width:100%; border-radius:6px; overflow:hidden; border:1px solid var(--line); background:var(--surface-2); user-select:none; }}
.compare img {{ position:absolute; inset:0; width:100%; height:100%; display:block; }}
.compare .after {{ clip-path:inset(0 0 0 50%); }}
.compare .handle {{ position:absolute; top:0; bottom:0; left:50%; width:2px; background:#fff; box-shadow:0 0 0 1px rgba(0,0,0,.35); transform:translateX(-1px); pointer-events:none; }}
.compare .knob {{ position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); width:34px; height:34px; border-radius:50%; background:#fff; color:#14181F; display:grid; place-items:center; font-family:var(--mono); font-size:0.7rem; box-shadow:0 1px 4px rgba(0,0,0,.4); pointer-events:none; }}
.compare .tag {{ position:absolute; bottom:8px; font-family:var(--mono); font-size:0.7rem; background:rgba(20,24,31,.72); color:#fff; padding:2px 7px; border-radius:3px; }}
.compare .tag.l {{ left:8px; }} .compare .tag.r {{ right:8px; }}
.compare input[type=range] {{ position:absolute; inset:0; width:100%; height:100%; opacity:0; cursor:ew-resize; margin:0; }}
.caption {{ font-size:0.82rem; color:var(--muted); margin-top:8px; }}

section {{ padding-block:36px; border-top:1px solid var(--line); }}
.two {{ display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:24px; }}
.three {{ display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:16px; }}
.figure {{ margin:0; }}
.figure img {{ width:100%; height:auto; display:block; border:1px solid var(--line); border-radius:4px; background:var(--surface-2); }}
.figure figcaption {{ font-size:0.82rem; color:var(--muted); margin-top:6px; }}
.steps {{ counter-reset:step; display:grid; gap:14px; padding:0; margin:0; list-style:none; }}
.steps li {{ display:grid; grid-template-columns:36px 1fr; gap:12px; }}
.steps li::before {{ counter-increment:step; content:counter(step); font-family:var(--display); font-size:1.4rem; font-weight:600; color:var(--accent); line-height:1.1; }}
.node {{ display:inline-block; font-family:var(--mono); font-size:0.78rem; padding:3px 8px; border:1px solid var(--line-2); border-radius:4px; background:var(--surface); }}
.node.seal {{ border-color:var(--seal); }}
.flow {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:12px 0 18px; }}
.flow .arr {{ color:var(--faint); }}

.gallery {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(230px, 1fr)); gap:14px; }}
.tile {{ margin:0; background:var(--surface); border:1px solid var(--line); border-radius:6px; overflow:hidden; display:flex; flex-direction:column; }}
.tile img {{ width:100%; aspect-ratio:1/1; object-fit:contain; background:var(--surface-2); display:block; }}
.tile figcaption {{ padding:10px 12px 12px; }}
.tile-head {{ display:flex; justify-content:space-between; gap:8px; align-items:start; margin-bottom:8px; }}
.tile-name {{ font-weight:600; font-size:0.92rem; line-height:1.25; }}
.pill {{ font-family:var(--mono); font-size:0.66rem; letter-spacing:0.04em; padding:2px 7px; border-radius:999px; white-space:nowrap; flex:none; }}
.pill.good {{ background:var(--good-soft); color:var(--good); }}
.pill.warn {{ background:var(--warn-soft); color:var(--warn); }}
.pill.bad {{ background:var(--bad-soft); color:var(--bad); }}
.kv {{ display:grid; grid-template-columns:1fr 1fr; gap:4px 10px; margin:0; font-size:0.78rem; }}
.kv div {{ display:flex; flex-direction:column; }}
.kv dt {{ color:var(--muted); }} .kv dd {{ margin:0; }}

table {{ border-collapse:collapse; width:100%; font-size:0.9rem; }}
th, td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
th {{ font-size:0.76rem; letter-spacing:0.06em; text-transform:uppercase; color:var(--muted); font-weight:600; }}
.tablewrap {{ overflow-x:auto; }}
.yes {{ color:var(--good); font-weight:600; }} .part {{ color:var(--warn); font-weight:600; }} .no {{ color:var(--bad); font-weight:600; }}

.chart {{ background:var(--surface); border:1px solid var(--line); border-radius:6px; padding:14px 14px 8px; }}
.chart h3 {{ font-size:1rem; }}
.chart .sub {{ font-size:0.8rem; color:var(--muted); margin-bottom:8px; }}
.chart svg {{ width:100%; height:auto; display:block; font-family:var(--body); }}
.legend {{ display:flex; gap:14px; flex-wrap:wrap; font-size:0.78rem; color:var(--ink-2); margin-top:6px; }}
.legend span::before {{ content:""; display:inline-block; width:14px; height:3px; border-radius:2px; vertical-align:middle; margin-right:6px; background:var(--sw); }}
.tip {{ position:fixed; pointer-events:none; background:var(--ink); color:var(--bg); font-family:var(--mono); font-size:0.72rem; padding:5px 8px; border-radius:4px; z-index:9; display:none; white-space:nowrap; }}
.toggle {{ display:flex; gap:6px; margin-bottom:10px; }}
.toggle button {{ font:inherit; font-size:0.8rem; padding:4px 10px; border:1px solid var(--line-2); background:var(--surface); color:var(--ink-2); border-radius:4px; cursor:pointer; }}
.toggle button[aria-pressed="true"] {{ background:var(--accent-soft); border-color:var(--accent); color:var(--ink); }}
details {{ border:1px solid var(--line); border-radius:6px; background:var(--surface); }}
details summary {{ cursor:pointer; padding:10px 14px; font-weight:600; }}
details > div {{ padding:0 14px 14px; }}
.callout {{ border-left:3px solid var(--seal); background:var(--seal-soft); padding:12px 16px; border-radius:0 6px 6px 0; }}
.callout.teal {{ border-left-color:var(--accent); background:var(--accent-soft); }}
.small {{ font-size:0.85rem; color:var(--muted); }}
footer {{ padding-block:24px; font-size:0.8rem; color:var(--muted); border-top:1px solid var(--line); }}
@media (max-width: 760px) {{
  .hero, .two, .three {{ grid-template-columns:1fr; }}
  .hero .facts {{ grid-template-columns:repeat(3, minmax(0,1fr)); }}
}}
@media (prefers-reduced-motion: no-preference) {{ .compare .after {{ transition:clip-path 40ms linear; }} }}
</style>

<header class="top"><div class="wrap">
  <span class="brand">Durable Watermark &amp; Content Credentials</span>
  <nav><a href="#watermark">Watermark</a><a href="#quality">Image quality</a><a href="#c2pa">C2PA</a><a href="#compliance">Compliance</a><a href="#install">Install</a></nav>
  <span class="version">release 0.1.0 · 2026-09-13</span>
</div></header>

<div class="wrap">
<div class="hero">
  <div>
    <div class="eyebrow">ComfyUI custom node packs · release notes</div>
    <h1 style="margin-block:10px 16px">Two layers of proof for every generated image</h1>
    <p class="lede">A keyed, invisible watermark that survives rotation, crops, rescaling, colour edits and JPEG, and a signed C2PA manifest that names the provider, system, time and a unique id. Together they meet the two-layer marking the EU AI Act Code of Practice asks for and the latent-disclosure fields in California's AI Transparency Act.</p>
    <div class="facts">
      <div class="fact"><div class="v mono">{media['diff_stats']['psnr']:.1f} dB</div><div class="l">PSNR of the mark on the demo image (default strength)</div></div>
      <div class="fact"><div class="v mono">{ok}/{len(g)}</div><div class="l">edits in the gallery below with the 32-bit payload recovered</div></div>
      <div class="fact"><div class="v mono">{media['wrong_key_z']:+.1f}</div><div class="l">z-score with the wrong key (threshold 5.0)</div></div>
    </div>
  </div>
  <div>
    <div class="compare" id="cmp">
      <img class="before" src="{media['original_png']}" alt="Original demo image">
      <img class="after" src="{media['marked_png']}" alt="Watermarked demo image">
      <div class="handle"></div><div class="knob">⇔</div>
      <span class="tag l">original</span><span class="tag r">watermarked</span>
      <input type="range" id="cmp-range" min="0" max="100" value="50" aria-label="Compare original and watermarked">
    </div>
    <div class="caption">Drag to compare. Both images were produced by running the nodes inside ComfyUI on its bundled <code>example.png</code>; the watermark carries payload <code>{media['payload_hex']}</code> ("acme-image-studio" hashed to 32 bits).</div>
  </div>
</div>

<section id="watermark">
  <div class="eyebrow">Pack 1 · comfyui_durable_watermark</div>
  <h2>A watermark you cannot rotate, crop or recolour away</h2>
  <div class="two">
    <div class="prose">
      <p>The mark lives in the frequency domain of the luminance channel, in <strong>{kl['n_rings']} concentric rings</strong> between {kl['r_min']} and {kl['r_max']} cycles per pixel. Each ring's mean energy is nudged up or down by a keyed sign, and its energy around the ring is modulated by {kl['n_harm']} angular harmonics with keyed phases and antipodal signs. That gives <strong>{kl['n_chips']} chips per image</strong>: {kl['n_sync']} known sync chips for presence detection and geometry estimation, {kl['n_payload']} payload chips carrying 32 bits plus a CRC through keyed block codes with soft maximum-likelihood decoding.</p>
      <p>Why this survives edits: the DFT magnitude ignores translation, so crops keep the rings aligned; a rotation only shifts each harmonic's phase by a known multiple of the angle, which the detector searches in 2° steps; a mirror conjugates the harmonics; uniform rescaling moves the rings radially and is found by a one-dimensional scan from 0.4× to 2.5×; hue and saturation never touch luminance, and brightness, contrast and gamma are removed by detrending.</p>
      <p>The detector reports an honest number. Every image is also scored with 96 <em>wrong</em> keys put through the identical search, and the z-score is measured against that distribution, so the geometric search cannot inflate false positives. The unmarked demo image scores z = {media['unmarked_z']:+.1f}; the marked image with the wrong key scores {media['wrong_key_z']:+.1f}.</p>
      <div class="flow"><span class="node">Durable Watermark Key</span><span class="arr">→</span><span class="node">Durable Watermark Embed</span><span class="arr">→</span><span class="node seal">Save Image with Content Credentials</span></div>
      <p class="small">No model weights, no GPU: pure numpy and scipy. About 0.8 s to embed and 2 s to detect a 768 px image on one CPU core. Apache-2.0 licensed. Also usable from the command line and as a two-function Python library for detection services.</p>
    </div>
    <div>
      <div class="three">
        <figure class="figure"><img src="{media['spec_original']}" alt="Log power spectrum of the original image"><figcaption>Log-power spectrum, original</figcaption></figure>
        <figure class="figure"><img src="{media['spec_marked']}" alt="Log power spectrum of the watermarked image"><figcaption>Spectrum, watermarked (visually identical)</figcaption></figure>
        <figure class="figure"><img src="{media['spec_ratio']}" alt="Ratio of watermarked to original spectrum showing concentric rings"><figcaption>Marked ÷ original: the keyed rings and their angular modulation</figcaption></figure>
      </div>
      <div class="three" style="margin-top:16px">
        <figure class="figure"><img src="{media['zoom_original']}" alt="Zoomed crop of the original"><figcaption>128 px crop, original, 3× zoom</figcaption></figure>
        <figure class="figure"><img src="{media['zoom_marked']}" alt="Zoomed crop of the watermarked image"><figcaption>Same crop, watermarked</figcaption></figure>
        <figure class="figure"><img src="{media['diff']}" alt="Amplified difference between watermarked and original"><figcaption>Difference ×24 (mean |Δ| {media['diff_stats']['mean_abs_delta_8bit']:.2f}, max {media['diff_stats']['max_abs_delta_8bit']:.0f} of 255)</figcaption></figure>
      </div>
    </div>
  </div>

  <h3 style="margin-top:34px">Detection after editing</h3>
  <p class="small" style="max-width:70ch">Each tile is the watermarked demo image after one edit, run through the <em>Durable Watermark Detect</em> node with the correct key. Green: the 32-bit payload was decoded and its CRC verified. Amber: presence detected (z ≥ 5) but the payload did not decode. Red: not detected. {det} of {len(g)} edits are detected; {ok} of {len(g)} return the payload.</p>
  <div class="gallery">{gallery_html}</div>
</section>

<section id="quality">
  <div class="eyebrow">Measurements</div>
  <h2>What image quality does to the watermark</h2>
  <div class="prose">
    <p>Three questions matter in practice: how much the mark costs in visual quality, how much compression it tolerates, and how small the image can get. The sweep below uses three 640 to 768 px test images: a photo-like illustration (ComfyUI's example), a flat vector-style graphic with a gradient and a solid shape, and a 1/f texture. Payload is 32 bits; "payload" means decoded with CRC verified.</p>
    <p><strong>Cost of the mark.</strong> Strength scales the modulation depth linearly. At the default 1.0 the mark sits at 43 dB PSNR on the photo, 47 dB on the flat graphic and 40 dB on the texture, with luminance SSIM between 0.97 and 0.99. Strength 1.5 buys roughly 5 to 6 z-points and one JPEG quality step at a 3 to 4 dB cost; below 1.0 the photo is still detected but the 32-bit payload no longer decodes.</p>
    <p><strong>Compression.</strong> JPEG discards exactly the mid and high spatial frequencies the rings use, so quality is the dominant factor. On the photo the payload survives to about q90 and presence to about q60 at strength 1.0 (the exact edge moves a step with the key and the image); at strength 1.5 the payload holds to q50 and presence to q30. Textured content is easy at any quality. WebP is <em>harsher</em> than JPEG at the same quality number: its deblocking filter smooths the mid band, so on the photo the payload only survives q100 and presence q90 at strength 1.0. Flat graphics are the weak case for both codecs: the only energy they carry in the band is the mark's own keyed floor, which quantisation removes below about q80.</p>
    <p><strong>Resolution.</strong> Downscaling shifts the rings outward; the scale search recovers it until the outer rings pass the Nyquist limit. The payload holds to 0.5× on the photo (a 384 px image) and presence to 0.4× (307 px); at strength 1.5 the payload holds to 0.4×. Below about 300 px there is not enough spectral resolution for the default ring width. Downscale followed by JPEG 85 compounds: the photo then keeps the payload only at full size (0.65× at strength 1.5).</p>
  </div>
  <div class="two" style="margin-top:8px">
    <div class="chart" id="chart-strength"></div>
    <div class="chart" id="chart-res"></div>
  </div>
  <div class="two" style="margin-top:16px">
    <div class="chart" id="chart-jpeg"></div>
    <div class="chart" id="chart-webp"></div>
  </div>
  <details style="margin-top:16px"><summary>Sweep data as a table</summary><div class="tablewrap" id="sweep-table"></div></details>
</section>

<section id="c2pa">
  <div class="eyebrow">Pack 2 · comfyui_content_credentials</div>
  <h2>A signed manifest that says who, what, when</h2>
  <div class="two">
    <div class="prose">
      <p>The save node encodes the image (PNG, JPEG or WebP), builds a C2PA manifest, signs it with your certificate through the official <code>c2pa-python</code> SDK (c2pa-rs 0.90 core) and writes the file. The manifest declares the asset AI-generated the way Adobe Firefly, OpenAI and Google do: a <code>c2pa.actions.v2</code> assertion with <code>c2pa.created</code> and <code>digitalSourceType = trainedAlgorithmicMedia</code>, an object-form <code>softwareAgent</code> with name and version, and a timestamp.</p>
      <p>The demo file below was signed inside ComfyUI with a self-issued test certificate. The <em>Read / Verify</em> node reports <strong>{c2['state_untrusted_anchor']}</strong> (cryptographically sound, signer not on the C2PA trust list) and <strong>{c2['state_with_root']}</strong> once the test root is supplied as an anchor. Production certificates from a C2PA-listed CA validate as Trusted in public verifiers without any extra step.</p>
      <div class="callout"><strong>Signed is not secret.</strong> Everything in a manifest is public and any re-encode removes it. That is why the watermark's payload and key fingerprint are written into a <code>c2pa.soft-binding</code> assertion: after the metadata is stripped, the watermark still identifies the manifest in your registry. Only the optional <code>org.comfyui.private</code> assertion is encrypted (AES-256-GCM, HKDF from a provider passphrase); the demo stores a tenant and job id there.</div>
      <div class="flow" style="margin-top:16px"><span class="node seal">C2PA Signer</span><span class="node seal">Generate Test Certificate</span><span class="node seal">Save Image with Content Credentials</span><span class="node seal">Read / Verify Manifest</span><span class="node seal">Decrypt Private Assertion</span></div>
      <div class="tablewrap"><table><thead><tr><th>Demo file</th><th class="num">Size</th></tr></thead><tbody>{size_row}</tbody></table></div>
    </div>
    <div>
      <div class="toggle" role="tablist">
        <button aria-pressed="true" data-pane="p-summary">Verification summary</button>
        <button aria-pressed="false" data-pane="p-manifest">Manifest as read back</button>
        <button aria-pressed="false" data-pane="p-private">Decrypted private assertion</button>
      </div>
      <pre id="p-summary">{html.escape(summary_json)}</pre>
      <pre id="p-manifest" hidden>{html.escape(manifest_json)}</pre>
      <pre id="p-private" hidden>{html.escape(private_json)}</pre>
    </div>
  </div>

  <h3 style="margin-top:34px">What C2PA supports, and what the node exposes</h3>
  <div class="tablewrap"><table>
    <thead><tr><th>Capability</th><th>C2PA 2.x / c2pa-python 0.37</th><th>This node pack</th></tr></thead>
    <tbody>
      <tr><td>Container formats</td><td>PNG, JPEG, WebP, AVIF, GIF, HEIC/HEIF, JXL, TIFF, DNG, SVG, MP4/MOV, MP3/WAV/FLAC/M4A, PDF (read), sidecar .c2pa</td><td><span class="yes">PNG, JPEG, WebP</span> written; any format read</td></tr>
      <tr><td>Signing algorithms</td><td>ES256/384/512, PS256/384/512, Ed25519; local keys, callback signers (HSM/KMS), remote signing services</td><td><span class="yes">all seven</span> with local PEM keys; callback signers via the Python API</td></tr>
      <tr><td>Certificates and trust</td><td>X.509 chain, RFC 3161 timestamps, OCSP, C2PA Trust List, user trust anchors, conformance levels 1 (software keys) and 2 (hardware)</td><td><span class="yes">chain from file/env/PEM, TSA, test-chain generator, custom anchors on read</span></td></tr>
      <tr><td>Hard binding</td><td>Hash of the asset bytes (<code>c2pa.hash.data</code>, BMFF/box hashes for video); any change invalidates</td><td><span class="yes">automatic</span></td></tr>
      <tr><td>Actions and provenance</td><td><code>c2pa.actions.v2</code>: created, opened, edited, placed, transcoded, watermarked; <code>digitalSourceType</code> from the IPTC vocabulary; <code>softwareAgent</code>; ingredients (parents, components) with nested manifests; update manifests</td><td><span class="yes">created / edited, five source types, watermarked, parent ingredient for img2img</span></td></tr>
      <tr><td>Generator identity</td><td><code>claim_generator_info</code> name + version + custom keys</td><td><span class="yes">system name, version, provider</span></td></tr>
      <tr><td>AI training preferences</td><td><code>cawg.training-mining</code> (ai_generative_training, ai_training, ai_inference, data_mining: allowed / notAllowed / constrained)</td><td><span class="yes">do-not-train switch</span></td></tr>
      <tr><td>Custom assertions</td><td>Any reverse-DNS label, CBOR or JSON</td><td><span class="yes">org.comfyui.generation, .watermark, .workflow, .private</span></td></tr>
      <tr><td>Soft bindings</td><td><code>c2pa.soft-binding</code> with an algorithm id from the 53-entry registry (TrustMark, Digimarc, PixelSeal, InvisMark …), region/time scopes; Soft Binding Resolution API for lookup</td><td><span class="part">written with <code>org.comfyui.ringmark.v1</code></span> (not yet a registered id; value stored as text)</td></tr>
      <tr><td>Metadata assertions</td><td><code>c2pa.metadata</code> (allow-listed Exif/IPTC/XMP), <code>cawg.metadata</code> (unrestricted), CAWG identity assertions</td><td><span class="no">not written</span> (generation facts live in the custom assertion)</td></tr>
      <tr><td>Thumbnails and resources</td><td>Claim and ingredient thumbnails, embedded resources</td><td><span class="yes">claim thumbnail (SDK default)</span></td></tr>
      <tr><td>Remote / sidecar manifests</td><td><code>set_remote_url</code>, <code>set_no_embed</code>, sidecar files, manifest repositories</td><td><span class="no">embedded only</span></td></tr>
      <tr><td>Redaction</td><td>Redact assertions from ingredient manifests</td><td><span class="no">no</span></td></tr>
      <tr><td>Encryption</td><td>Not part of C2PA</td><td><span class="yes">optional encrypted private assertion</span> (pack feature)</td></tr>
      <tr><td>Validation output</td><td>States Invalid / Valid / Trusted; success, informational and failure codes per manifest and ingredient</td><td><span class="yes">state, failures, AI-generated flag, signer, soft bindings</span></td></tr>
    </tbody>
  </table></div>
</section>

<section id="compliance">
  <div class="eyebrow">Regulatory mapping · not legal advice · no compliance warranty</div>
  <h2>Where each obligation lands</h2>
  <div class="tablewrap"><table>
    <thead><tr><th>Obligation</th><th>Watermark</th><th>Content Credentials</th></tr></thead>
    <tbody>
      <tr><td><strong>EU AI Act Art. 50(2)</strong>, in force since 2 Aug 2026: outputs "marked in a machine-readable format and detectable as artificially generated"; Code of Practice (June 2026) requires signed metadata <em>and</em> an imperceptible watermark, plus a detection facility</td><td class="yes">imperceptible layer; Detect node and CLI as the detection facility</td><td class="yes">signed, timestamped metadata layer with <code>trainedAlgorithmicMedia</code></td></tr>
      <tr><td><strong>California B&amp;P §22757.3</strong> (SB 942 / AB 853, operative 2 Aug 2026): latent disclosure with (A) provider name, (B) system name and version, (C) time and date, (D) unique identifier; "consistent with widely accepted industry standards"; "permanent or extraordinarily difficult to remove"; provider must offer a detection tool</td><td class="part">carries a 32-bit id (provider or generation id fragment); survives the edits that strip metadata</td><td class="yes">all four fields in <code>org.comfyui.generation</code>, <code>softwareAgent</code>, action <code>when</code> and the manifest <code>urn:uuid</code></td></tr>
      <tr><td><strong>SB 1000</strong> (on the Governor's desk, deadline 30 Sep 2026): removes the 1 M-user threshold, adds a created-vs-altered flag</td><td>—</td><td class="yes"><code>c2pa.created</code> vs <code>c2pa.edited</code> plus <code>digitalSourceType</code></td></tr>
      <tr><td><strong>Do-not-train signalling</strong> (CAWG assertion referenced by EU Code and industry practice)</td><td>—</td><td class="yes"><code>cawg.training-mining</code></td></tr>
      <tr><td><strong>China GB 45438-2025</strong> implicit-label XMP fields; <strong>Korea, India</strong> visible labels for realistic output</td><td class="part">machine-readable label acceptable in Korea for non-deepfake output</td><td class="no">XMP block and visible labels not produced; mirror the same facts downstream</td></tr>
    </tbody>
  </table></div>
</section>

<section id="install">
  <div class="eyebrow">Getting started</div>
  <h2>Install and first workflow</h2>
  <div class="two">
    <div>
      <ol class="steps">
        <li><div><strong>Install the packs.</strong> They ship in <code>custom_nodes/</code> of this ComfyUI fork. Run <code>pip install -r custom_nodes/comfyui_content_credentials/requirements.txt</code> (adds <code>c2pa-python</code> and <code>cryptography</code>); the watermark pack needs nothing beyond ComfyUI's numpy, scipy and Pillow.</div></li>
        <li><div><strong>Set the private value.</strong> Export <code>COMFYUI_WATERMARK_SECRET</code> on the server, or reference it as <code>env:NAME</code> in the Key node. Never type a literal secret into the widget: ComfyUI writes widget values into PNG metadata. Providers set <code>COMFYUI_WATERMARK_ENFORCE=1</code> so workflows cannot re-key or disable the mark.</div></li>
        <li><div><strong>Wire the graph.</strong> <span class="node">Durable Watermark Key</span> → <span class="node">Durable Watermark Embed</span> after your VAE Decode, then <span class="node seal">C2PA Signer</span> + <span class="node seal">Save Image with Content Credentials</span> as the last node. Connect the embed node's <code>watermark_record</code> to the save node.</div></li>
        <li><div><strong>Get a real certificate.</strong> Test chains validate as Valid but untrusted. A certificate chaining to the C2PA Trust List (DigiCert, SSL.com, Tauth Labs) issued for a conformant product shows as Trusted in verifiers. Keep timestamping on so manifests outlive the certificate.</div></li>
        <li><div><strong>Verify.</strong> Use the Read / Verify node, <code>c2patool file.png</code>, or the public Content Credentials verifier; detect the watermark with the Detect node or <code>python -m durable_watermark detect file.png --secret env:NAME</code>.</div></li>
      </ol>
    </div>
    <div>
      <h3>Known limits</h3>
      <ul class="small" style="padding-left:18px; line-height:1.6">
        <li>Like SynthID, TrustMark and every post-hoc watermark, the mark does not survive diffusion regeneration, adversarial spectral optimisation or averaging many images marked with one key. Rotate keys and use per-image payloads.</li>
        <li>Flat vector-style graphics lose the payload under JPEG at or below q75 at default strength; use strength 1.5 or accept presence-only detection.</li>
        <li>Combined edits that net a downscale below about 0.65× together with strong JPEG push most rings past the usable band.</li>
        <li>Any node that re-saves the image after the C2PA node strips the manifest; the C2PA node must be the last writer.</li>
        <li><code>c2pa.soft-binding.value</code> is written as a text string; the spec's CDDL says byte string. Current validators accept it; the SDK's builder has no typed path yet.</li>
        <li>The research behind this page was compiled from a sandbox that blocked many primary legal sources; the repository reports cite every claim and flag the ones taken from secondary summaries.</li>
      </ul>
      <h3 style="margin-top:18px">In the repository</h3>
      <p class="small"><code>custom_nodes/comfyui_durable_watermark</code> · <code>custom_nodes/comfyui_content_credentials</code> · <code>docs/ai-content-compliance/</code> (design overview, legal research, watermarking state of the art, C2PA tooling) · branch <code>claude/ai-watermarking-compliance-0c2ubb</code>.</p>
    </div>
  </div>
</section>

<footer>All images on this page were produced by executing the released nodes inside ComfyUI (CPU) on the bundled example image; no diffusion model was run. Numbers are from the packs' benchmark and quality-sweep scripts on 13 September 2026. Demo certificate: self-issued "Acme Image Studio" test chain. Both packs are released under the Apache License 2.0 with a NOTICE disclaiming warranty, liability and any promise of regulatory compliance; nothing on this page is legal advice.</footer>
</div>
<div class="tip" id="tip"></div>

<script id="data" type="application/json">{data_js}</script>
<script>
(function(){{
  const D = JSON.parse(document.getElementById('data').textContent);
  // comparison slider
  const r = document.getElementById('cmp-range'), cmp = document.getElementById('cmp');
  const after = cmp.querySelector('.after'), handle = cmp.querySelector('.handle'), knob = cmp.querySelector('.knob');
  const set = v => {{ after.style.clipPath = `inset(0 0 0 ${{v}}%)`; handle.style.left = v + '%'; knob.style.left = v + '%'; }};
  r.addEventListener('input', e => set(+e.target.value)); set(50);
  // panes
  document.querySelectorAll('.toggle button').forEach(b => b.addEventListener('click', () => {{
    document.querySelectorAll('.toggle button').forEach(x => x.setAttribute('aria-pressed', x === b));
    ['p-summary','p-manifest','p-private'].forEach(id => document.getElementById(id).hidden = id !== b.dataset.pane);
  }}));

  // charts
  const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const SER = {{photo: '--s1', flat: '--s2', texture: '--s3'}};
  const names = {{photo:'photo-like', flat:'flat graphic', texture:'1/f texture'}};
  const tip = document.getElementById('tip');
  function showTip(e, t) {{ tip.textContent = t; tip.style.display='block'; tip.style.left = (e.clientX + 12) + 'px'; tip.style.top = (e.clientY + 12) + 'px'; }}
  function hideTip() {{ tip.style.display = 'none'; }}
  function lineChart(el, title, sub, series, xs, xlab, ylab, opts) {{
    const W = 520, H = 300, L = 46, R = 14, T = 16, B = 40;
    const ymin = opts.ymin ?? 0, ymax = opts.ymax; const xmin = Math.min(...xs), xmax = Math.max(...xs);
    const X = x => L + (opts.reverse ? (xmax - x) / (xmax - xmin) : (x - xmin) / (xmax - xmin)) * (W - L - R);
    const Y = y => T + (1 - (y - ymin) / (ymax - ymin)) * (H - T - B);
    let s = `<svg viewBox="0 0 ${{W}} ${{H}}" role="img" aria-label="${{title}}">`;
    const ticks = opts.yticks; ticks.forEach(t => {{ s += `<line x1="${{L}}" x2="${{W-R}}" y1="${{Y(t)}}" y2="${{Y(t)}}" stroke="${{css('--grid')}}" stroke-width="1"/><text x="${{L-6}}" y="${{Y(t)+4}}" text-anchor="end" font-size="11" fill="${{css('--muted')}}">${{t}}</text>`; }});
    if (opts.threshold != null) s += `<line x1="${{L}}" x2="${{W-R}}" y1="${{Y(opts.threshold)}}" y2="${{Y(opts.threshold)}}" stroke="${{css('--line-2')}}" stroke-width="1" stroke-dasharray="none"/><text x="${{L+4}}" y="${{Y(opts.threshold)-4}}" text-anchor="start" font-size="10" fill="${{css('--muted')}}">${{opts.thresholdLabel}}</text>`;
    xs.forEach(x => {{ s += `<text x="${{X(x)}}" y="${{H-B+16}}" text-anchor="middle" font-size="11" fill="${{css('--muted')}}">${{opts.xfmt ? opts.xfmt(x) : x}}</text>`; }});
    s += `<text x="${{(L+W-R)/2}}" y="${{H-4}}" text-anchor="middle" font-size="11" fill="${{css('--muted')}}">${{xlab}}</text>`;
    s += `<text transform="translate(12 ${{(T+H-B)/2}}) rotate(-90)" text-anchor="middle" font-size="11" fill="${{css('--muted')}}">${{ylab}}</text>`;
    series.forEach(sr => {{
      const col = css(SER[sr.key]);
      const pts = sr.pts.map(p => [X(p.x), Y(Math.max(ymin, Math.min(ymax, p.y)))]);
      s += `<path d="${{pts.map((p,i)=>(i?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ')}}" fill="none" stroke="${{col}}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
      sr.pts.forEach((p,i) => {{ const [px,py] = pts[i]; const filled = p.ok; s += `<circle cx="${{px}}" cy="${{py}}" r="${{filled?4.5:4}}" fill="${{filled?col:css('--surface')}}" stroke="${{filled?css('--surface'):col}}" stroke-width="2" data-tip="${{names[sr.key]}} · ${{opts.tipx ? opts.tipx(p.x) : p.x}} · ${{ylab}} ${{p.y}}${{p.ok?' · payload ok':(p.det?' · presence only':' · missed')}}"/>`; }});
      const last = pts[pts.length-1];
    }});
    s += `</svg>`;
    el.innerHTML = `<h3>${{title}}</h3><div class="sub">${{sub}}</div>${{s}}<div class="legend">${{series.map(sr=>`<span style="--sw:${{css(SER[sr.key])}}">${{names[sr.key]}}</span>`).join('')}}<span style="--sw:transparent">● filled = payload verified · ○ hollow = not decoded</span></div>`;
    el.querySelectorAll('circle').forEach(c => {{ c.addEventListener('mousemove', e => showTip(e, c.dataset.tip)); c.addEventListener('mouseleave', hideTip); }});
  }}
  const imgs = ['photo','flat','texture'];
  const sq = D.sweep.strength_quality;
  lineChart(document.getElementById('chart-strength'), 'Visual cost of the mark', 'PSNR of watermarked vs original, by strength (higher is more faithful)',
    imgs.map(k => ({{key:k, pts: sq.filter(r=>r.image===k).map(r=>({{x:r.strength, y:r.psnr, ok:r.payload_ok, det:true}}))}})),
    [0.5,0.75,1,1.5,2], 'strength', 'PSNR (dB)', {{ymin:30, ymax:56, yticks:[30,35,40,45,50,55]}});
  const jp = D.sweep.jpeg.filter(r=>r.strength===1.0), jp15 = D.sweep.jpeg.filter(r=>r.strength===1.5);
  const qs = [100,90,80,70,60,50,40,30,20];
  lineChart(document.getElementById('chart-jpeg'), 'JPEG quality, strength 1.0', 'Calibrated detection z-score after re-encoding (threshold 5). Strength 1.5 results are in the table below.',
    imgs.map(k => ({{key:k, pts: jp.filter(r=>r.image===k).map(r=>({{x:r.quality, y:r.z, ok:r.payload_ok, det:r.detected}}))}})),
    qs, 'JPEG quality (right = more compressed)', 'z-score', {{ymin:-2, ymax:46, yticks:[0,10,20,30,40], threshold:5, thresholdLabel:'detection threshold z = 5', reverse:true, tipx:x=>'q'+x}});
  const wp = D.sweep.webp.filter(r=>r.strength===1.0);
  lineChart(document.getElementById('chart-webp'), 'WebP quality, strength 1.0', 'Same test with WebP lossy encoding',
    imgs.map(k => ({{key:k, pts: wp.filter(r=>r.image===k).map(r=>({{x:r.quality, y:r.z, ok:r.payload_ok, det:r.detected}}))}})),
    qs, 'WebP quality (right = more compressed)', 'z-score', {{ymin:-2, ymax:46, yticks:[0,10,20,30,40], threshold:5, thresholdLabel:'detection threshold z = 5', reverse:true, tipx:x=>'q'+x}});
  const rs = D.sweep.resolution.filter(r=>r.strength===1.0);
  lineChart(document.getElementById('chart-res'), 'Downscaling, strength 1.0', 'z-score after Lanczos downscale to a fraction of the original side (then re-read as 8-bit)',
    imgs.map(k => ({{key:k, pts: rs.filter(r=>r.image===k).map(r=>({{x:r.factor, y:r.z, ok:r.payload_ok, det:r.z>=5}}))}})),
    [1,0.8,0.65,0.5,0.4,0.3,0.25], 'scale factor (right = smaller image)', 'z-score', {{ymin:-2, ymax:46, yticks:[0,10,20,30,40], threshold:5, thresholdLabel:'detection threshold z = 5', reverse:true, xfmt:x=>x+'×', tipx:x=>x+'×'}});

  // table
  const rows = [];
  D.sweep.jpeg.concat(D.sweep.webp.map(r=>Object.assign({{codec:'WebP'}}, r))).forEach(r => rows.push(`<tr><td>${{r.codec||'JPEG'}}</td><td>${{names[r.image]}}</td><td class="num">${{r.strength}}</td><td class="num">${{r.quality}}</td><td class="num">${{r.bpp}}</td><td class="num">${{r.z}}</td><td>${{r.payload_ok?'payload':(r.detected?'presence':'—')}}</td></tr>`));
  document.getElementById('sweep-table').innerHTML = `<table><thead><tr><th>Codec</th><th>Image</th><th class="num">Strength</th><th class="num">Quality</th><th class="num">bits/px</th><th class="num">z</th><th>Result</th></tr></thead><tbody>${{rows.join('')}}</tbody></table>`;
}})();
</script>
'''
open(OUT, "w").write(page)
print("wrote", OUT, len(page) // 1024, "KB")
