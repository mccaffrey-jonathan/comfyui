# Independent review: the ComfyUI watermark + Content Credentials packs against the California AI Transparency Act

**Reviewed artefacts**

* `custom_nodes/comfyui_durable_watermark/` — `README.md`, `NOTICE`, `wm_nodes.py`, `durable_watermark/core.py`, `durable_watermark/keys.py`, `durable_watermark/cli.py`, `tests/test_core.py`
* `custom_nodes/comfyui_content_credentials/` — `README.md`, `NOTICE`, `cc_nodes.py`, `content_credentials/{manifest,signing,certs,crypto_box,verify}.py`, `tests/test_c2pa.py`
* `docs/ai-content-compliance/00-design-and-compliance-overview.md`, `01-legal-requirements-eu-california-global.md`, `03-c2pa-content-credentials-tooling.md`, `release/index.html`

**Review date:** 17 September 2026. **Reviewer posture:** gap analysis, deliberately critical. No code was modified.

> **This is not legal advice.** I am not a lawyer and this document is not a legal opinion, a compliance
> certification, or a substitute for counsel licensed in California. It is an engineering assessment of
> what two open-source node packs do and do not do, measured against my reading of a statute whose
> primary text I could not fetch directly (see *Verification status*). Nothing here is a representation
> that using these packs makes anyone compliant with anything; the packs' own `NOTICE` files disclaim
> exactly that, correctly.

---

## 0. Verification status of the legal text (read this before relying on any citation below)

The sandbox's egress proxy **blocked every primary and near-primary source** I tried:
`leginfo.legislature.ca.gov`, `law.justia.com`, `codes.findlaw.com`, `california.public.law`,
`legiscan.com`, `infobytes.orrick.com`, `calmatters.digitaldemocracy.org`, `en.wikipedia.org`, and
every law-firm domain (`troutmanprivacy.com`, `aicomplianceatlas.com`, …). `WebFetch` returned
`EGRESS_BLOCKED` for all of them.

What I *could* do is run `WebSearch`, whose result summaries quote those same pages. So:

| Claim | How verified here | Confidence |
|---|---|---|
| §22757.2 detection-tool elements (no cost; upload **and** URL; outputs system provenance data; does **not** output personal provenance data; publicly accessible with security-risk limits; **API**; collects feedback; no retention of personal information, submitted content, or personal provenance data) | Search summaries quoting Justia/`california.public.law` §22757.2 and Morgan Lewis | High — language quoted nearly verbatim in two independent searches |
| §22757.3(b) four latent fields + "to the extent technically feasible and reasonable" + "either directly or through a link to a permanent internet website" + detectable by the provider's tool + "consistent with widely accepted industry standards" + "permanent or extraordinarily difficult to remove" | Search summary quoting FindLaw/Justia §22757.3 | High |
| §22757.3(c) licensee contract + **96-hour** revocation | Same search | High |
| §22757.3 applies to content "created or altered, **except by minor modification**" | Search summary; I could **not** retrieve the §22757.1 definition of "minor modification" | Medium — *flagged as unverified* |
| §22757.1 "covered provider" = produces a GenAI system with **>1,000,000 monthly visitors or users**, publicly accessible in California | Search summary | High |
| AB 853 (Ch. 674, Stats. 2025, signed 13 Oct 2025) **amends §§22757.1, 22757.4, 22757.6 and adds §§22757.3.1, .3.2, .3.3** — it does **not** amend §22757.3 | Search summary of the chaptered LegiScan text | High — and this contradicts one of the repo's own docs, see Gap G-13 |
| AB 853 definitions of provenance data / system provenance data / personal provenance data | Search summary quoting AB 853 | High |
| §22757.4 $5,000 per violation, **each day a discrete violation**, AG / city attorney / county counsel, injunctive relief and fees | Search summaries | High |
| §22757.5 exemption for exclusively non-user-generated video game/TV/streaming/movie/interactive experiences | Search summary | High |
| Operative date **2 Aug 2026** (§22757.6, as moved by AB 853) | Search summaries + Morgan Lewis Aug-2026 alert | High |
| **SB 1000 status as of today (17 Sep 2026): passed, presented to the Governor 2 Sep 2026, NOT yet signed or vetoed, deadline 30 Sep 2026** | Two independent searches, both "still on his desk" | Medium-high — *re-check before relying; this can change any day* |
| SB 1000 contents: deletes the 1M threshold; renames "AI detection tool" → "**disclosure verification tool**"; **deletes** the manifest-disclosure option; **adds** a created-vs-altered element to the latent disclosure; **urgency clause** | Search summaries of the Legislative Counsel's digest and the Assembly Privacy Committee analysis | Medium-high |

The repository's own `01-legal-requirements-eu-california-global.md` §2.1–2.2 states the same
positions with a denser citation list, and its statement of the law matched my independent checks on
every point except one (Gap G-13). **Everything below inherits these confidence levels.** Before
acting on this review, pull the chaptered text of §§22757–22757.6 from `leginfo` on an unblocked
network and re-verify.

---

## 1. Bottom line

The two packs are a competent, honest implementation of **one half of one obligation**.

* They produce a strong **§22757.3(b) latent-disclosure candidate** for the *file as saved*: a signed
  C2PA 2.x manifest carrying all four statutory fields, plus a keyed, geometry-robust watermark that
  survives the edits that destroy the manifest.
* The four statutory fields exist **only in the C2PA manifest**. The watermark carries **32 bits by
  default (64 max) with no field structure at all** — it carries one opaque integer. Once a platform
  re-encodes the file, the only thing that survives is that integer, and the packs ship **no registry,
  no resolver, and no service** that turns it back into provider / system / version / time / id. The
  "durable content credential" story is architecturally sound and **operationally unfinished**.
* **§22757.2 is not implemented at all.** There is no public detection tool, no URL input, no API, no
  feedback channel, no retention policy — only a local CLI (`python -m durable_watermark detect`) and
  a ComfyUI node, both of which require the provider's private secret. This is the single largest gap,
  and it is not incidental: §22757.3(b) conditions the *validity of the latent disclosure* on it being
  "detectable by the covered provider's AI detection tool", so a covered provider with no tool
  arguably fails §22757.2 **and** §22757.3(b).
* **§22757.3(a) (the offered manifest / visible disclosure) is not implemented at all** — no
  burned-in-label node, no toggle. That obligation is live today and only goes away if SB 1000 is
  signed.
* **Enforcement is node-level and therefore defeatable.** `COMFYUI_WATERMARK_ENFORCE=1` pins three of
  the seven key-schedule inputs, the C2PA pack has no enforcement mode at all, and nothing prevents a
  tenant from using stock `SaveImage`. A covered provider cannot rely on workflow discipline.

For a hobbyist below any threshold, the packs are more than adequate and the honest `NOTICE` is the
right posture. For an actual covered provider, the packs are **a component, not a compliance
solution**, and roughly 60–70 % of the engineering work sits outside them.

### Who is the "covered provider" for a ComfyUI operator?

* **Today (§22757.1):** a person who "creates, codes, or otherwise produces" a GenAI system that is
  publicly accessible in California **and has >1,000,000 monthly visitors or users**. A self-hosted
  ComfyUI used privately is not publicly accessible and is out. A small public ComfyUI SaaS is under
  the threshold. Only a large public image-generation service is in. Whether an operator who *deploys*
  someone else's open weights "produces" the GenAI system is genuinely arguable and unresolved —
  the broad reading (anyone wrapping open weights into a publicly accessible product) is the prudent
  one, and it is the one the repo's docs assume.
* **If SB 1000 is signed (deadline 30 Sep 2026, urgency clause):** the threshold disappears. **Every
  publicly accessible GenAI image service in California becomes a covered provider on the day of
  signature**, including one-person ComfyUI deployments behind a public URL. The packs' target
  audience changes overnight from "large providers" to "everyone running these nodes publicly", and
  the missing §22757.2 tool becomes an obligation for people who have no ability to run a public API.
  This is the most consequential pending fact in this review.
* **§22757.3.3 (AB 853, from 1 Jan 2027):** a **GenAI hosting platform** may not knowingly make
  available a covered provider's GenAI system that does not place the required latent disclosures.
  A model host, a node registry, or a "run ComfyUI in the cloud" service should read that section
  carefully — it may be the route by which these packs' users acquire obligations.

---

## 2. Requirement-by-requirement assessment

Legend: **Meets** / **Partial** / **Does not** / **Out of scope** (a node pack cannot discharge it;
noted because a deploying provider still must).

### 2.1 §22757.2 — free AI detection tool (operative 2 Aug 2026)

| # | Requirement (citation) | What the packs do | Assessment | Evidence |
|---|---|---|---|---|
| 2.1 | Make available, **at no cost**, a tool letting a user assess whether image/video/audio was created or altered by the provider's GenAI system (§22757.2(a)) | A ComfyUI `Durable Watermark Detect` node and a CLI `detect` subcommand; a `C2PA Read / Verify Manifest` node. Both are local, operator-side, and the watermark path needs the private secret | **Does not** (as shipped) / **Out of scope** for a node pack, but the *building blocks* are there | `durable_watermark/cli.py:70-110`; `wm_nodes.py:139-212`; `content_credentials/verify.py:19-103` |
| 2.2 | Tool accepts **content upload** (§22757.2) | CLI takes a local file path; node takes an `IMAGE` tensor | **Partial** — file input exists, no user-facing upload surface | `cli.py:19-25, 76` |
| 2.3 | Tool accepts a **URL** to online content (§22757.2) | Nothing. `C2PAReadManifest` resolves names only inside ComfyUI's `input/`/`output/` dirs | **Does not** | `cc_nodes.py:301-315` |
| 2.4 | Tool **outputs any system provenance data** detected (§22757.2) | `summarize()` returns exactly the right shape: `ai_generated`, `digital_source_types`, `software_agents`, `claim_generator`, `signer`, `generation`, `soft_bindings`, `validation_state`. The watermark detector returns `z_score`, `payload_hex`, `scale/rotation/flip` | **Partial → good basis** — the data model is right; nothing publishes it | `verify.py:62-103`; `core.py:502-532` |
| 2.5 | Tool must **not output personal provenance data** (§22757.2) | No filter exists. `summarize()` returns the whole `org.comfyui.generation` assertion verbatim, which (with `workflow_in_manifest=True`) can include a redacted-but-complete ComfyUI graph with local paths, and always includes `prompt_sha256`/`workflow_sha256`. `org.comfyui.private` is AES-GCM encrypted (good) but `has_private_assertion: true` is disclosed | **Does not** — no allowlist, no classification of fields as system vs personal | `verify.py:96-102`; `manifest.py:110-124`; `cc_nodes.py:166-170` |
| 2.6 | Tool **publicly accessible** (with permitted limits for demonstrable security/integrity risks) (§22757.2) | Nothing is served | **Does not** | — |
| 2.7 | Tool supports an **API** invocable without visiting the provider's website (§22757.2) | Nothing. The CLI is a local process, not an API | **Does not** | `cli.py` |
| 2.8 | **Collect user feedback** on efficacy and incorporate it (§22757.2) | Nothing | **Does not** | — |
| 2.9 | **No retention** of personal information from tool users (beyond limited contact info), no retention of submitted content beyond necessity, no retention of personal provenance data (§22757.2) | Nothing retains anything because nothing is served; but also no documented policy or reference implementation for a provider to inherit | **Out of scope, unaddressed** — a provider wrapping the CLI in a web service will get this wrong by default (temp files, request logs, URL-fetch caches) | — |

### 2.2 §22757.3(a) — optional manifest (visible) disclosure

| # | Requirement | What the packs do | Assessment | Evidence |
|---|---|---|---|---|
| 2.10 | Offer users the **option** to include a manifest disclosure identifying content as AI-generated, clear, conspicuous, appropriate to the medium, understandable to a reasonable person, permanent or extraordinarily difficult to remove (§22757.3(a)) | Nothing. No overlay/burn-in node, no toggle. `README.md` of the C2PA pack explicitly puts it "out of scope; burn a label in with an image node when required" | **Does not** — and this obligation is **live today** | `comfyui_content_credentials/README.md`, "Regulatory mapping" table, last row |
| 2.11 | (If SB 1000 is signed, this obligation is deleted) | The docs anticipate this correctly | n/a | `01-legal-requirements…md:123-124` |

### 2.3 §22757.3(b) — mandatory latent disclosure

| # | Requirement | What the packs do | Assessment | Evidence |
|---|---|---|---|---|
| 2.12 | Include a latent disclosure in **all** image/video/audio content the system creates or alters (except by minor modification) | The C2PA save node writes a manifest and the embed node writes a watermark — **only when a workflow wires them in**. Nothing is automatic; no server-side enforcement for the C2PA node at all | **Partial** — capability yes, guarantee no | `cc_nodes.py:126-286`; `wm_nodes.py:99-137` |
| 2.13 | (A) **Name of the covered provider** | `provider_name` widget → `org.comfyui.generation.provider` and `claim_generator_info[0]["org.comfyui.provider"]`. **Free text, no validation; if left empty the field is silently dropped** (`{k: v for k, v in … if v is not None}`) | **Partial** — present in metadata; silently omissible; absent from the watermark | `manifest.py:99, 108, 162`; `cc_nodes.py:150` |
| 2.14 | (B) **Name and version number of the GenAI system** | `softwareAgent {name, version}`, `claim_generator_info`, and `org.comfyui.generation.system`. `system_version` defaults to the **ComfyUI** version; the checkpoint goes to `parameters["org.comfyui.model"]`, not to the version | **Partial** — defensible but ambiguous: is the "GenAI system" ComfyUI, or ComfyUI + Flux 1.dev? The packs let you say either and default to the former | `manifest.py:77-88, 100`; `cc_nodes.py:151-154, 253` |
| 2.15 | (C) **Time and date of creation or alteration** | `action.when` (RFC 3339 UTC, second precision) + `org.comfyui.generation.created`; RFC 3161 TSA timestamp on the signature (DigiCert by default) | **Meets** in metadata. Caveat: the release page's own demo shows `"signer": {"time": null}` — the trusted timestamp did not land in that artefact | `manifest.py:70-76, 81-84`; `signing.py:24`; `release/index.html` verification summary |
| 2.16 | (D) **Unique identifier** | Per-image `uuid4` as `generation_id` (in the action parameters and the generation assertion) plus the C2PA manifest label `urn:c2pa:<uuid>` | **Meets** in metadata | `cc_nodes.py:247`; `manifest.py:49, 85, 104` |
| 2.17 | Conveyed "**directly or through a link to a permanent internet website**" | The manifest conveys all four **directly** — good. The watermark conveys **neither**: 32 opaque bits, no URL, no scheme-registered resolver. There is no registry code, no remote-manifest URL, no `dcterms:provenance` pointer | **Partial → the durable layer fails this** | `wm_nodes.py:133-137`; `manifest.py:139-151`; see Gap G-1 |
| 2.18 | "**Detectable by the covered provider's AI detection tool**" | The C2PA layer is detectable by any C2PA reader (`verify.py`). The watermark is detectable **only with the private secret and the exact key-schedule parameters** — the provider can, the public cannot | **Partial** — the statutory test is the *provider's* tool, so a keyed mark is compatible in principle, but there is no tool, and see Gaps G-4/G-5 for cases where even the provider's tool fails | `core.py:134-152, 664-762` |
| 2.19 | "**Consistent with widely accepted industry standards**" | C2PA 2.x via official `c2pa-python` / c2pa-rs, IPTC `digitalSourceType` — squarely the industry standard. The watermark is a **bespoke scheme** (`org.comfyui.ringmark.v1`) that is **not on the C2PA Soft Binding Algorithm List** (53 entries as of Sept 2026), so no third party can resolve it | **Partial** — strong for the metadata layer, weak for the watermark layer | `manifest.py:26-38, 141-151`; `03-c2pa-…md:410-423` |
| 2.20 | "**Permanent or extraordinarily difficult to remove**" (to the extent technically feasible) | Metadata: **not** permanent — any re-encode strips it, and the README says so. Watermark: survives rotation/flip/crop/rescale/colour/gamma/blur/noise and JPEG ≈ q75 on photos; fails on flat graphics at q75, fails rot15 + 0.61× + q75, and (like every post-hoc mark) fails regeneration and adversarial attacks | **Partial, and the packs say so honestly** — this is the best-faith reading available for a post-hoc watermark; whether it satisfies "extraordinarily difficult" is a question for counsel, not for me | `comfyui_durable_watermark/README.md` robustness table + "Limitations"; `00-design-…md` "Known limitations" |
| 2.21 | Created-vs-altered element (**SB 1000 only**, not yet law) | `c2pa.created` vs `c2pa.edited`, chosen by whether `parent_image` is connected; plus `digital_source_type`. **Nothing in the watermark** | **Partial / premature** — see Gaps G-6 and G-13 | `manifest.py:81`; `cc_nodes.py:260` |

### 2.4 §22757.3(c) — licensee flow-down

| # | Requirement | What the packs do | Assessment | Evidence |
|---|---|---|---|---|
| 2.22 | Contractually require licensees to **maintain** the latent-disclosure capability (§22757.3(c)) | Nothing contractual (correctly — it is a legal artefact). Technically: `COMFYUI_WATERMARK_ENFORCE=1` pins the server-side secret, payload and strength so a tenant workflow cannot re-key or disable the mark | **Partial**, technical half only, and **incomplete** — see Gap G-4 | `keys.py:66-160`; `wm_nodes.py:76-97, 131` |
| 2.23 | **Revoke the licence within 96 hours** of discovering a licensee disabled it | Nothing: no telemetry, no per-licensee key, no audit/verification hook, no revocation mechanism. There is a `key_fingerprint` that could anchor per-licensee keys, but nothing uses it that way | **Does not** / **Out of scope** for the packs, but the packs give a provider no head start either | `core.py:129-132` |
| 2.24 | The C2PA half of the disclosure has **no enforcement mode at all** | `C2PASaveImage` has no `C2PA_ENFORCE` equivalent; `provider_name`, `system_name`, `digital_source_type` and `do_not_train` are tenant-editable widgets with no server override, and any workflow can simply use stock `SaveImage` | **Does not** — asymmetric with the watermark pack | `cc_nodes.py:139-177` (no config/env override path); `signing.py:17-24` (env vars cover credentials only) |

### 2.5 Penalties, exemptions, AB 853 additions, SB 1000, AB 2013

| # | Requirement | Relevance to the packs | Assessment | Evidence |
|---|---|---|---|---|
| 2.25 | §22757.4 — $5,000 per violation, **each day a discrete violation**, AG / city attorney / county counsel, injunctive relief + fees | Sets the cost of the gaps above. Note the packs' `NOTICE` disclaims liability; a provider cannot transfer this risk to an Apache-2.0 dependency | **Out of scope** (provider risk) | `NOTICE` (both packs) |
| 2.26 | §22757.5 — exemption for exclusively non-user-generated video game / TV / streaming / movie / interactive experiences | A ComfyUI pipeline producing game assets **non-user-generated** may be exempt; the docs mention the exemption in `01-legal-…md:109` but neither pack's README surfaces it | **Out of scope**, under-documented | `01-legal-…md:109` |
| 2.27 | §22757.3.1 / .3.3 (AB 853, **1 Jan 2027**) — large online platforms must detect, surface and let users inspect system provenance data, and must **not knowingly strip** provenance data; GenAI hosting platforms must not knowingly host non-compliant systems | Explains why the C2PA layer matters even though platforms strip it today, and why the soft binding is the right architecture. Nothing in the packs helps a platform | **Out of scope** | `01-legal-…md:113-117` |
| 2.28 | §22757.3.2 (AB 853, **1 Jan 2028**) — capture-device manufacturers embed manufacturer/device/time latent disclosures | Not applicable to a generation pipeline | **Out of scope** | `01-legal-…md:117` |
| 2.29 | **SB 1000** — threshold removal; "disclosure verification tool"; manifest option deleted; created-vs-altered added; urgency clause | Would make the missing §22757.2 tool and the missing created/altered bit urgent for every public deployment, and would retire the one obligation (2.10) the packs currently fail outright | **Watch item** — status as of 17 Sep 2026: **on the Governor's desk, unsigned, deadline 30 Sep 2026** | Searches above; `01-legal-…md:119-125` |
| 2.30 | **AB 2013** (training-data transparency, in force 1 Jan 2026) | Frequently confused with CAITA but is a **different obligation**: publish documentation of training datasets for GenAI systems made publicly available to Californians and released on/after 1 Jan 2022. It is a **website-publication duty about the model**, not a content label; nothing in these packs addresses it and nothing in these packs is required by it. (A ComfyUI operator distributing others' checkpoints is generally a deployer, not the "developer" who trained them — but fine-tuning or merging may make you one.) A federal constitutional challenge was filed by xAI in Dec 2025 and AB 2013 was reported as in effect and enforced as of 2026 | **Out of scope, correctly** — the repo's docs classify it correctly at `01-legal-…md` table row "AB 2013" | `01-legal-…md` §2.4 table |
| 2.31 | **AG guidance** | The California AG issued general AI legal advisories in **January 2025** (not CAITA-specific) and has been reported to be hiring AI technologists for enforcement. I found **no CAITA-specific AG regulation, advisory, or FAQ** — and the Act grants no rulemaking authority I could verify. Do not expect a safe harbour | **Out of scope** — but note the packs' docs also do not claim one | Search results (WilmerHale, Jan 2025) |

---

## 3. Specific technical gaps

### G-1 — The four latent-disclosure fields live in the layer that does not survive; the layer that survives carries 32 opaque bits

The architecture is explicitly "metadata for the fields, watermark for durability, soft binding to
join them" (`00-design-…md`, "Why two layers"). That is the right architecture. **The join is not
implemented.**

What actually survives a re-encode:

| §22757.3(b) field | In C2PA manifest | In watermark pixels |
|---|---|---|
| (A) provider name | yes (`org.comfyui.generation.provider`, `claim_generator_info`) | **no** — inferable only from *which private key detects*, which requires the provider's service |
| (B) system name + version | yes (`softwareAgent{name,version}`) | **no** |
| (C) time and date | yes (`action.when` + TSA) | **no** |
| (D) unique identifier | yes (`generation_id`, `urn:c2pa:<uuid>`) | **partially** — 32 bits, *if* the payload is set per-image, which enforce mode prevents (G-3) |
| created vs altered (SB 1000) | yes (`c2pa.created`/`c2pa.edited`) | **no** — not one bit of the payload is reserved for it |

So after any social-platform re-encode, the surviving disclosure is one 32-bit integer plus the fact
that a key matched. The statute permits conveying fields "through a link to a permanent internet
website" — **but the packs ship no such link and no such website**. There is:

* no registry schema, table, or persistence code anywhere in either pack (the C2PA README merely
  advises "store the `manifest_json` output keyed by `generation_id` / watermark payload");
* no C2PA **remote manifest URL** (c2pa-rs supports remote/no-embed manifests; `sign_image_bytes` at
  `manifest.py:167-190` always embeds);
* no **Soft Binding Resolution API** endpoint or client, although the repo's own research documents
  the spec and Adobe's implementation (`03-c2pa-…md:404`).

**Assessment:** the 32-bit payload does **not** on its own "convey, directly or through a link", any
of the four fields. It is a *lookup key for a registry that does not exist*. Building that registry
and resolver is the single highest-value missing piece.

### G-2 — 32 bits is too small to be a "unique identifier" at any real volume

`payload_bits` defaults to 32 (`core.py:88`, `wm_nodes.py:47`). With random per-image payloads, the
birthday bound gives a ~50 % chance of a collision after ≈ 77,000 images, and ~1 % after ≈ 9,300. A
covered provider — by definition >1M monthly users today — will collide within hours. At 64 bits
(the maximum) the 50 % point moves to ≈ 5×10⁹ images, which is workable, but the README states 64
bits "halves the per-bit margin", i.e. costs robustness precisely where it matters.

Worse, `payload_from_string` (`core.py:304-328`) **hashes** any non-numeric string (e.g. a UUID
fragment) to `payload_bits` bits. There is no structured payload — no provider-prefix/serial split,
no epoch field, no reserved bits. A provider who wants both "which provider" and "which image" in 32
bits must design that layout themselves, outside the pack.

The 8-bit CRC (`core.py:295-301, 342-370`) gives a ~1/256 chance that a random decode passes CRC;
combined with the z ≥ 5 presence gate that is acceptable, but a registry doing lookups on decoded
payloads must treat a CRC-passing decode as *probable*, not *certain*, and cross-check.

### G-3 — Enforce mode and per-image unique IDs are mutually exclusive

`DurableWatermarkEmbed.execute` ignores `payload_override` when the key is enforced:

```python
if payload_override and not key.get("enforced"):
    payload = payload_from_string(payload_override, cfg.payload_bits)
```
(`wm_nodes.py:131-132`)

And in enforce mode `resolve_payload` returns the single server-side `COMFYUI_WATERMARK_PAYLOAD` /
config value (`keys.py:131-143`). So the provider must choose:

* **enforce on** → tenants cannot disable or re-key the mark (good for §22757.3(c)) **but every image
  carries the identical payload**, so the watermark conveys no unique identifier (field D) and no
  route to time/date (field C) after stripping; or
* **enforce off** → per-image IDs are possible, but a tenant workflow can change the payload, the
  band parameters, or simply not wire the node at all.

This is a design conflict, not a bug, and it is not acknowledged anywhere in the docs. The fix is a
server-side payload *template* (fixed high bits pinned by the server, low bits per-image from the
generation UUID) rather than a fixed integer.

### G-4 — Enforce mode does not pin the parameters that the key schedule depends on

`_kdf` binds the key material to `secret`, `payload_bits`, `r_min`, `r_max`, `ring_width`
(`core.py:134-152`). `resolve()` pins only `secret`, `payload_text`, `strength`
(`keys.py:146-165`), and `DurableWatermarkKey.execute` then builds the config from the **widget**
values for `payload_bits`, `r_min`, `r_max`, `ring_width`, `perceptual_mask`, `noise_floor`
(`wm_nodes.py:74-86`).

Consequence: with `COMFYUI_WATERMARK_ENFORCE=1`, a tenant who sets `r_max = 0.20` or
`payload_bits = 16` produces images whose mark the provider's own detector — configured with the
server defaults — **cannot find at all** (wrong key schedule ⇒ pure noise, z < 3 by construction).
The provider believes the mark is enforced; §22757.3(b)'s "detectable by the covered provider's AI
detection tool" silently fails. This is the most concrete defect I found in the review, and it is a
few lines to fix.

(`strength` and the two booleans are not in the KDF, so varying those only degrades, rather than
destroys, detection. `perceptual_mask`/`noise_floor` mismatches are recoverable; band mismatches are
not.)

### G-5 — A public detection tool keyed to private secrets does not scale, and the statistics need a multiple-comparisons correction

Detection costs ≈ 1.5–2.5 s per 768 px image **per key** on one core (`00-design-…md`). A provider
who rotates keys (which the packs correctly recommend, because averaging attacks exist) must try
every historical key on every submission. 365 daily keys × 2 s ≈ 12 minutes of CPU **per public API
request** — trivially DoS-able, and §22757.2 requires the tool to be publicly accessible with only
security-risk-based limits.

Second, the z-threshold. `detect()` builds an empirical null from 96 wrong keys and the default
threshold is z ≥ 5 (`core.py:664-762`, `wm_nodes.py:170-171`) — honest and well-designed for a single
key. But a public tool trying K keys makes K tests; the per-image false-positive rate scales with K.
At K = 365 and p ≈ 3×10⁻⁷ per test, expect a false "yes, we made this" roughly once per 9,000
queries. For a tool whose output will be used to accuse or exonerate, that needs an explicit
Bonferroni/Šidák correction and a documented operating point. Nothing in the packs mentions it.

Third, input size: `detect()` returns "image too small" below 48 px and the docs note the payload
needs ≳ 300 px (`core.py:676-682`; `00-design-…md`). A public tool will be fed thumbnails and
screenshots constantly and must degrade gracefully and say so.

### G-6 — No created-vs-altered signal in the durable layer, and the metadata signal is inferred, not declared

`is_edit_of_input = parent_bytes is not None` (`cc_nodes.py:260`), i.e. `c2pa.created` vs
`c2pa.edited` is decided **solely by whether the optional `parent_image` input happens to be wired**.
An img2img or inpainting workflow that does not connect `parent_image` produces a manifest asserting
`c2pa.created` — and `digital_source_type` is an independent widget that defaults to
`trainedAlgorithmicMedia`, so the same workflow will also assert "fully AI-generated" for an edit of
a user photograph. Two independent, silently-defaultable controls govern a statement about
provenance that SB 1000 would make a mandatory statutory element.

And under SB 1000 the created/altered flag belongs to the **latent disclosure** — which, post-strip,
is the watermark. The watermark has no such bit. The release page's regulatory table implies the
requirement is met ("SB 1000 … adds a created-vs-altered flag — `c2pa.created` vs `c2pa.edited` plus
`digitalSourceType`"); after a re-encode it is not.

### G-7 — Soft-binding interoperability: unregistered algorithm, deprecated action, wrong CBOR type

Three separate issues, all documented in the repo's own research and none fixed in the code:

1. **`alg: "org.comfyui.ringmark.v1"` is not on the C2PA Soft Binding Algorithm List** (53 entries,
   Sept 2026 — `03-c2pa-…md:412`). No third-party validator, and no C2PA Soft Binding Resolution API
   client, can act on it. For the "widely accepted industry standards" test this is the weakest point
   of an otherwise standards-clean manifest.
2. **`c2pa.watermarked` is deprecated** for new content in favour of `c2pa.watermarked.bound` /
   `.unbound` (spec 2.2+; `03-c2pa-…md:406`). `manifest.py:90-97` writes the deprecated action. Since
   the pack *does* write an accompanying `c2pa.soft-binding`, `c2pa.watermarked.bound` is the correct
   label, and using it would also avoid the `assertion.action.softBindingMissing` family of codes.
3. **`blocks[].value` is a CBOR text string where the CDDL says `bstr`** — acknowledged in the C2PA
   pack README ("current validators accept the text form") and analysed at `03-c2pa-…md:408`. Also
   `"scope": {}` is written empty. Tolerated today; a strict validator may reject it tomorrow.

### G-8 — §22757.2's "no personal provenance data" has no implementation anywhere

AB 853 defines *personal provenance data* as provenance data containing unique device/system/service
information reasonably capable of being associated with a particular user. The packs write, into the
**public, signed** manifest:

* `prompt_sha256` / `workflow_sha256` always (`manifest.py:110-113`);
* the full redacted prompt **and** workflow when `workflow_in_manifest=True` (`manifest.py:115-117`,
  `cc_nodes.py:167-169`) — which can include local filesystem paths, LoRA names, user-chosen
  filenames;
* ComfyUI `prompt`/`workflow` PNG text chunks by default (`embed_workflow_metadata=True`,
  `cc_nodes.py:165-166`, written at `cc_nodes.py:231-240`).

The redaction that does exist (`keys.redact_prompt`, `keys.py:168-193`) blanks **only**
`DurableWatermarkKey.secret` — it is a secret-leak guard, not a personal-data guard, and the tooltip
at `cc_nodes.py:168` correctly shouts "(public!)". Meanwhile `summarize()` (`verify.py:62-103`)
returns everything it finds. A provider who wraps `verify.summarize()` in the §22757.2 tool will
publish whatever the workflow put in the manifest. There is no `system_provenance_only=True` mode.

(The `org.comfyui.private` AES-256-GCM assertion is the right place for tenant/job identifiers and is
well built — HKDF-SHA256, AEAD with the generation id as AAD, tamper test at `tests/test_c2pa.py:88`.
It is simply not wired to any policy about what *must* go there.)

### G-9 — Node-level enforcement cannot bind a tenant; the C2PA pack has no enforcement at all

`COMFYUI_WATERMARK_ENFORCE` is a genuine and thoughtful feature, but it only affects the
`DurableWatermarkKey` node's output. A tenant workflow that omits both packs and uses stock
`SaveImage` produces an entirely unmarked, unsigned image. There is no ComfyUI-level hook here that
forces marking of every output. For a covered provider the implication is blunt: **the marking must
happen in the serving layer (a post-execution hook or an egress proxy over the output directory),
not in the graph.** Neither pack says this, and the release page's "Providers set
`COMFYUI_WATERMARK_ENFORCE=1` so workflows cannot re-key or disable the mark" overstates what that
flag achieves.

`C2PASaveImage` has no equivalent at all: `provider_name`, `system_name`, `system_version`,
`model_name`, `digital_source_type` and `do_not_train` are free widgets with no server override, and
an empty `provider_name` silently drops statutory field (A) (`manifest.py:108, 162`).

### G-10 — No manifest-disclosure (visible label) capability

§22757.3(a) is in force today. Neither pack can burn in a label, and the C2PA README declares it out
of scope. For a covered provider this is a straightforward "does not meet" that no amount of C2PA
correctness fixes. It is also the requirement most likely to disappear (SB 1000) — which is an
argument for a thin implementation, not for none.

### G-11 — Robustness envelope vs. "extraordinarily difficult to remove"

Credit where due: the measurements are unusually honest (calibrated nulls from wrong keys, published
failure rows, explicit "does not survive regeneration/UnMarker/MarkNull/averaging"). But note what
the numbers mean for the statute:

* **Flat/vector graphics lose the 32-bit payload at JPEG ≤ q75** at default strength (README table:
  `flat s=1.0`, JPEG q75 → ❌ z=2). Product screenshots, logos and UI mockups are exactly this class,
  and they are common generative outputs.
* **WebP is harsher than JPEG** — the release page reports payload survival only at q100 and presence
  at q90 on the photo at strength 1.0. Most social platforms serve WebP/AVIF.
* **Combined rescale+JPEG** (net 0.65× + q75/q85) loses everything on photo and flat images.
* The default is strength 1.0; the configuration that survives real platform pipelines is 1.5, at a
  3–4 dB PSNR cost. The default therefore optimises quality over durability — a reasonable
  open-source default and arguably the wrong one for a covered provider. Nothing warns about this in
  the node tooltips.

None of this makes the claim unsupportable — "to the extent it is technically feasible" is doing a
lot of work in the statute, and no post-hoc watermark does better — but a provider should document
the envelope, choose strength 1.5, and not assume durability through a WebP-serving CDN.

### G-12 — Detection needs the private secret: correct for the statute, wrong for everyone else

§22757.2 asks for detection by *the covered provider's* tool, so a keyed scheme is admissible and the
keying is a genuine security benefit (an attacker cannot locate or forge the mark). But the practical
consequences deserve stating plainly:

* Only the provider can ever answer "did you make this?" — journalists, platforms and the public
  cannot verify independently once the C2PA manifest is gone. This is the opposite of the C2PA/AB 853
  direction of travel (platforms surfacing provenance from 1 Jan 2027).
* The provider's secret becomes a compliance-critical asset: lose it and every previously marked
  image becomes undetectable, which is a §22757.3(b) failure with a per-day penalty. `keys.py` gets
  key *sourcing* right (env/file precedence, literal-secret warning, PNG-metadata redaction) but
  there is no key escrow, versioning, or rotation record anywhere — no `key_id` in the payload, no
  key registry file, only an unstored 8-byte `key_fingerprint` echoed into the manifest.

### G-13 — Internal inconsistency about what AB 853 actually did (and a resulting mislabel in shipped code)

`03-c2pa-content-credentials-tooling.md:361` states that AB 853 "rewrites (b) as new subdivision (a)
with item **(E) 'Whether the content is generated or modified by artificial intelligence'**",
"altered, except by minor modification", and "permanent or extraordinarily difficult to remove **or
tamper with**".

That does not match the chaptered bill. The enacted AB 853 (Ch. 674, Stats. 2025) is "an act to amend
Sections 22757.1, 22757.4, and 22757.6 of, and to add Sections 22757.3.1, 22757.3.2, and 22757.3.3
to, the Business and Professions Code" — **§22757.3 is untouched**. The "(E)" language appears to
come from an earlier (introduced/amended) version of AB 853, which was narrowed before passage.
`01-legal-…md` §2.1–2.2 gets this right and attributes the created/altered element to **SB 1000**.

This has leaked into shipped documentation: `comfyui_content_credentials/README.md` labels the
manifest fields "(AB 853/SB 1000: created vs altered)" and `manifest.py:11` comments
`digitalSourceType … (… SB 942 (E) "created vs altered")`. **There is no subdivision (E) and no
created/altered element in current law.** It is a pending SB 1000 change. Presenting it as enacted is
the kind of error that erodes trust in the rest of an otherwise careful mapping.

### G-14 — Marketing language slightly outruns the implementation

The `NOTICE` files are exemplary and the READMEs are largely careful. The release page is looser:

* "Together they meet … the latent-disclosure fields in California's AI Transparency Act" — they
  *populate* those fields in strippable metadata; they do not meet §22757.3(b) as a whole, because
  §22757.3(b) requires detectability by a tool that the packs do not provide.
* The regulatory table's California row ends "…; provider must offer a detection tool" with the
  watermark/credentials columns describing what the packs do — **but no cell says "not provided by
  these packs"**. A reader skims that row as a checklist that is ticked.
* "Providers set `COMFYUI_WATERMARK_ENFORCE=1` so workflows cannot re-key or disable the mark" — see
  G-4 and G-9.

---

## 4. Prioritised recommendations

### MUST (a covered provider cannot ship these packs without this work)

**M1. Build and operate the §22757.2 tool (provider, not pack).** A minimal design that wraps the
existing CLI/library honestly:

```
POST /v1/detect        multipart file  |  {"url": "..."}        → 200 JSON
GET  /v1/detect?url=…                                            → 200 JSON
POST /v1/feedback      {"query_id","verdict","comment"}          → 202
GET  /v1/openapi.json                                            (the §22757.2 "API")
GET  /                  browser page: drag-drop + URL box + feedback form
```
Implementation notes that map to the statute:
* **Both inputs, per §22757.2**: upload *and* URL. The URL fetcher must be SSRF-hardened (deny
  RFC1918/link-local/metadata IPs, cap size ~32 MB, cap redirects, enforce a timeout, allow only
  image/* content types).
* **Pipeline:** (1) `content_credentials.verify.read_manifest` + a **new** `summarize_system_only()`
  that emits an explicit allowlist of fields — `ai_generated`, `digital_source_types`,
  `software_agents`, `claim_generator`, `signer{issuer,common_name,time,alg}`, `validation_state`,
  provider/system/version/created/generation_id from `org.comfyui.generation`, `soft_bindings` —
  and **never** `prompt_sha256`, `workflow_sha256`, `org.comfyui.workflow`, ingredient titles, or
  file paths. (2) `durable_watermark.detect` against the provider's key set. (3) If a payload
  decodes, resolve it against the manifest registry (M2) and return the four fields from there.
* **Output**: `{"assessment": "created_by_us" | "altered_by_us" | "not_detected" | "inconclusive",
  "system_provenance": {...}, "evidence": {"c2pa": {...}, "watermark": {"z": ..., "p": ...,
  "payload": "0x...", "threshold": ..., "keys_tried": N}}, "query_id": "..."}`. State the
  multiple-comparison-corrected threshold you used (G-5).
* **Retention**: process in memory or in a `tempfile` unlinked in a `finally:`; no request body
  logging; log only `{query_id, timestamp, verdict, latency, key_epoch}`; strip URL query strings
  from logs; drop any decoded personal provenance data immediately (§22757.2). Publish the retention
  policy on the tool's page.
* **Feedback**: persist `{query_id, verdict, free text}` only, and record in your compliance file how
  feedback was reviewed and what changed — the statute requires *incorporating* it.
* **Availability limits**: rate-limit and CAPTCHA are defensible as "reasonable limitations … to
  prevent or respond to demonstrable risks to security or integrity"; a login wall or a paywall is
  not (the tool must be free and publicly accessible).
* **Cost control** for G-5: put a **key epoch index in the payload's high bits** so the service tries
  one key, not 365 (see M3).

**M2. Ship a manifest registry + resolver (pack or provider).** The soft binding is worthless without
it. Minimum viable: on save, persist `(payload_hex, key_fingerprint, scheme) → manifest_json,
generation_id, created_at, provider, system, version, created_or_altered`. Expose
`GET /v1/provenance/{scheme}/{key_fingerprint}/{payload_hex}` returning the four §22757.3(b) fields
from a **permanent** URL, and have the detection tool call it. This is what turns the watermark's 32
bits into a statutory "link to a permanent internet website". The C2PA node already returns
`manifest_json` (`cc_nodes.py:285`) — a tiny SQLite/S3 writer node or a post-save hook closes the
loop. Consider also implementing the **C2PA Soft Binding Resolution API** shape so third parties can
use it (`03-c2pa-…md:404`).

**M3. Fix enforce mode (pack, small change).** Pin **all** KDF inputs server-side —
`payload_bits`, `r_min`, `r_max`, `ring_width` (and ideally `perceptual_mask`/`noise_floor`) — when
`COMFYUI_WATERMARK_ENFORCE=1`, by having `resolve()` return them and `DurableWatermarkKey.execute`
prefer them over the widgets, with a log line when a widget value is overridden. Without this,
enforce mode can produce marks the provider's own detector cannot find (G-4). At the same time,
replace the fixed enforced payload with a **payload template**: e.g. server pins bits 63..40 (provider
+ key epoch), the node fills bits 39..0 from the generation UUID, resolving the enforce-vs-unique-id
conflict (G-3) and giving the detection service a cheap key-epoch hint (G-5).

**M4. Default to the durable configuration for providers.** Document (and, in an enforced deployment,
pin) `payload_bits = 64` and `strength = 1.5`, and say plainly in the README that strength 1.0 /
32 bits is the *hobbyist* default. Note explicitly that flat graphics and WebP delivery are the weak
cases (G-11).

**M5. Implement §22757.3(a) or state its absence at the top of the README (pack).** A
`ManifestDisclosureOverlay` node — configurable corner, contrast-aware plate, "AI-generated" or
provider-supplied text, plus writing IPTC `digitalSourceType` into XMP — is a day of work and closes
an obligation that is live *today*. If it stays out of scope, both READMEs and the release page
should say "these packs do **not** implement §22757.3(a)" rather than burying it in a table row.

**M6. Correct the AB 853 / SB 1000 attribution (docs, pack).** Fix `03-c2pa-…md:361`, the
`comfyui_content_credentials/README.md` regulatory table, and the `manifest.py:11` docstring: there
is no §22757.3(b)(E); the created/altered element is a **pending SB 1000** change (G-13). Add a dated
"status as of" line, because SB 1000 resolves by 30 Sep 2026.

### SHOULD

**S1. Reserve a created/altered bit in the watermark payload** and set it from the same source of
truth as `c2pa.created`/`c2pa.edited`, so the flag survives stripping if SB 1000 becomes law (G-6).

**S2. Make created-vs-altered explicit, not inferred.** Add a `content_relationship`
(`created` / `altered`) widget to `C2PASaveImage` that drives both the action label and a validated
`digital_source_type` (reject `trainedAlgorithmicMedia` when `altered` is selected, and vice versa),
instead of keying off whether `parent_image` happens to be connected (`cc_nodes.py:260`).

**S3. Add a `C2PA_ENFORCE` server mode** mirroring the watermark pack: pin `provider_name`,
`system_name`, `system_version` and `do_not_train` from env/config, and **fail the node** (rather than
silently dropping the field) when `provider_name` is empty in enforced mode (`manifest.py:108, 162`).

**S4. Add `summarize_system_only()` to `verify.py`** (the allowlist described in M1) so the
§22757.2 "no personal provenance data" rule has a code-level home rather than being a deployment
convention (G-8). Default `embed_workflow_metadata` to **False** when `C2PA_ENFORCE` is set.

**S5. Modernise the soft binding** (G-7): emit `c2pa.watermarked.bound` instead of the deprecated
`c2pa.watermarked`; keep a `TODO`/issue link about the `bstr` vs `tstr` CDDL mismatch; and either
register `org.comfyui.ringmark.v1` on the C2PA Soft Binding Algorithm List or ship an optional
**TrustMark** (`com.adobe.trustmark.Q`, MIT) second mark so the manifest also carries a *registered*
algorithm that third-party resolvers understand. The repo's own research already recommends this
layering (`00-design-…md`, final paragraph).

**S6. Document the multiple-comparisons correction** in `detect()`'s docstring and in the Detect
node's tooltip, and add a `keys_tried`/`family_wise_threshold` field to `DetectionResult` so a
detection service reports an honest number (G-5).

**S7. Write the operator's guide the packs currently lack**: mark in the serving layer, not the graph
(G-9); key rotation and escrow procedure; what to log; and a one-page statement of the robustness
envelope for the compliance file.

**S8. Soften the release page** (G-14): change "Together they meet …" to "Together they produce …",
and add an explicit "not provided by these packs" column or footnote covering §22757.2's public tool,
§22757.3(a)'s visible label, the registry, and licensee revocation.

### COULD

**C1. Emit a C2PA remote-manifest URL** (`no_embed` + `set_remote_url` in c2pa-rs) as an option, so
the asset carries a permanent link even when the embedded manifest is stripped by tools that preserve
XMP.

**C2. Write IPTC `digitalSourceType` into XMP** alongside the C2PA manifest (some pipelines keep XMP
while dropping JUMBF), and a TC260 `AIGC` XMP block for China — both already scoped in the docs.

**C3. Per-licensee keys and a revocation ledger**: derive licensee keys from a master secret plus a
licensee id, record `key_fingerprint → licensee, issued_at, revoked_at`, and give the provider a CLI
to mark a key revoked — the technical substrate for the §22757.3(c) 96-hour duty (G-12, 2.23).

**C4. A conformance self-test node/CLI** (`durable_watermark selftest` / `c2pa selftest`) that takes
a saved output and asserts: manifest present and valid; all four fields non-empty; watermark detected
with the server key at server parameters; payload resolvable in the registry. Run it in CI and as a
production canary — this is how a provider *discovers* a G-4-class failure within 96 hours.

**C5. Structured-payload helpers** in `core.py` (`pack_payload(provider_id, epoch, serial)` /
`unpack_payload`) so providers stop hashing strings into 32 bits (G-2).

---

## 5. What a covered provider still has to do, outside these nodes

- [ ] **Determine whether you are a covered provider** — today: >1M monthly visitors/users and
      publicly accessible in California; **after 30 Sep 2026, possibly any public GenAI service** if
      SB 1000 is signed. Re-check on 1 Oct 2026 and document the analysis.
- [ ] **Check the §22757.5 exemption** (exclusively non-user-generated game/TV/streaming/movie/
      interactive experiences) before building anything.
- [ ] **Build, host and operate the §22757.2 free public detection tool** — upload **and** URL input,
      public API, feedback collection, no retention of personal information / submitted content /
      personal provenance data, system provenance data only in the output. Keep it up: every day of
      non-compliance is a discrete $5,000 violation.
- [ ] **Run the manifest registry** behind it, with a permanence commitment (the statute contemplates
      "a permanent internet website"), backups, and a data-retention policy that survives the
      products that created the images.
- [ ] **Offer the §22757.3(a) manifest (visible) disclosure option** to users until/unless SB 1000
      removes it.
- [ ] **Enforce marking in the serving layer**, not in tenant workflows — post-execution hook or
      output-directory egress gate — and prove it with a production canary.
- [ ] **Obtain a production C2PA certificate** chaining to the C2PA Trust List (a test chain is
      `Valid` but `signingCredential.untrusted`), keep RFC 3161 timestamping on, and verify the
      timestamp actually lands (the release demo shows `signer.time: null`).
- [ ] **Key management**: generate, escrow, rotate and record watermark secrets and signing keys;
      losing the watermark secret retroactively breaks detectability of everything you ever marked.
- [ ] **Licensee contracts (§22757.3(c))**: contractual maintenance obligation, a detection mechanism
      for disabled disclosures, and an operational path to **revoke within 96 hours**.
- [ ] **Decide the "GenAI system name and version"** you will assert (the product? ComfyUI? the
      checkpoint?) and apply it consistently — the packs let you say anything.
- [ ] **Classify your fields as system vs personal provenance data** and make sure the detection tool
      emits only the former; keep tenant/user identifiers in the encrypted assertion.
- [ ] **Watch SB 1000** (sign/veto by 30 Sep 2026; urgency clause ⇒ immediate effect on signature) and
      the AB 853 phase-ins (**1 Jan 2027** large online platforms and GenAI hosting platforms; **1 Jan
      2028** capture devices).
- [ ] **Separately assess AB 2013** (training-data documentation, in force 1 Jan 2026) if you train,
      fine-tune or merge models you make publicly available — it is a different statute with a
      different trigger, and these packs do not touch it.
- [ ] **Assess the EU AI Act Art. 50(2)** in parallel if you serve the EU; the packs are aimed at both
      regimes, and the EU Code of Practice's two-layer expectation is what makes this architecture
      worth the effort regardless of the California outcome.
- [ ] **Keep a compliance file**: the robustness envelope you measured, the detection threshold and
      its justification, the feedback you received and what you changed, and dated copies of the
      statutory text you relied on.

---

## 6. Sources

Statute and amendments (all primary sources were **egress-blocked** in this environment; these are the
canonical URLs to verify against on an unblocked network):

* SB 942 (2024) text — https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=202320240SB942
* AB 853 (2025) text / chaptered (Ch. 674, Stats. 2025) — https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=202520260AB853 · https://legiscan.com/CA/text/AB853/id/3273369
* SB 1000 (2026) text and status — https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=202520260SB1000 · https://leginfo.legislature.ca.gov/faces/billStatusClient.xhtml?bill_id=202520260SB1000 · https://calmatters.digitaldemocracy.org/bills/ca_202520260sb1000
* Assembly Privacy Committee analysis of SB 1000 (16 Jun 2026) — https://apcp.assembly.ca.gov/media/1177
* B&P Code §§22757.1 / .2 / .3 — https://law.justia.com/codes/california/code-bpc/division-8/chapter-25/section-22757-1/ · https://california.public.law/codes/business_and_professions_code_section_22757.2 · https://codes.findlaw.com/ca/business-and-professions-code/bpc-sect-22757-3/
* Compiled statute + amendment (Orrick) — https://infobytes.orrick.com/wp-content/uploads/California-AI-Transparency-Act-and-Amendment2.pdf

Secondary analyses relied on for the verification above:

* Morgan Lewis, "New California AI Disclosure Rules Become Operative" (Aug 2026) — https://www.morganlewis.com/pubs/2026/08/new-california-ai-disclosure-rules-become-operative
* Troutman Pepper, "California AI Transparency Act Amendments Signed Into Law" (Oct 2025) — https://www.troutmanprivacy.com/2025/10/california-ai-transparency-act-amendments-signed-into-law/
* AI Compliance Atlas, SB 942 — https://aicomplianceatlas.com/law/california-sb-942
* Kolmogorov Law, "What Businesses Need to Know Now That It Is Operative" — https://www.kolmogorovlaw.com/california-ai-transparency-act-sb-942
* Cowan DeBaets, "All About California's New AI Transparency Act" — https://cdas.com/all-about-californias-new-ai-transparency-act/
* Kelley Drye, "California's 2026 Legislative Session Wraps" — https://www.kelleydrye.com/viewpoints/blogs/ad-law-access/californias-2026-legislative-session-wraps-a-wave-of-privacy-and-ai-bills-reaches-the-governor-with-key-child-safety-and-ai-measures-signed-into-law
* The Build, "SB 1000: Everyone Is a Covered Provider Now" — https://thebuild.com/blog/sb-1000-everyone-is-a-covered-provider-now/
* Vorp Labs, September 2026 US AI regulatory update — https://vorplabs.com/ai-regulatory-updates/united-states/2026-09/colorado-admt-rules-california-ai-bills-ftc-cmg-order
* WilmerHale, "California AG Issues AI Advisories" (Jan 2025) — https://www.wilmerhale.com/en/insights/blogs/wilmerhale-privacy-and-cybersecurity-law/20250130-california-ag-issues-ai-advisories
* Crowell & Moring on AB 2013 — https://www.crowell.com/en/insights/client-alerts/californias-ab-2013-requires-generative-ai-data-disclosure-by-january-1-2026
* Davis+Gilbert on AB 2013 taking effect — https://www.dglaw.com/ai-legal-updates-californias-ai-training-data-transparency-law-takes-effect/

Standards and tooling:

* C2PA Soft Binding Algorithm List — https://github.com/c2pa-org/softbinding-algorithm-list
* C2PA Soft Binding Resolution API (Adobe implementation) — https://developer.adobe.com/cai-soft-binding-api/
* c2pa-rs / c2pa-python — https://github.com/contentauth/c2pa-rs · https://github.com/contentauth/c2pa-python
* Adobe TrustMark — https://github.com/adobe/trustmark

In-repository sources cited above: `docs/ai-content-compliance/00-design-and-compliance-overview.md`,
`01-legal-requirements-eu-california-global.md` §§2.1–2.5, `03-c2pa-content-credentials-tooling.md`
§§2–3, `release/index.html` (regulatory-mapping section), and the two packs' source files as cited
inline.

---

*Prepared 17 September 2026 as an independent engineering review. Not legal advice. No warranty of
any kind; the reviewed packs themselves disclaim any promise of regulatory compliance, and this
review makes none either.*
