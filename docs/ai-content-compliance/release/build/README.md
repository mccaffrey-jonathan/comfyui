# Release page build

`index.html` (one self-contained file, images inlined) is produced by:

1. `make_media.py` – runs the Key / Embed / Detect / C2PA nodes inside ComfyUI (CPU) on
   `input/example.png` and writes `media/media.json` (data URIs, detection reports, manifest).
2. `quality_sweep.py` – JPEG / WebP / resolution / strength sweep -> `quality_sweep.json`
   (needs `tools/bench.py` from the watermark pack on the path; copy it next to this script).
3. `build_page.py` – assembles the page. Set `RELEASE_WORK` to the directory holding
   `media/media.json` and `quality_sweep.json`; `CORPUS_RESULTS` to the output of
   `tools/eval_corpus.py` and `CORPUS_FIGS` to the directory holding its figures
   (`payload_rate_by_transform.png`, `z_separation.png`, `corpus_contact_sheet.jpg`, see
   `docs/ai-content-compliance/reviews/figures/corpus100/`).

Run from the ComfyUI root with the two node packs installed.
