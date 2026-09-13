# C2PA Content Credentials for AI-generated images from Python (state as of 13 Sep 2026)

Research target: a ComfyUI custom node that signs PNG / JPEG / WebP outputs with C2PA manifests.

Note on sourcing: `opensource.contentauthenticity.org`, `spec.c2pa.org`, `c2pa.org`, `cawg.io`, `help.openai.com`, `leginfo.legislature.ca.gov` and most secondary blogs are blocked by this sandbox's egress proxy, so everything below was verified against the underlying GitHub sources of those sites (the `contentauth/c2pa-python`, `contentauth/c2pa-rs`, `contentauth/c2patool`, `contentauth/opensource.contentauth.org` (the docs-site source), `c2pa-org/softbinding-algorithm-list`, `adobe/trustmark` repos), PyPI's JSON API, real-world manifests committed to public repos, and a mirror of the California statute text. Where a claim rests on a search-engine snippet rather than a fetched primary source, it is marked "(snippet)".

---

## 1. `c2pa-python` — current package, API and platforms

### 1.1 Version and distribution

| Item | Value | Source |
|---|---|---|
| PyPI name / import | `c2pa-python` / `import c2pa` (import renamed from `c2pa-python` to `c2pa` in 0.4.0) | [PyPI JSON](https://pypi.org/pypi/c2pa-python/json), [release-notes.md](https://github.com/contentauth/c2pa-python/blob/main/docs/release-notes.md) |
| Latest version | **0.37.10**, released 4 Sep 2026 (0.37.9 same day, 0.37.8 on 27 Aug 2026). **There is no 1.x**; the project is still 0.x. | [PyPI](https://pypi.org/project/c2pa-python/) |
| Python | `requires-python = ">=3.10"` | [pyproject.toml](https://github.com/contentauth/c2pa-python/blob/main/pyproject.toml) |
| License | `MIT OR Apache-2.0` | pyproject.toml |
| Runtime deps | `toml>=0.10.2`, `cryptography>=41.0.0`, `requests>=2.0.0` | pyproject.toml |
| Native core | Prebuilt `c2pa-c-ffi` library from **c2pa-rs `c2pa-v0.90.19`** (file `c2pa-native-version.txt` at tag v0.37.10). `c2pa.sdk_version()` returns it at runtime. | [c2pa-native-version.txt](https://github.com/contentauth/c2pa-python/blob/main/c2pa-native-version.txt) |
| Wheels for 0.37.10 | `py3-none-macosx_10_9_universal2`, `py3-none-macosx_10_9_x86_64`, `py3-none-macosx_11_0_arm64`, `py3-none-manylinux_2_28_x86_64`, `py3-none-manylinux_2_28_aarch64`, `py3-none-win_amd64`, plus sdist. (PyPI's HTML page also lists a Windows ARM64 wheel; the JSON API for 0.37.10 showed only `win_amd64`.) Wheels are `py3-none` (ctypes, no CPython ABI dependency). | PyPI JSON |

The bindings are **ctypes** over the C FFI (`src/c2pa/c2pa.py` is ~4,200 lines wrapping `libc2pa_c`). The package is maintained by Adobe/CAI (Gavin Peacock, Tania Mathern).

### 1.2 API history — what changed and what is current

From [docs/release-notes.md](https://github.com/contentauth/c2pa-python/blob/main/docs/release-notes.md) and the current source:

- **0.3.0**: `c2pa.read_file`, `c2pa.read_ingredient_file`, `c2pa.sign_file` free functions; `C2paSignerInfo(alg, ...)`.
- **0.5.0**: API rewritten to stream-based **Builder / Reader**. `Reader.from_file`, `reader.json()`, `Builder.from_json`, `builder.sign` / `sign_file`, `builder.add_ingredient*`, `builder.add_resource*`, `to_archive`/`from_archive`, and **`create_signer`** which "requires a signing function to keep private keys private". Example signing functions such as `sign_ps256` lived in `c2pa_api.py`.
- **0.6.0**: `c2pa.sign_ps256()` signature changed (PEM string instead of path).
- **0.33.0**: **removed** the deprecated free functions `read_file`, `read_ingredient_file`, `sign_file` and `Builder.add_ingredient_from_file_path`. Migration: `Reader(path).json()`, `Builder.add_ingredient(json, format, stream)`, `Builder.sign_file(src, dst, signer)`.
- **Current (0.37.x)**: `Settings` / `Context` / `ContextBuilder` replace the global `load_settings()` (deprecated). `create_signer()` and `create_signer_from_info()` still exist but emit `DeprecationWarning` and forward to `Signer.from_callback()` / `Signer.from_info()`. `sign_ps256` is gone; there is only a helper `ed25519_sign(data, private_key)` left in the module.

Public surface (`src/c2pa/__init__.py`):

```python
from c2pa import (
    Builder, Reader, Signer, Stream,
    C2paError, C2paSigningAlg, C2paDigitalSourceType, C2paBuilderIntent, C2paSignerInfo,
    Settings, Context, ContextBuilder, ContextProvider,
    sdk_version, load_settings,   # load_settings is deprecated
)
```

Key signatures (verified in `src/c2pa/c2pa.py` on `main`, Sept 2026):

```python
class C2paSigningAlg(enum.IntEnum):  ES256=0, ES384=1, ES512=2, PS256=3, PS384=4, PS512=5, ED25519=6

class C2paDigitalSourceType(enum.IntEnum):
    EMPTY, TRAINED_ALGORITHMIC_DATA, DIGITAL_CAPTURE, COMPUTATIONAL_CAPTURE, NEGATIVE_FILM,
    POSITIVE_FILM, PRINT, HUMAN_EDITS, COMPOSITE_WITH_TRAINED_ALGORITHMIC_MEDIA,
    ALGORITHMICALLY_ENHANCED, DIGITAL_CREATION, DATA_DRIVEN_MEDIA, TRAINED_ALGORITHMIC_MEDIA,
    ALGORITHMIC_MEDIA, SCREEN_CAPTURE, VIRTUAL_RECORDING, COMPOSITE, COMPOSITE_CAPTURE, COMPOSITE_SYNTHETIC

class C2paBuilderIntent(enum.IntEnum):  CREATE=0, EDIT=1, UPDATE=2

C2paSignerInfo(alg, sign_cert: bytes, private_key: bytes, ta_url: bytes|str|None)
    # alg may be a C2paSigningAlg, a str ("es256") or bytes (b"ps256")

Signer.from_info(signer_info) -> Signer
Signer.from_callback(callback: Callable[[bytes], bytes], alg: C2paSigningAlg,
                     certs: str,              # PEM chain
                     tsa_url: Optional[str] = None) -> Signer
signer.reserve_size() -> int

Builder(manifest_json: str | dict, context: ContextProvider | None = None)
Builder.from_json(manifest_json, context=None)          # same thing
Builder.from_archive(stream)
builder.set_intent(intent: C2paBuilderIntent, digital_source_type=C2paDigitalSourceType.EMPTY)
builder.set_no_embed();  builder.set_remote_url(url)
builder.add_resource(uri, stream)
builder.add_ingredient(ingredient_json: str|dict, format: str, source: stream)   # == add_ingredient_from_stream
builder.add_action(action_json: str|dict)
builder.to_archive(stream); builder.with_archive(stream); builder.add_ingredient_from_archive(stream)
builder.sign(signer, format, source, dest=None) -> bytes   # returns the manifest-store bytes
builder.sign(format, source, dest=None) -> bytes           # uses the Context's signer
builder.sign_file(source_path, dest_path, signer=None) -> bytes
    # A Builder is single-use: it is closed after sign().

Reader(path, context=ctx)                       # file path
Reader("image/png", stream, context=ctx)        # format + stream
Reader(stream)                                  # auto-detect
Reader(format_or_path, stream, manifest_data)   # sidecar manifest bytes
Reader.try_create(...) -> Reader | None         # None instead of ManifestNotFound
reader.json() -> str;  reader.detailed_json() -> str;  reader.crjson() -> str
reader.get_active_manifest() -> dict|None;  reader.get_manifest(label)
reader.get_validation_state() -> "Invalid"|"Valid"|"Trusted"|None
reader.get_validation_results() -> dict|None
reader.resource_to_stream(uri, stream) -> int;  reader.is_embedded();  reader.get_remote_url()
Reader.get_supported_mime_types();  Builder.get_supported_mime_types()

Settings(); Settings.from_json(str); Settings.from_dict(dict); settings.set("builder.thumbnail.enabled","false"); settings.update({...})
Context(settings=None, signer=None); Context.from_dict(dict); Context.from_json(str); Context.builder().with_settings(s).with_signer(sig).build()
```

All of `Builder`, `Reader`, `Signer`, `Context`, `Settings` are context managers. A `Signer` handed to a `Context` is **consumed** (do not reuse it). An explicit signer passed to `sign()` takes precedence over the Context's signer.

Supported formats (c2pa-rs [docs/supported-formats.md](https://github.com/contentauth/c2pa-rs/blob/main/docs/supported-formats.md)): `png` (`image/png`), `jpg/jpeg` (`image/jpeg`), `webp` (`image/webp`), `avif`, `gif`, `heic/heif`, `jxl`, `tif/tiff`, `dng`, `svg`, `mp4/mov`, `mp3/wav/flac/m4a`, `pdf` (read-only), `c2pa` sidecar. When both a path and a MIME type exist, the extension wins; otherwise the format hint; otherwise byte-sniffing.

### 1.3 Local signer from PEM cert chain + private key

```python
import c2pa
signer_info = c2pa.C2paSignerInfo(
    alg=c2pa.C2paSigningAlg.ES256,          # or "es256" / b"ps256" / ED25519
    sign_cert=open("chain.pem", "rb").read(),   # end-entity cert FIRST, then intermediates; root optional/omitted
    private_key=open("key.pem", "rb").read(),   # PKCS#8 PEM ("BEGIN PRIVATE KEY")
    ta_url="http://timestamp.digicert.com",     # RFC 3161 TSA, or None
)
signer = c2pa.Signer.from_info(signer_info)
```

`alg` must match the key: `es256` = ECDSA P-256/SHA-256, `es384`, `es512`, `ps256/384/512` = RSASSA-PSS, `ed25519`. The chain "must start with the end-entity certificate used to sign the claim and end with the intermediate certificate before the root CA" ([c2patool docs/signing.md](https://github.com/contentauth/c2patool/blob/main/docs/signing.md)).

Equivalent declarative form (recommended in the docs) via Settings — no `Signer` object needed:

```python
ctx = c2pa.Context.from_dict({
    "signer": {"local": {"alg": "es256", "sign_cert": chain_pem_str,
                         "private_key": key_pem_str, "tsa_url": "http://timestamp.digicert.com"}}
})
with c2pa.Builder(manifest, context=ctx) as b:
    b.sign("image/png", src, dst)      # no signer argument
```
There is also `"signer": {"remote": {"alg","url","sign_cert","tsa_url"}}` where the SDK POSTs the bytes-to-sign to `url` and expects raw signature bytes back ([docs/context-settings.md](https://github.com/contentauth/c2pa-python/blob/main/docs/context-settings.md)).

### 1.4 Callback signing (HSM / KMS / keychain)

`Signer.from_callback(callback, alg, certs, tsa_url)` — the SDK calls `callback(data: bytes) -> bytes` with the bytes to be signed (the wrapper rejects inputs > 1 MB and treats an empty/None return or an exception as a signing error, returning -1 to native code). The callback must return the **raw signature**; for EC keys c2pa-rs accepts both DER and IEEE P1363 (release note 0.5.2: "Allow EC signatures in DER format from signers"), which is why the official example can return `cryptography`'s DER output directly. The `certs` argument is the PEM chain as `str`; `tsa_url` must start with `http://` or `https://`.

Official example ([examples/sign.py](https://github.com/contentauth/c2pa-python/blob/main/examples/sign.py)):

```python
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

def callback_signer_es256(data: bytes) -> bytes:
    private_key = serialization.load_pem_private_key(key_pem, password=None)
    return private_key.sign(data, ec.ECDSA(hashes.SHA256()))   # DER-encoded ECDSA sig is accepted

with c2pa.Context() as context, \
     c2pa.Signer.from_callback(callback_signer_es256, c2pa.C2paSigningAlg.ES256,
                               certs.decode(), "http://timestamp.digicert.com") as signer, \
     c2pa.Builder(manifest_definition, context) as builder:
    builder.sign_file("A.jpg", "A_signed.jpg", signer)
```

For PS256 use `padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32)` with `hashes.SHA256()` (as in [examples/training.py](https://github.com/contentauth/c2pa-python/blob/main/examples/training.py) comments). AWS KMS pattern (from the [c2pa-python-example](https://github.com/contentauth/c2pa-python-example) architecture, which builds a Signer via `Signer.from_callback` and delegates to boto3): `kms.sign(KeyId=..., Message=data, MessageType="RAW", SigningAlgorithm="ECDSA_SHA_256")["Signature"]` for ES256, or `"RSASSA_PSS_SHA_256"` for PS256; the certificate chain for the KMS key comes from a CSR you issue (`setup.py create-key-and-csr`). Note the same repo explains that KMS returns DER-encoded keys/signatures and "the CAI open-source SDK automatically converts it to a supported format".

### 1.5 Complete working example for the latest API (ComfyUI-style, PNG/JPEG/WebP)

```python
"""Sign an AI-generated image with a C2PA manifest using c2pa-python >= 0.37."""
import io, json, uuid, datetime as dt
import c2pa

MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}

def build_manifest(*, provider, tool_name, tool_version, model_name, seed, prompt_hash,
                   title, mime, do_not_train=True, extra=None):
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    gen_id = str(uuid.uuid4())
    manifest = {
        # claim_version 2 is the default; omit for v2
        "claim_generator_info": [{"name": tool_name, "version": tool_version}],
        "title": title,
        "format": mime,
        "assertions": [
            {   # inception action — MUST be first; v2 label
                "label": "c2pa.actions.v2",
                "data": {
                    "actions": [{
                        "action": "c2pa.created",
                        "when": now,
                        "digitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia",
                        "softwareAgent": {"name": f"{tool_name} ({model_name})", "version": tool_version},
                        "parameters": {"org.comfyui.model": model_name,
                                       "org.comfyui.generation_id": gen_id},
                    }],
                    "allActionsIncluded": True,
                },
            },
            {   # custom assertion (reverse-DNS label). kind Json keeps it readable in viewers.
                "label": "org.comfyui.generation",
                "kind": "Json",
                "data": {
                    "provider": provider,            # SB 942 (A)
                    "system": {"name": tool_name, "version": tool_version},   # SB 942 (B)
                    "model": model_name,
                    "created": now,                  # SB 942 (C)
                    "id": gen_id,                    # SB 942 (D)
                    "seed": seed,
                    "prompt_sha256": prompt_hash,    # store a hash, not the prompt, unless the user opts in
                    **(extra or {}),
                },
            },
        ],
    }
    if do_not_train:
        manifest["assertions"].append({
            "label": "cawg.training-mining",
            "data": {"entries": {
                "cawg.ai_generative_training": {"use": "notAllowed"},
                "cawg.ai_training":            {"use": "notAllowed"},
                "cawg.ai_inference":           {"use": "notAllowed"},
                "cawg.data_mining":            {"use": "notAllowed"},
            }},
        })
    return manifest

def make_signer(chain_pem: bytes, key_pem: bytes, alg="es256", tsa="http://timestamp.digicert.com"):
    return c2pa.Signer.from_info(c2pa.C2paSignerInfo(alg=alg, sign_cert=chain_pem,
                                                     private_key=key_pem, ta_url=tsa))

def sign_bytes(image_bytes: bytes, ext: str, manifest: dict, signer: c2pa.Signer,
               parent_bytes: bytes | None = None, parent_ext: str | None = None) -> bytes:
    """Return the signed asset bytes. `parent_bytes` = img2img input (becomes a parentOf ingredient)."""
    mime = MIME[ext.lower()]
    settings = c2pa.Settings.from_dict({
        "builder": {"thumbnail": {"enabled": True, "long_edge": 512}},
        # "verify": {"verify_after_sign": True}  # default; SDK re-validates what it wrote
    })
    with c2pa.Context(settings) as ctx, c2pa.Builder(manifest, ctx) as builder:
        if parent_bytes is not None:
            # img2img: declare the input as parent ingredient and link an opened action to it
            builder.add_ingredient({"title": "input image", "relationship": "parentOf",
                                    "instance_id": "xmp.iid:" + str(uuid.uuid4()),
                                    "label": "input_image"},
                                   MIME[parent_ext.lower()], io.BytesIO(parent_bytes))
        src, dst = io.BytesIO(image_bytes), io.BytesIO()
        builder.sign(signer, mime, src, dst)          # returns manifest bytes; dst holds the asset
        return dst.getvalue()

def read_and_check(signed: bytes, mime: str, trust_anchors_pem: str | None = None) -> dict:
    conf = {"verify": {"verify_cert_anchors": True}}
    if trust_anchors_pem:
        conf["trust"] = {"user_anchors": trust_anchors_pem}   # add your test root without replacing the built-ins
    with c2pa.Context(c2pa.Settings.from_dict(conf)) as ctx, \
         c2pa.Reader(mime, io.BytesIO(signed), context=ctx) as reader:
        store = json.loads(reader.json())
        return {"state": reader.get_validation_state(),          # Invalid | Valid | Trusted
                "results": reader.get_validation_results(),
                "active": store["manifests"][store["active_manifest"]]}
```

Notes for the img2img case: when a `parentOf` ingredient exists the first action must be `c2pa.opened` (not `c2pa.created`) with `parameters.ingredientIds` pointing at the ingredient's `instance_id`/`label`, and `digitalSourceType` on subsequent generative actions should be `compositeWithTrainedAlgorithmicMedia` (see §2.2). The simplest way to get this right is the **intent** API: `builder.set_intent(C2paBuilderIntent.EDIT)` auto-creates the parent from the source stream and adds the `c2pa.opened` action; `set_intent(C2paBuilderIntent.CREATE, C2paDigitalSourceType.TRAINED_ALGORITHMIC_MEDIA)` auto-adds `c2pa.created` for txt2img (Create "must not have a parent ingredient") — [docs/intents.md](https://github.com/contentauth/c2pa-python/blob/main/docs/intents.md). The docs state that the explicit-JSON form and the intent form "produce the same signed manifest".

ComfyUI-specific pitfalls (confirmed by the existing [mikecaronna/comfyui_c2pa_signer](https://github.com/mikecaronna/comfyui_c2pa_signer) node, which shells out to `c2patool`): the signed file must be the **last** writer — ComfyUI's `SaveImage` re-encodes with PIL and drops the C2PA chunk (`caBX` in PNG, APP11 JUMBF in JPEG, `C2PA` chunk in WebP), so the node must write the final file itself (or run after all metadata is in place). Any change to the bytes after signing (adding `tEXt` prompt/workflow chunks, re-saving) breaks the `c2pa.hash.data` binding, so write ComfyUI's PNG `prompt`/`workflow` metadata first, then sign that stream.

### 1.6 `c2patool` CLI fallback

`c2patool` (now its own repo, [contentauth/c2patool](https://github.com/contentauth/c2patool); releases <= v0.27.15 were in c2pa-rs) takes a JSON manifest definition: `c2patool in.png -m manifest.json -o out.png [--create trainedAlgorithmicMedia | --edit | --update] [--signer-path ./my-signer] [--parent parent.jpg]`. Signing config is via `[signer.local]`/`[signer.remote]` in a settings TOML, the manifest fields `alg`/`private_key`/`sign_cert`/`ta_url`, env vars `C2PA_SIGN_CERT`/`C2PA_PRIVATE_KEY`, or a **subprocess signer** protocol (`--signer-info` returns `{alg, sign_cert, tsa_url, reserve_size}`; bytes on stdin -> raw signature on stdout). If nothing is configured it uses a built-in test cert with a warning. `c2patool init trust` caches the official trust list; `c2patool file trust --trust_anchors ...` enables trust checks. Reading: `c2patool file.png` (summary JSON), `-d` (detailed), `--certs` (dump chain). ([docs/usage.md](https://github.com/contentauth/c2patool/blob/main/docs/usage.md), [docs/manifest.md](https://github.com/contentauth/c2patool/blob/main/docs/manifest.md), [docs/signing.md](https://github.com/contentauth/c2patool/blob/main/docs/signing.md)). Homebrew: `brew install c2patool`.

---

## 2. Manifest JSON for an AI-generated image

### 2.1 Top-level manifest definition

From the SDK's `ManifestDefinition.schema.json` (docs-site `static/schemas`) and c2pa-rs `builder.rs`:

| Field | Meaning |
|---|---|
| `claim_version` | default **2** (v2 claims, C2PA 2.x); set `1` only for legacy consumers |
| `claim_generator_info` | **array** of `{name, version?, icon?{format,identifier}, operating_system?, specVersion?}`. If omitted, filled from `builder.claim_generator_info` in settings, else the library default. The legacy string `claim_generator` ("MyApp/1.0 c2pa-rs/x.y") is derived/reported by readers. |
| `vendor` | reverse-domain prefix for the manifest label (optional) |
| `title` | human-readable title (typically the filename) |
| `format` | MIME of the source asset |
| `instance_id` | `xmp:iid:<uuid>` (auto-generated if omitted) |
| `thumbnail` | `{format, identifier}` resource ref; the SDK auto-generates thumbnails by default (`builder.thumbnail.enabled`) |
| `ingredients` | list of `Ingredient` (`title, format, instance_id, relationship: parentOf|componentOf|inputTo, label, digital_source_type, thumbnail, ...`) — usually added via `add_ingredient()` |
| `assertions` | list of `{label, data, kind?: "Cbor"|"Json"|"Binary"|"Uri" (default Cbor), created?: bool}` |
| `redactions`, `label`, `hash_alg`, `metadata` | optional |

`created: true` marks a *created assertion* (attributed to the signer) versus a *gathered assertion*; by default the hard binding is created and everything else gathered, and settings `builder.created_assertion_labels` can override. Typical: actions/ingredients/thumbnails created, `cawg.training-mining`/`cawg.metadata` gathered ([assertions-actions.md](https://github.com/contentauth/opensource.contentauth.org/blob/main/docs/manifest/writing/assertions-actions.md)).

### 2.2 Actions assertion (`c2pa.actions.v2`)

- Use label **`c2pa.actions.v2`** (v1 `c2pa.actions` is still written by some producers; c2pa-rs serializes with `LABEL_VERSIONED = "c2pa.actions.v2"` and `ASSERTION_CREATION_VERSION = 2`).
- "Every manifest has to start with either an opened or created action, which has to be the first action" and `c2pa.opened`/`c2pa.placed`/`c2pa.transcoded`/`c2pa.repackaged` **must** reference ingredients via `parameters.ingredientIds` (the old `ingredientId`/`instanceId` are deprecated; c2pa-rs also accepts `parameters.org.cai.ingredientIds`).
- Action object fields: `action`, `digitalSourceType` (IPTC URI), `softwareAgent` (**in v2 an object with the `ClaimGeneratorInfo` shape**: `{name, version, ...}`; a plain string is still accepted by c2pa-rs for compatibility), `softwareAgentIndex` (index into a `softwareAgents` array), `parameters` (free-form, incl. `description`, `ingredientIds`), `when` (RFC 3339), `changes`/regions, plus `templates` and `allActionsIncluded` at the assertion level.
- Generative AI: `c2pa.created` + `digitalSourceType: http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia` for a fully generated asset; `compositeWithTrainedAlgorithmicMedia` when generative output is composited with other media (inpainting/outpainting/img2img); `compositeSynthetic` / `composite` for mixes; `algorithmicallyEnhanced` for AI upscaling/enhancement. Full list in c2pa-rs `DigitalSourceType` enum (also C2PA-specific `http://c2pa.org/digitalsourcetype/trainedAlgorithmicData` and `.../empty`). Note IPTC retired `digitalArt` and `minorHumanEdits` in favour of `digitalCreation` and `humanEdits`.

```json
{
  "label": "c2pa.actions.v2",
  "data": {
    "actions": [
      {
        "action": "c2pa.created",
        "digitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia",
        "softwareAgent": { "name": "ComfyUI", "version": "0.3.60" },
        "when": "2026-09-13T10:15:00Z",
        "parameters": { "org.comfyui.model": "flux1-dev.safetensors" }
      }
    ],
    "allActionsIncluded": true
  }
}
```

img2img / inpainting (manual form):

```json
"ingredients": [{ "title": "input.png", "format": "image/png", "relationship": "parentOf",
                  "instance_id": "xmp.iid:7f136ee1-6e84-4d80-9de3-e1180ef2b690" }],
"assertions": [{ "label": "c2pa.actions.v2", "data": { "actions": [
  { "action": "c2pa.opened", "parameters": { "ingredientIds": ["xmp.iid:7f136ee1-6e84-4d80-9de3-e1180ef2b690"] } },
  { "action": "c2pa.edited",
    "digitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/compositeWithTrainedAlgorithmicMedia",
    "softwareAgent": { "name": "ComfyUI", "version": "0.3.60" },
    "parameters": { "description": "img2img, denoise 0.6" } }
]}}]
```
(With `add_ingredient()` the ingredient bytes are hashed and, if the input already carries a manifest, its provenance chain is nested.)

### 2.3 Which "AI" assertions are current

| Label | Status (Sept 2026) |
|---|---|
| `c2pa.actions.v2` with `digitalSourceType` | **The** normative way to say "AI-generated". |
| `cawg.training-mining` | **Current** do-not-train / do-not-mine assertion (CAWG Training and Data Mining Assertion v1.1, DIF-ratified 16 May 2025). Entries `cawg.ai_generative_training`, `cawg.ai_training`, `cawg.ai_inference`, `cawg.data_mining`, each `{"use": "allowed" | "notAllowed" | "constrained", "constraint_info"?: "..."}`. |
| `c2pa.training-mining` | previous label of the same assertion — replaced by `cawg.training-mining`. |
| `c2pa.ai_generative_training`, `c2pa.ai_training`, `c2pa.ai_inference`, `c2pa.data_mining` | **Deprecated** individual assertions (C2PA 1.x) — "have been replaced by CAWG training and data mining assertions". Do not write them. |
| `com.adobe.generative-ai` | Adobe-private custom assertion from early Firefly builds; not a standard. Firefly today expresses the same thing via `c2pa.created` + `softwareAgent: "Adobe Firefly"` + `parameters.com.adobe.firefly.*` (see §6). |
| `stds.schema-org.CreativeWork` (author) | **Legacy**. C2PA 2.2 replaced the Exif/IPTC/CreativeWork assertions with the `c2pa.metadata` assertion (restricted field list) and CAWG's unrestricted `cawg.metadata`; the docs say "the CreativeWork assertion is not supported at all" in the latest SDK, although c2pa-rs's builder still has a deprecated typed path for it. For authorship prefer `cawg.metadata` (`dc:creator`) or the CAWG identity assertion. |
| `stds.exif`, `stds.iptc` | still recognised; now considered CAWG metadata assertions (JSON-LD with `@context`). |

Do-not-train example (from the official `training.py`):

```json
{ "label": "cawg.training-mining",
  "data": { "entries": {
    "cawg.ai_inference": { "use": "notAllowed" },
    "cawg.ai_generative_training": { "use": "notAllowed" },
    "cawg.data_mining": { "use": "constrained", "constraint_info": "Contact licensing@example.com" } } } }
```

### 2.4 Recording model / prompt / author

- **Custom assertion**: any reverse-DNS label, e.g. `org.comfyui.generation`, `kind: "Json"` (readable in inspectors) or default CBOR. c2pa-rs stores unknown labels through the generic `User`/`UserCbor` path verbatim. Suggested payload: `model`, `model_hash`, `sampler`, `steps`, `cfg`, `seed`, `prompt` or `prompt_sha256`, `negative_prompt`, `workflow_sha256`, `comfyui_version`, `generation_id`. The existing ComfyUI signer node embeds the full workflow as `com.comfyui.workflow`; be deliberate about privacy (prompts can contain personal data and are permanent once signed).
- **Action parameters**: Firefly puts `com.adobe.firefly.version` / `com.adobe.firefly.operation` inside `parameters` of the `c2pa.created` action; the same pattern (`org.comfyui.model`, `org.comfyui.seed`) keeps model info next to the action that used it.
- **Metadata assertions**: `c2pa.metadata` (C2PA 2.2) only permits an allow-listed set of Exif/IPTC/XMP fields; anything else goes in `cawg.metadata` (no restrictions). Example gathered assertion:

```json
{ "label": "cawg.metadata", "created": false,
  "data": { "@context": { "dc": "http://purl.org/dc/elements/1.1/", "xmp": "http://ns.adobe.com/xap/1.0/",
                           "Iptc4xmpExt": "http://iptc.org/std/Iptc4xmpExt/2008-02-29/" },
            "dc:creator": ["Jane Doe"], "xmp:CreatorTool": "ComfyUI 0.3.60",
            "Iptc4xmpExt:DigitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia" } }
```

### 2.5 California SB 942 latent-disclosure fields -> manifest mapping

Statute (Bus. & Prof. Code §22757.3, as enacted by SB 942, Stats. 2024 ch. 291; text from a [GitHub mirror of the code section](https://github.com/jbloewencolon/regs-checker/blob/main/output/law_texts/TMP-CA-AITRANSPARENCY.txt)):

> (b) A covered provider shall include a latent disclosure in AI-generated image, video, or audio content ... that meets all of the following criteria: (1) To the extent that it is technically feasible and reasonable, the disclosure conveys all of the following information, either directly or through a link to a permanent internet website: (A) The name of the covered provider. (B) The name and version number of the GenAI system that created or altered the content. (C) The time and date of the content's creation or alteration. (D) A unique identifier. (2) The disclosure is detectable by the covered provider's AI detection tool. (3) The disclosure is consistent with widely accepted industry standards. (4) The disclosure is permanent or extraordinarily difficult to remove, to the extent it is technically feasible.

Definitions: "Covered provider" = producer of a GenAI system with > 1,000,000 monthly visitors/users, publicly accessible in California; "Latent" = present but not manifest; "Manifest" = easily perceived by a natural person; §22757.3(a) also requires offering an optional *manifest* (visible) disclosure. **AB 853 (signed 13 Oct 2025)** moved the operative date from 1 Jan 2026 to **2 Aug 2026**, extends duties to large online platforms (2027) and capture-device makers (2028), and — per the amended bill text on GitHub — rewrites (b) as new subdivision (a) with item **(E) "Whether the content is generated or modified by artificial intelligence"**, "altered, except by minor modification", and "permanent or extraordinarily difficult to remove *or tamper with*" ([AB 853 bill text mirror](https://github.com/aaronjuar-ez/PUBINFO-2025); summaries: [Hintze Law](https://hintzelaw.com/blog/2025/10/19/california-amends-artificial-intelligence-transparency-act-and-passes-ai-defenses-act), [CASRAI](https://casrai.org/news/california-sb-942-ai-transparency-act-effective-august-2026) (snippets)). Penalty: $5,000 per violation per day (snippet).

Mapping into C2PA:

| SB 942 item | C2PA field(s) |
|---|---|
| (A) provider name | signing certificate `O=` (shown as `signature_info.issuer`/`common_name`), `claim_generator_info[0].name`, plus your custom assertion `provider` |
| (B) system name + version | `claim_generator_info[].name/version` and `actions[].softwareAgent{name,version}` (and `parameters.org.comfyui.model`) |
| (C) time and date | claim signature time (`signature_info.time`), RFC 3161 timestamp (`ta_url`), `actions[].when` |
| (D) unique identifier | manifest label `urn:uuid:...`, `instance_id` (`xmp:iid:...`), and/or your own `generation_id`; for durability also encode it in the watermark payload (soft binding, §3) |
| (E) AI-generated flag | `digitalSourceType: trainedAlgorithmicMedia` (or `compositeWith...`) |
| "consistent with widely accepted industry standards" / "difficult to remove" | C2PA manifest + a registered soft-binding watermark ("Durable Content Credentials") |

Only providers over the 1M-user threshold are "covered providers"; a ComfyUI node itself is not, but the same fields are what downstream platforms (2027) must detect and display.

---

## 3. Soft bindings (watermarks) and Durable Content Credentials

### 3.1 The `c2pa.soft-binding` assertion

Structure (c2pa-rs `sdk/src/assertions/soft_binding.rs`, mirroring spec CDDL `soft-binding-map`; also the crJSON schema):

```jsonc
{ "label": "c2pa.soft-binding",
  "data": {
    "alg": "com.adobe.trustmark.Q",       // REQUIRED: identifier from the C2PA Soft Binding Algorithm List
                                          //   (if absent, taken from the claim's alg_soft; no default)
    "alg-params": <bstr>,                 // optional, algorithm-specific parameters
    "name": "human readable",             // optional
    "blocks": [                           // REQUIRED, >= 1
      { "scope": {                        // REQUIRED (may be empty = whole asset)
          "timespan": { "start": 0, "end": 1000 },   // ms, temporal media
          "region": { ... region-of-interest ... }   // spatial ("extent" is deprecated)
        },
        "value": <bstr>                   // REQUIRED: the soft-binding value in algorithm-specific format
      }
    ],
    "pad": <bstr>, "pad2": <bstr>,        // zero fill (multi-step processing; unused by c2pa-rs)
    "bindingMetadata": { "description": "...", "contact": "...", "informationalUrl": "..." }
  } }
```

Semantics (C2PA 2.x, "Content bindings"): a hard binding (`c2pa.hash.data`) proves the exact bytes; a **soft binding** is a perceptual identifier — a watermark payload or a fingerprint — that survives re-encoding, and "enhance[s] the durability of content credentials by enabling the discovery of the C2PA Manifest Store if it is not embedded in an asset." The watermark carries an identifier used "as a key to lookup the C2PA Manifest within a manifest repository", and the **C2PA Soft Binding Resolution API** (spec: `spec.c2pa.org/.../softbinding/Decoupled.html`; Adobe runs one at `developer.adobe.com/cai-soft-binding-api/`) standardises that lookup across repositories. Adobe/CAI brand this as [Durable Content Credentials](https://contentauthenticity.org/blog/durable-content-credentials). A soft binding is never the sole content binding (a hard binding is still required) and validators are not required to recompute it — c2pa-rs reads/reports it and only checks structure; its only related status code is `assertion.action.softBindingMissing` (an action that claims a watermark without a soft-binding assertion).

Actions: `c2pa.watermarked` was the 1.x action; c2pa-rs `claim.rs` notes it "is deprecated for producing new content (spec 2.2+)" in favour of **`c2pa.watermarked.bound`** (watermark payload is bound to this manifest — i.e. it carries/points to the manifest identifier) and **`c2pa.watermarked.unbound`** (labels in `actions.rs`). A `watermarked.bound` action must be accompanied by a `c2pa.soft-binding` assertion.

Practical caveat for the Python/JSON path: c2pa-rs's `Builder` has **no typed handling for `c2pa.soft-binding`** — the match in `builder.rs` covers actions, CreativeWork, Exif, box/data/BMFF hashes and `c2pa.metadata`; everything else is serialised generically from your JSON (`kind` default Cbor -> `c2pa_cbor::to_value(json)`). So a JSON string `value` becomes a CBOR **text string** and a JSON array of ints becomes a CBOR **array**, whereas the CDDL says `bstr`. An independent Go implementation that probed c2patool 0.27.16 (Sept 2026) reports exactly this: the generic path "cannot write one correctly ... `"value": [1,2,3,4]` ... become CBOR ARRAYS", while c2patool reads such assertions back and leaves `validation_state: Trusted` ([richardwooding/c2pa notes](https://github.com/richardwooding/c2pa/blob/main/CLAUDE.md)). Adobe's own TrustMark example writes `value` as a text string `"<schema>*<bits>"` through c2patool and it round-trips, so today's ecosystem tolerates a tstr — but strict validators may flag it. If bstr fidelity matters, either open an issue/PR for typed `SoftBinding` support in `Builder` (the typed struct with `serde_bytes` already exists in c2pa-rs) or sign the manifest through a path that lets you supply the CBOR yourself.

### 3.2 The Soft Binding Algorithm List and TrustMark

Authoritative registry: [c2pa-org/softbinding-algorithm-list](https://github.com/c2pa-org/softbinding-algorithm-list) (`softbinding-algorithm-list.json`), **53 entries** as of Sept 2026, each `{identifier, alg, type: watermark|fingerprint, decodedMediaTypes, entryMetadata}`. Image-capable watermark algorithms include: `com.digimarc.validate.1` (#1), `com.adobe.trustmark.Q` (#4), `com.adobe.trustmark.C` (#5), `com.adobe.trustmark.P` (#13), `ai.steg.api`, `ai.trufo.pawprint.watermark`, `app.overlai.watermark.1`, `com.imatag.lamark.v1`, `com.microsoft.invismark.1` (#19), `com.aiwatermark.pixelseal.1` (Meta PixelSeal), `me.reconize.videoseal.1`, `com.museblossom.contentsdefence.1`, `es.lumatrace`, `com.markany.watermark.1`, ...; fingerprints include `io.iscc.v0` (ISO 24138 ISCC), `com.adobe.icn.dense`, `com.joinmonolith.sha256`. Google's SynthID is **not** on the list, so SynthID cannot be expressed as an `alg` value.

TrustMark ([adobe/trustmark](https://github.com/adobe/trustmark), MIT): 100-bit payload with BCH error-correction schemas (`BCH_SUPER`, `BCH_5`, `BCH_4`, `BCH_3`, chosen by 2 version bits); variants Q/C/P are the registered C2PA algorithms (B is the newer "signpost" model used by provcheck). Its [c2pa/c2pa_watermark_example.py](https://github.com/adobe/trustmark/blob/main/c2pa/c2pa_watermark_example.py) generates a random ID of `tm.schemaCapacity()` bits, encodes it (`tm.encode(rgb, id, MODE='binary')`), and writes:

```json
{ "label": "c2pa.soft-binding",
  "data": { "alg": "com.adobe.trustmark.Q",
            "blocks": [ { "scope": {}, "value": "2*0110100101..." } ] } }
```
with an action `c2pa.watermarked`, then signs via c2patool. The TrustMark README/FAQ also documents a "signpost" mode (`Encoding.BCH_SUPER`) where the payload is the integer `identifier` of another registered watermark from the list, telling a verifier which decoder to run. TrustMark modifies pixels only, so you must carry EXIF/ICC yourself; re-sign after watermarking (watermark first, then C2PA), because the hard binding hashes the watermarked pixels.

For a ComfyUI node: embed TrustMark (or another listed algorithm) with a payload that encodes your `generation_id` (or a DB key), record `c2pa.soft-binding{alg, blocks[].value}` + `c2pa.watermarked.bound`, keep a copy of the manifest store bytes returned by `builder.sign()` in a repository keyed by that payload, and you have a recoverable credential after metadata stripping. provcheck v1.4.0 already ships a ComfyUI node doing TrustMark-B + C2PA ([CreativeMayhemLtd/provcheck](https://github.com/CreativeMayhemLtd/provcheck)).

---

## 4. Test certificates with OpenSSL (ES256)

### 4.1 Requirements

Facts established from primary sources:

- The reference test leaf cert (c2pa-rs `sdk/tests/fixtures/certs/es256.pub`, same as c2pa-python `tests/fixtures/es256_certs.pem`) has: `Basic Constraints: critical, CA:FALSE`; `Extended Key Usage: critical, E-mail Protection`; `Key Usage: critical, Digital Signature, Non Repudiation`; SKI/AKI; issued by an intermediate CA (`CA:TRUE`) under a root; signature `ecdsa-with-SHA256`. The `.pub` chain file contains **leaf + intermediate only**; the root is distributed separately (`es256_root.pub_key`) as a trust anchor. ([certs README](https://github.com/contentauth/c2pa-rs/blob/main/sdk/tests/fixtures/certs/README.md))
- c2pa-rs's built-in ephemeral cert generator (`sdk/src/utils/ephemeral_cert.rs`) issues EE certs with Key Usage `digitalSignature`, EKU `id-kp-emailProtection` (1.3.6.1.5.5.7.3.4) **and** `anyExtendedKeyUsage` (1.3.6.1.5.5.7.3.0), Basic Constraints `cA=FALSE` encoded explicitly, 365-day validity, chained to a generated CA.
- Accepted EKUs in the SDK's default trust config (seen in c2pa-min/c2pa-rs settings fixtures): `id-kp-emailProtection 1.3.6.1.5.5.7.3.4`, `id-kp-documentSigning 1.3.6.1.5.5.7.3.36`, `id-kp-timeStamping .8`, `id-kp-OCSPSigning .9`, `MS C2PA Signing 1.3.6.1.4.1.311.76.59.1.9`, and the conformance-program **C2PA claim-signing EKU `1.3.6.1.4.1.62558.2.1`** (production certs from the C2PA trust list use this; the conformance tool notes c2pa-rs "accepts [emailProtection] unconditionally regardless of `trust_config`"). `trust.trust_config` in Settings can extend the EKU allow-list.
- The docs are explicit: "**The CAI SDK does not allow you to use a self-signed certificate to sign a manifest**" ([test-certs.md](https://github.com/contentauth/opensource.contentauth.org/blob/main/docs/signing/test-certs.md)) — so generate a two-level chain (test root CA -> leaf), never a single self-signed leaf. Private keys should be PKCS#8 PEM. ES256/384/512 signatures must be IEEE P1363 in the manifest (the SDK converts DER for you).

### 4.2 Recipe (adapted from the [c2pa-conformance-tool EKU fixtures README](https://github.com/contentauth/c2pa-conformance-tool/blob/main/wasm/tests/fixtures/eku/README.md), which is the closest thing to an official OpenSSL script; the `testing-private` cert-generation repo referenced by the docs is not public)

```bash
# 1) Test root CA (EC P-256). Keep it offline; it is your trust anchor.
openssl ecparam -name prime256v1 -genkey -noout -out root_key.pem
openssl req -x509 -new -key root_key.pem -sha256 -days 3650 \
  -subj "/C=US/O=My ComfyUI Test CA/OU=FOR TESTING ONLY/CN=ComfyUI Test Root CA" \
  -addext "basicConstraints=critical,CA:true" \
  -addext "keyUsage=critical,keyCertSign,cRLSign" \
  -out root_cert.pem

# 2) Leaf (claim-signing) key, converted to PKCS#8, and CSR
openssl ecparam -name prime256v1 -genkey -noout -out leaf_key_sec1.pem
openssl pkcs8 -topk8 -nocrypt -in leaf_key_sec1.pem -out es256_private.key
openssl req -new -key es256_private.key \
  -subj "/C=US/O=My Org (Test)/OU=FOR TESTING ONLY/CN=ComfyUI C2PA Signer" -out leaf.csr

# 3) Leaf extensions: not a CA, digitalSignature, EKU emailProtection (test) — production
#    certs from a C2PA-listed CA carry the claim-signing EKU 1.3.6.1.4.1.62558.2.1 instead.
cat > leaf_ext.cnf <<'EOF'
basicConstraints=critical,CA:false
keyUsage=critical,digitalSignature,nonRepudiation
extendedKeyUsage=critical,emailProtection
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid,issuer
EOF
openssl x509 -req -in leaf.csr -CA root_cert.pem -CAkey root_key.pem -CAcreateserial \
  -days 825 -sha256 -extfile leaf_ext.cnf -out leaf_cert.pem

# 4) Chain file handed to c2pa: end-entity first, then intermediates (root not required)
cat leaf_cert.pem > es256_certs.pem            # add intermediate(s) here if you have a 3-tier chain
openssl verify -CAfile root_cert.pem leaf_cert.pem
```

Use `alg="es256"` with `sign_cert=es256_certs.pem`, `private_key=es256_private.key`. For RSA/PS256: `openssl genpkey -algorithm RSA-PSS -pkeyopt rsa_keygen_bits:3072 ...` (or a plain RSA key; the SDK signs RSASSA-PSS regardless), and for Ed25519: `openssl genpkey -algorithm ed25519`. OpenSSL >= 3.0 is recommended (`-addext`/`-copy_extensions`).

### 4.3 The trust caveat

Signing with this chain produces a manifest whose `validation_state` is **`Valid`** (cryptographically correct) but **not `Trusted`**: `signingCredential.untrusted` appears unless the verifier has your root in `trust.user_anchors`/`trust_anchors` (or the leaf in `trust.allowed_list`). Public verifiers show "The Content Credential issuer couldn't be recognized" / "unknown source". Only certificates chaining to the **C2PA Trust List** ([conformance-public/trust-list/C2PA-TRUST-LIST.pem](https://github.com/c2pa-org/conformance-public/blob/main/trust-list/C2PA-TRUST-LIST.pem), issued by listed CAs — DigiCert, SSL.com, Tauth Labs, Trufo as of Apr 2026 — to products that pass the C2PA conformance program) validate as trusted in conformant validators; the legacy Interim Trust List (`https://contentcredentials.org/trust/anchors.pem` + `allowed.sha256.txt` + `store.cfg`) was **frozen on 1 Jan 2026** and is what the older Verify site (`verify.contentauthenticity.org`) still consults, while Adobe's ACA Inspect (`inspect.cr`) uses the C2PA trust list ([trust-lists.mdx](https://github.com/contentauth/opensource.contentauth.org/blob/main/docs/conformance/trust-lists.mdx), [get-cert.md](https://github.com/contentauth/opensource.contentauth.org/blob/main/docs/signing/get-cert.md)). Timestamps have their own list (`C2PA-TSA-TRUST-LIST.pem`); a TSA not on the configured list yields informational `timeStamp.untrusted`.

---

## 5. Verifying / reading manifests in Python; validation codes

```python
import json, urllib.request, c2pa

anchors = urllib.request.urlopen(
    "https://raw.githubusercontent.com/c2pa-org/conformance-public/refs/heads/main/trust-list/C2PA-TRUST-LIST.pem"
).read().decode()

settings = c2pa.Settings.from_dict({
    "verify": {"verify_cert_anchors": True, "verify_trust": True, "verify_timestamp_trust": True,
               "remote_manifest_fetch": False},       # offline
    "trust": {"trust_anchors": anchors,                # official list (replaces built-ins)
              "user_anchors": open("root_cert.pem").read()},  # plus your dev root
})
with c2pa.Context(settings) as ctx:
    reader = c2pa.Reader.try_create("out.png", context=ctx)   # None if no manifest at all
    if reader is None:
        print("no Content Credentials"); raise SystemExit
    with reader:
        store = json.loads(reader.json())
        active = store["manifests"][store["active_manifest"]]
        print(reader.get_validation_state())            # Invalid | Valid | Trusted
        res = reader.get_validation_results() or {}
        for sev in ("success", "informational", "failure"):
            for e in res.get("activeManifest", {}).get(sev, []):
                print(sev, e["code"], e.get("explanation"), e.get("url"))
        for a in active["assertions"]:
            if a["label"].startswith("c2pa.actions"):
                for act in a["data"]["actions"]:
                    print(act["action"], act.get("digitalSourceType"), act.get("softwareAgent"))
        # thumbnails / resources:
        # reader.resource_to_stream(active["thumbnail"]["identifier"], open("thumb.jpg","wb"))
        print(reader.detailed_json()[:2000])            # claim/assertion-store level view
```

Output shape (`Reader.schema.json`): `{"active_manifest": label, "manifests": {label: Manifest}, "validation_state": ..., "validation_results": {"activeManifest": {"success": [], "informational": [], "failure": []}, "ingredientDeltas": [...], "specVersion", "trustListUri", "timestampTrustListUri"}}`; each entry is `{code, url, explanation, success?}`. `Manifest` has `claim_generator`, `claim_generator_info[]`, `title`, `format`, `instance_id`, `thumbnail`, `ingredients[]`, `assertions[]`, `signature_info {alg, issuer, common_name, cert_serial_number, time, revocation_status}`, `label`, `claim_version`. The old flat `validation_status` array is deprecated in favour of `validation_results` + `validation_state`.

`ValidationState` (c2pa-rs `validation_results.rs`): `Invalid` (malformed, integrity failure, or validation disabled), `Valid` (well-formed and cryptographic checks pass), `Trusted` (valid **and** signer chains to a trust anchor). "Valid but untrusted" is the normal state with test certs.

Status codes (constants in c2pa-rs `sdk/src/validation_results.rs::validation_codes`, matching the spec's success/failure code tables):

- **Success / informational**: `claimSignature.validated`, `claimSignature.insideValidity`, `signingCredential.trusted`, `signingCredential.ocsp.notRevoked`, `signingCredential.ocsp.skipped`, `signingCredential.ocsp.inaccessible`, `timeStamp.validated`, `timeStamp.trusted`, `timeStamp.untrusted`, `timeStamp.mismatch`, `timeStamp.malformed`, `timeStamp.outsideValidity`, `assertion.hashedURI.match`, `assertion.dataHash.match`, `assertion.bmffHash.match`, `assertion.boxesHash.match`, `assertion.collectionHash.match`, `assertion.accessible`, `ingredient.manifest.validated`, `ingredient.claimSignature.validated`, `ingredient.unknownProvenance`, `manifest.unknownProvenance`, `manifest.unreferenced`, `algorithm.deprecated`, `timeOfSigning.insideValidity`.
- **Failure**: `signingCredential.untrusted`, `signingCredential.invalid`, `signingCredential.expired`, `signingCredential.ocsp.revoked`, `signingCredential.ocsp.unknown`, `claimSignature.missing`, `claimSignature.mismatch`, `claimSignature.outsideValidity`, `claim.malformed`, `claim.missing`, `claim.multiple`, `claim.required.missing`, `claim.cbor.invalid`, `claim.hardBindings.missing`, `assertion.multipleHardBindings`, `assertion.hashedURI.mismatch`, `assertion.dataHash.mismatch`, `assertion.dataHash.malformed`, `assertion.dataHash.redacted`, `assertion.bmffHash.mismatch`, `assertion.boxesHash.mismatch`, `assertion.boxesHash.unknownBox`, `assertion.collectionHash.mismatch`, `assertion.missing`, `assertion.undeclared`, `assertion.inaccessible`, `assertion.notRedacted`, `assertion.selfRedacted`, `assertion.required.missing`, `assertion.json.invalid`, `assertion.cbor.invalid`, `assertion.outsideManifest`, `assertion.action.malformed`, `assertion.action.ingredientMismatch`, `assertion.action.redactionMismatch`, `assertion.action.redacted`, `assertion.action.softBindingMissing`, `assertion.metadata.disallowed`, `assertion.ingredient.malformed`, `assertion.cloud-data.*`, `ingredient.hashedURI.mismatch`, `ingredient.manifest.missing`, `ingredient.manifest.mismatch`, `ingredient.claimSignature.missing/mismatch`, `manifest.inaccessible`, `manifest.multipleParents`, `manifest.update.invalid`, `manifest.update.wrongParents`, `manifest.timestamp.invalid/wrongParents`, `manifest.compressed.invalid`, `hashedURI.missing/mismatch`, `algorithm.unsupported`, `general.error`, plus CAWG identity codes `cawg.x509.credential.trusted/untrusted/invalid`, `cawg.x509.signature.validated/mismatch/...`, `cawg.ica.untrusted_issuer`.

`url` values are JUMBF URIs: `self#jumbf=/c2pa/<manifest-label>/c2pa.signature` for credential codes, `self#jumbf=c2pa.assertions/<label>` for assertion codes. Note that c2pa-rs since ~0.23 reports `signingCredential.expired` as a failure when the cert has expired and no trusted timestamp proves the signing time ([c2pa-rs issue #1488](https://github.com/contentauth/c2pa-rs/issues/1488)) — another reason to always set `ta_url`.

---

## 6. How real generators populate their manifests

Real manifests extracted from public repositories:

**OpenAI DALL·E 3 via API + ChatGPT (Feb 2024)** — [Tebs-Lab/lab-report-code cape-bear-manifest.json](https://github.com/Tebs-Lab/lab-report-code/blob/main/2024-03-03/cape-bear-manifest.json). Two nested manifests: the generator manifest and a wrapper added by ChatGPT (webp conversion), both signed `es256`, issuer `OpenAI`:

```json
"claim_generator": "OpenAI-API c2pa-rs/0.28.4", "claim_generator_info": null,
"dc:format": "webp", "dc:title": "image.webp",
"c2pa.actions": { "actions": [
  { "action": "c2pa.created",
    "digitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia",
    "softwareAgent": "DALL·E" },
  { "action": "c2pa.converted" } ] },
"signature": { "alg": "es256", "issuer": "OpenAI", "time": "2024-02-27T01:03:12+00:00" }
```
Wrapper: `"claim_generator": "ChatGPT c2pa-rs/0.28.4"` with a `c2pa.ingredient` (`relationship: parentOf`, `c2pa_manifest` pointing at the inner manifest) and an ingredient thumbnail. Newer (2025–26) ChatGPT/gpt-image output uses `claim_generator_info: [{"name": "ChatGPT", "org.cai.c2pa_rs": "0.49.5"}]`, `c2pa.actions.v2`, `softwareAgent: {"name": "GPT-4o"}` or `{"name": "gpt-image"}` (conformance-tool fixture) and Azure's variant `{"name": "Azure OpenAI ImageGen"}` (snippets + [c2pa-conformance-tool fixture](https://github.com/contentauth/c2pa-conformance-tool/blob/main/src/lib/rubrics/__fixtures__/ingredient_dst_complex.json)). In May 2026 OpenAI joined the C2PA steering committee and announced SynthID watermarking alongside C2PA (snippet).

**Adobe Firefly (Oct 2025)** — [contentauth/example-assets Firefly_tabby_cat.json](https://github.com/contentauth/example-assets/blob/main/images/manifests/Firefly_tabby_cat.json):

```json
"claim_generator": "Adobe_Firefly",
"claim_generator_info": [{ "name": "Adobe_Firefly", "org.contentauth.c2pa_rs": "0.65.0" }],
"title": "Generated image", "format": "image/jpeg", "ingredients": [],
"assertions": [{ "label": "c2pa.actions.v2", "data": { "actions": [{
    "action": "c2pa.created", "softwareAgent": "Adobe Firefly",
    "parameters": { "com.adobe.firefly.version": "4.0.0-release-firefly_v4-main_78135.80468",
                    "com.adobe.firefly.operation": "text_to_image" },
    "digitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia" }],
  "allActionsIncluded": true } }],
"signature_info": { "alg": "Ps256", "issuer": "Adobe Inc.", "common_name": "Adobe Firefly C2PA",
                    "cert_serial_number": "4137...", "time": "2025-10-23T21:14:47+00:00" }
```
validated `Valid` with `signingCredential.ocsp.notRevoked`, `timeStamp.validated` (Adobe TSA) and informational `timeStamp.untrusted`. 2023-era Firefly wrote v1 `c2pa.actions` with `softwareAgent: "Adobe Firefly Pipeline"` and `parameters.firefly.operation/version`, `claim_generator: "Adobe_Firefly adobe_c2pa/0.5.0 c2pa-rs/0.20.0"`; Firefly-in-Express edits use `c2pa.edited` + `trainedAlgorithmicMedia` ([c2pa-org/public-testfiles](https://github.com/c2pa-org/public-testfiles/blob/main/legacy/1.4/pdf/manifests/adobe-20240110-single_manifest_store/manifest_store.json)). Firefly also applies a TrustMark-family watermark for Durable Content Credentials (Adobe's `com.adobe.trustmark.P` entry cites Adobe Content Authenticity).

**Microsoft Bing Image Creator / Designer (Feb 2024)** — raw JUMBF found in signed JPEGs on GitHub: `claim_generator: "Microsoft_Responsible_AI/1.0"`, `claim_generator_info: [{name: "Microsoft Responsible AI Image Provenance", version: "1.0"}]`, action `{ "action": "c2pa.created", "softwareAgent": "Image Creator from Designer", "when": "2024-02-05T01:48:06Z", "description": "AI Generated Image" }`, hard binding `c2pa.hash.boxes`, cert issued by "Microsoft SCD Claimants RSA CA". Microsoft also registered `com.microsoft.invismark.1` as a soft-binding watermark.

**Google (Imagen / Gemini image / Veo, 2025–26)** — signed by "Google LLC" using the "Google C2PA Core Generator Library"; `c2pa.created` with `trainedAlgorithmicMedia`, `softwareAgent` reported as "Google Generative AI" / `{"name": "Google LLC"}`, action description "Image generated with SynthID", and Google's own TSA ("Google Core Time Stamping Authority T8") (third-party fixtures/snippets: [jasonkneen/agensis ASSETS.md](https://github.com/jasonkneen/agensis/blob/main/ASSETS.md), [alfredobs97/pizzathon test](https://github.com/alfredobs97/pizzathon)). SynthID is referenced descriptively, not as a `c2pa.soft-binding` (it is not on the algorithm list). Pixel 10 signs camera captures on-device (snippet).

**Stability AI** — no first-party manifest example was found; Stability's `diffusers` integration/the neural watermarker "requires the optional c2pa Python package ... and a manifest file defining your claimant identity" (snippet) — i.e. the same `c2pa-python` + JSON manifest approach described here.

Common pattern across all vendors: `c2pa.created` + `trainedAlgorithmicMedia` + a `softwareAgent` naming the model/product + vendor-namespaced `parameters` for version/operation + a real CA-issued cert (RSA-PSS or ES256) + RFC 3161 timestamp. None of them embed prompts.

**Existing ComfyUI integrations**: [mikecaronna/comfyui_c2pa_signer](https://github.com/mikecaronna/comfyui_c2pa_signer) (c2patool subprocess, `keys/es256_private.key` + `keys/es256_certs.pem`, optional `com.comfyui.workflow` assertion, warns not to chain `SaveImage` after it); provcheck v1.4.0 ComfyUI node (Rust, TrustMark-B watermark + C2PA signature bound to an AT Protocol identity, ES256 keys in OS keychain/YubiKey); Certivu's ComfyUI node (docs unreachable).

---

## 7. Checklist for the ComfyUI node

1. `pip install c2pa-python>=0.37` (Python 3.10+, wheels for Linux x86_64/aarch64 manylinux_2_28, macOS, Windows x64). Check `c2pa.sdk_version()`.
2. Encode the image (PNG with ComfyUI `tEXt` metadata / JPEG / WebP) to bytes **first**; optionally watermark pixels (TrustMark) before encoding.
3. Build the manifest dict: `claim_generator_info`, `title`, `format`, `c2pa.actions.v2` (`c2pa.created` + `trainedAlgorithmicMedia` + `softwareAgent{name,version}` + `when`), optional `cawg.training-mining`, custom `org.comfyui.generation` (kind Json), optional `c2pa.soft-binding` + `c2pa.watermarked.bound`; for img2img add the input as `parentOf` ingredient and start with `c2pa.opened` (or use `set_intent(EDIT)`).
4. Sign with `Signer.from_info` (PEM) or `Signer.from_callback` (KMS/HSM), always with a `ta_url`; call `builder.sign(signer, mime, src, dst)`; write `dst` as the final file and, if you store manifests for soft-binding recovery, persist the returned manifest bytes.
5. Verify with `Reader` + `Settings.trust.user_anchors` in tests; expect `Valid` with test certs and `Trusted` only with a C2PA-trust-list certificate from a conforming product.

## Sources

- PyPI: https://pypi.org/project/c2pa-python/ and https://pypi.org/pypi/c2pa-python/json
- c2pa-python repo (README, `docs/usage.md`, `docs/context-settings.md`, `docs/intents.md`, `docs/release-notes.md`, `examples/sign.py`, `examples/training.py`, `examples/read.py`, `src/c2pa/c2pa.py`, `pyproject.toml`, `c2pa-native-version.txt`): https://github.com/contentauth/c2pa-python
- c2pa-python-example (KMS callback signer, CSR/openssl walkthrough): https://github.com/contentauth/c2pa-python-example
- c2pa-rs (`docs/supported-formats.md`, `docs/release-notes.md`, `sdk/src/assertions/{soft_binding,actions,labels}.rs`, `sdk/src/builder.rs`, `sdk/src/validation_results.rs`, `sdk/src/utils/ephemeral_cert.rs`, `sdk/tests/fixtures/certs/`, `sdk/tests/fixtures/schemas/crJSON-schema.json`): https://github.com/contentauth/c2pa-rs ; issue #1488: https://github.com/contentauth/c2pa-rs/issues/1488
- c2patool (`README.md`, `docs/usage.md`, `docs/manifest.md`, `docs/signing.md`): https://github.com/contentauth/c2patool
- CAI docs source (`docs/manifest/writing/assertions-actions.md`, `docs/manifest/reading/{validation,legacy}.md`, `docs/signing/{get-cert,test-certs,local-signing}.*`, `docs/conformance/trust-lists.mdx`, `static/schemas/{ManifestDefinition,Reader}.schema.json`): https://github.com/contentauth/opensource.contentauth.org (rendered at https://opensource.contentauthenticity.org/docs/)
- C2PA Soft Binding Algorithm List: https://github.com/c2pa-org/softbinding-algorithm-list ; C2PA trust lists: https://github.com/c2pa-org/conformance-public/tree/main/trust-list ; spec (blocked here): https://spec.c2pa.org/specifications/specifications/2.2/specs/C2PA_Specification.html and https://spec.c2pa.org/specifications/specifications/2.2/softbinding/Decoupled.html ; Adobe resolution API: https://developer.adobe.com/cai-soft-binding-api/
- TrustMark: https://github.com/adobe/trustmark (README, FAQ.md, c2pa/README.md, c2pa/c2pa_watermark_example.py)
- c2pa-conformance-tool EKU fixtures / openssl: https://github.com/contentauth/c2pa-conformance-tool/blob/main/wasm/tests/fixtures/eku/README.md
- CAWG Training and Data Mining Assertion v1.1: https://cawg.io/training-and-data-mining/1.1/ (source: https://github.com/decentralized-identity/cawg-training-and-data-mining-assertion)
- Third-party soft-binding write-path analysis: https://github.com/richardwooding/c2pa/blob/main/CLAUDE.md
- Real manifests: DALL·E 3 https://github.com/Tebs-Lab/lab-report-code/blob/main/2024-03-03/cape-bear-manifest.json ; Firefly https://github.com/contentauth/example-assets/blob/main/images/manifests/Firefly_tabby_cat.json and https://github.com/c2pa-org/public-testfiles ; DALL·E article (blocked): https://mikecvet.medium.com/examining-c2pa-provenance-metadata-in-dall-e-3-images-64ed51159091 ; OpenAI help (blocked): https://help.openai.com/en/articles/8912793-c2pa-in-chatgpt-images
- SB 942 text mirror: https://github.com/jbloewencolon/regs-checker/blob/main/output/law_texts/TMP-CA-AITRANSPARENCY.txt ; official: https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=202320240SB942 ; AB 853 analysis: https://hintzelaw.com/blog/2025/10/19/california-amends-artificial-intelligence-transparency-act-and-passes-ai-defenses-act
- ComfyUI nodes: https://github.com/mikecaronna/comfyui_c2pa_signer ; https://github.com/CreativeMayhemLtd/provcheck ; https://comfyui-wiki.com/en/news/2026-09-03-provcheck-c2pa-node
