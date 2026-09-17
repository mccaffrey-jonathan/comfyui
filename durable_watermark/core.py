# SPDX-License-Identifier: Apache-2.0
"""
Keyed radial + angular-harmonic spread-spectrum image watermark ("RingMark").

Design goals
------------
* **Blind, keyed, multi-bit.**  A private secret string drives every
  pseudo-random choice (chip signs, bit interleaving, noise floor).  Without
  the secret the mark is statistically invisible; with it a payload of up to
  64 bits plus an 8-bit CRC is recovered.
* **Frequency-domain, synchronisation-free for rotation/translation/flip.**
  The mark lives in concentric rings of the luminance DFT magnitude.  Each
  ring carries (a) a keyed +/-1 *radial* chip (its mean log-power is nudged
  up or down) used for presence detection and scale search, and (b) keyed
  *angular harmonic* chips: the ring's log-power is modulated as
  s * cos(h*theta + phi) for even harmonics h with keyed phase phi and
  antipodal sign s (sync or payload bit).  Translating an image only changes
  DFT phase, rotating it by d shifts every harmonic's phase by h*d, and
  flipping it conjugates the harmonics; the radial means need no search at
  all, and the angular chips are read coherently after a cheap 1-D search
  over the rotation angle (and a flip hypothesis).  Coherent read-out means
  natural image anisotropy is zero-mean noise rather than bias.
* **Scale handled by a 1-D search.**  A uniform rescale by s moves ring
  radii to r/s in cycles/pixel; detection evaluates all features on a fine
  radial grid and scans s.
* **Crop/aspect tolerant.**  Cropping does not change the frequency of the
  content in cycles/pixel, so bins stay aligned; only energy is lost.
* **Colour tolerant.**  Only luminance is used; brightness/contrast/gamma
  and hue/saturation changes leave the detrended log-radial profile nearly
  unchanged.
* **Honest statistics.**  Detection z-scores are calibrated against an
  empirical null built from many *wrong* keys on the *same* image, so the
  false-positive estimate accounts for image-specific spectral structure and
  for the scale search.

The scheme is deliberately training-free and pure numpy/scipy so it can be
audited and run anywhere (CPU, no model weights).  It is inspired by
Fourier-Mellin / ring-template watermarking (O Ruanaidh & Pun 1998; Lin et
al. 2001), Tree-Ring's rotation-invariant Fourier rings, and classical
spread-spectrum CDMA watermarks (Cox et al. 1997).  See the pack README for
robustness measurements and limitations (in particular: like every post-hoc
watermark it does not survive diffusion "regeneration" attacks).
"""
from __future__ import annotations

import functools
import hashlib
import hmac
import math
import struct
from dataclasses import dataclass, field, asdict
from typing import Optional

import numpy as np

try:  # scipy is a ComfyUI core dependency, but keep the core importable without it.
    from scipy import ndimage as _ndimage
except Exception:  # pragma: no cover
    _ndimage = None

__all__ = [
    "WatermarkConfig",
    "DetectionResult",
    "KeySchedule",
    "embed",
    "detect",
    "payload_from_string",
    "payload_to_hex",
    "crc8",
    "recommended_strength",
    "image_statistics",
]

SCHEME_ID = "org.comfyui.ringmark.v1"
_DOMAIN = b"comfyui-durable-watermark/ringmark/v1"
_EPS = 1e-12


# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------
@dataclass
class WatermarkConfig:
    """Everything embed() and detect() must agree on.

    ``secret`` is the private value of the source (user / inference provider).
    All other fields are public parameters; they are part of the key schedule
    so a detector with the wrong parameters will simply see noise.
    """

    secret: str = ""
    payload_bits: int = 32          # 0..64 user bits (plus 8 CRC bits)
    strength: float = 1.0           # 0.25 (faint) .. 3.0 (aggressive)
    r_min: float = 0.05             # band lower edge, cycles/pixel
    r_max: float = 0.36             # band upper edge, cycles/pixel
    ring_width: float = 0.004       # radial chip width, cycles/pixel (>= ~2/min image side)
    perceptual_mask: bool = True    # spatial masking of the residual
    noise_floor: bool = True        # keyed additive floor for flat images

    def __post_init__(self):
        if not (0 <= self.payload_bits <= 64):
            raise ValueError("payload_bits must be in [0, 64]")
        if not (0.0 < self.r_min < self.r_max <= 0.5 * math.sqrt(2)):
            raise ValueError("need 0 < r_min < r_max <= 0.707 cycles/pixel")
        if not (0.0005 <= self.ring_width <= 0.05):
            raise ValueError("ring_width must be in [0.0005, 0.05] cycles/pixel")
        if self.strength <= 0:
            raise ValueError("strength must be > 0")

    # --- helpers ---------------------------------------------------------
    @property
    def crc_bits(self) -> int:
        return 8

    @property
    def coded_bits(self) -> int:
        return self.payload_bits + self.crc_bits

    @property
    def n_bins(self) -> int:
        return int(math.floor((self.r_max - self.r_min) / self.ring_width + 1e-9))

    def ring_edges(self) -> np.ndarray:
        """(n_bins+1,) radial edges in cycles/pixel."""
        return self.r_min + self.ring_width * np.arange(self.n_bins + 1)

    def public_params(self) -> dict:
        d = asdict(self)
        d.pop("secret", None)
        d["scheme"] = SCHEME_ID
        return d

    def key_fingerprint(self) -> str:
        """Short, non-reversible identifier of the secret+params (safe to log)."""
        return _kdf(self, b"fingerprint")[:8].hex()


_SCHEDULE_VERSION = 3
_SCRYPT = dict(n=2 ** 14, r=8, p=1)     # ~25 ms, 16 MB: makes guessing the secret from a published
                                        # key fingerprint cost a scrypt per guess
_NULL_PREFIX = "\x00ringmark-null::"   # internal wrong-key baselines (never real secrets): fast hash


def _params_blob(cfg: WatermarkConfig) -> bytes:
    return struct.pack("<iiddd", _SCHEDULE_VERSION, cfg.payload_bits, float(cfg.r_min), float(cfg.r_max),
                       float(cfg.ring_width))


@functools.lru_cache(maxsize=64)
def _master_key(secret: str, params: bytes) -> bytes:
    """Memory-hard master key from the secret and the public parameters (cached per process)."""
    if secret.startswith(_NULL_PREFIX):
        return hashlib.sha256(_DOMAIN + b"|null|" + secret.encode("utf-8") + b"|" + params).digest()
    return hashlib.scrypt(secret.encode("utf-8"), salt=_DOMAIN + b"|" + params, dklen=32,
                          maxmem=64 * 1024 * 1024, **_SCRYPT)


def _kdf(cfg: WatermarkConfig, purpose: bytes) -> bytes:
    """Derive 32 bytes of purpose-specific key material (HMAC of the master key)."""
    return hmac.new(_master_key(cfg.secret, _params_blob(cfg)), purpose, hashlib.sha256).digest()


def _rng(cfg: WatermarkConfig, purpose: bytes) -> np.random.Generator:
    seed = int.from_bytes(_kdf(cfg, purpose)[:16], "little")
    return np.random.Generator(np.random.PCG64(seed))


# ----------------------------------------------------------------------------
# Key schedule
# ----------------------------------------------------------------------------
HARMONICS = (2, 6, 10, 14, 18, 22)   # even (Hermitian symmetry), not multiples of 4 (axis/JPEG structure)
_SECTORS = 128                        # angular sectors for the harmonic analysis
_SYNC_FRACTION = 0.25                 # share of angular chips reserved as payload-independent sync


_GROUP_BITS = 8                       # info bits per soft-decoded block code


@dataclass
class KeySchedule:
    """Keyed chip layout for a config.

    * ``radial`` (n_bins,) in {-1,+1}: sync chip per ring (mean log-power).
    * ``phases`` (n_bins, n_harm): keyed phase of each angular chip.
    * ``signs``  (n_bins, n_harm) in {-1,+1}: keyed sign of sync chips.
    * ``roles``  (n_bins, n_harm): -1 for sync chips, else the payload group index.
    * ``group_chips``: list of flat chip indices per group.
    * ``codebooks``: per group a keyed (2**g_bits, n_chips_in_group) +/-1 code;
      payload bits select a codeword, detection does soft ML decoding.
    """

    n_bins: int
    radial: np.ndarray
    phases: np.ndarray
    signs: np.ndarray
    roles: np.ndarray
    group_bits: list
    group_chips: list
    codebooks: list
    noise_seed: int

    @property
    def n_harm(self) -> int:
        return len(HARMONICS)

    @property
    def n_chips(self) -> int:
        return self.n_bins * self.n_harm

    @classmethod
    def from_config(cls, cfg: WatermarkConfig) -> "KeySchedule":
        n = cfg.n_bins
        nb = cfg.coded_bits
        nh = len(HARMONICS)
        n_chips = n * nh
        if cfg.payload_bits == 0:          # zero-bit mode: every chip carries sync
            n_sync, n_groups = n_chips, 0
        else:
            n_sync = int(round(_SYNC_FRACTION * n_chips))
            n_groups = (nb + _GROUP_BITS - 1) // _GROUP_BITS
        n_payload = n_chips - n_sync
        if n_groups and n_payload // n_groups < 2 * _GROUP_BITS:
            raise ValueError(
                f"band too narrow: {n} rings give {n_payload} payload chips for {nb} coded bits; "
                "widen r_min..r_max, lower ring_width or lower payload_bits"
            )
        rng = _rng(cfg, b"radial")
        radial = rng.choice(np.array([-1.0, 1.0]), size=n)
        rng = _rng(cfg, b"phases")
        phases = rng.uniform(0, 2 * np.pi, size=(n, nh))
        rng = _rng(cfg, b"signs")
        signs = rng.choice(np.array([-1.0, 1.0]), size=(n, nh))
        rng = _rng(cfg, b"roles")
        roles = np.full(n_chips, -1, dtype=np.int64)
        perm = rng.permutation(n_chips)
        payload_idx = perm[n_sync:]
        group_bits, group_chips, codebooks = [], [], []
        if n_groups:
            per = n_payload // n_groups
            crng = _rng(cfg, b"codebook")
            for g in range(n_groups):
                gb = min(_GROUP_BITS, nb - g * _GROUP_BITS)
                idx = np.sort(payload_idx[g * per:(g + 1) * per])
                roles[idx] = g
                group_bits.append(gb)
                group_chips.append(idx)
                codebooks.append(crng.choice(np.array([-1.0, 1.0]), size=(1 << gb, len(idx))))
        noise_seed = int.from_bytes(_kdf(cfg, b"noise")[:8], "little")
        return cls(n, radial, phases, signs, roles.reshape(n, nh), group_bits, group_chips, codebooks, noise_seed)

    # --- read-out helpers on the (n_bins, n_harm) chip statistic ---------
    def sync_weights(self) -> np.ndarray:
        """(n_bins, n_harm): sign on sync chips, 0 elsewhere, normalised."""
        w = np.where(self.roles < 0, self.signs, 0.0)
        return w / math.sqrt(max(int((self.roles < 0).sum()), 1))

    def chip_values(self, bits_pm: np.ndarray) -> np.ndarray:
        """(n_bins, n_harm) in {-1,+1}: sync signs plus payload codewords."""
        v = np.where(self.roles < 0, self.signs, 0.0).reshape(-1)
        bits01 = (bits_pm > 0).astype(np.int64)
        for g, (gb, idx, cb) in enumerate(zip(self.group_bits, self.group_chips, self.codebooks)):
            word = 0
            for b in bits01[g * _GROUP_BITS:g * _GROUP_BITS + gb]:
                word = (word << 1) | int(b)
            v[idx] = cb[word]
        return v.reshape(self.n_bins, self.n_harm)

    def ring_reliability(self, t: np.ndarray) -> np.ndarray:
        """(n_bins,) non-negative per-ring weights estimated from the known sync
        chips: rings whose sync chips read back strongly (e.g. survived JPEG)
        get more say in payload decoding.  Smoothed over neighbouring rings."""
        agree = (np.where(self.roles < 0, self.signs, 0.0) * t.reshape(self.n_bins, self.n_harm)).sum(axis=1)
        cnt = (self.roles < 0).sum(axis=1).astype(np.float64)
        k = np.array([1, 2, 3, 4, 3, 2, 1], dtype=np.float64)
        num = np.convolve(agree, k, mode="same")
        den = np.convolve(cnt, k, mode="same")
        rel = num / np.maximum(den, 1e-9)
        rel = np.maximum(rel, 0.0)
        top = np.percentile(rel, 90) if np.any(rel > 0) else 1.0
        return np.clip(rel / max(top, 1e-9), 0.0, 1.0)

    def decode(self, t: np.ndarray):
        """Soft ML decode of flat chip statistics t (n_chips,).

        Returns (bits01 array of coded bits, per-group confidence z-scores).
        """
        tw = t
        bits, conf = [], []
        for gb, idx, cb in zip(self.group_bits, self.group_chips, self.codebooks):
            corr = cb @ tw[idx]
            order = np.argsort(corr)
            best = int(order[-1])
            rest = corr[order[:-1]]
            conf.append(float((corr[best] - rest.mean()) / (rest.std() + 1e-12)))
            bits.extend([(best >> (gb - 1 - i)) & 1 for i in range(gb)])
        return np.array(bits, dtype=np.int64), conf


# ----------------------------------------------------------------------------
# Payload helpers
# ----------------------------------------------------------------------------
def crc8(data: bytes, poly: int = 0x07, init: int = 0x00) -> int:
    crc = init
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ poly) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def payload_from_string(s: str, bits: int) -> int:
    """Interpret a user string as a payload integer.

    * empty            -> 0
    * decimal digits   -> that integer
    * 0x... hex        -> that integer
    * anything else    -> first ``bits`` bits of SHA-256(s) (stable ID for a name)
    Values are reduced modulo 2**bits.
    """
    s = (s or "").strip()
    if bits == 0:
        return 0
    mask = (1 << bits) - 1
    if s == "":
        return 0
    if s.isdigit():
        return int(s) & mask
    if s.lower().startswith("0x"):
        try:
            return int(s, 16) & mask
        except ValueError:
            pass
    digest = hashlib.sha256(s.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") >> (64 - bits) if bits < 64 else int.from_bytes(digest[:8], "big")


def payload_to_hex(value: int, bits: int) -> str:
    if bits == 0:
        return ""
    width = (bits + 3) // 4
    return f"0x{value:0{width}x}"


def _payload_bytes(value: int, bits: int) -> bytes:
    nbytes = max(1, (bits + 7) // 8)
    return int(value).to_bytes(nbytes, "big")


def _coded_bits(cfg: WatermarkConfig, payload: int) -> np.ndarray:
    """Payload bits (MSB first) followed by CRC-8 -> array in {-1,+1}."""
    bits = cfg.payload_bits
    if bits:
        payload &= (1 << bits) - 1
    else:
        payload = 0
    pb = [(payload >> (bits - 1 - i)) & 1 for i in range(bits)]
    crc = crc8(_payload_bytes(payload, bits) + bytes([bits]))
    cb = [(crc >> (7 - i)) & 1 for i in range(8)]
    arr = np.array(pb + cb, dtype=np.float64)
    return arr * 2.0 - 1.0


def _decode_bits(cfg: WatermarkConfig, bits01: np.ndarray) -> tuple[int, bool]:
    bits = cfg.payload_bits
    if bits == 0:
        return 0, True
    payload = 0
    for i in range(bits):
        payload = (payload << 1) | int(bits01[i])
    crc = 0
    for i in range(8):
        crc = (crc << 1) | int(bits01[bits + i])
    ok = crc == crc8(_payload_bytes(payload, bits) + bytes([bits]))
    return payload, ok


# ----------------------------------------------------------------------------
# Image helpers
# ----------------------------------------------------------------------------
def to_luma(img: np.ndarray) -> np.ndarray:
    """float32/64 HxWxC or HxW in [0,1] -> HxW luminance (BT.601)."""
    img = np.asarray(img, dtype=np.float64)
    if img.ndim == 2:
        return img
    if img.shape[-1] == 1:
        return img[..., 0]
    return 0.299 * img[..., 0] + 0.587 * img[..., 1] + 0.114 * img[..., 2]


def _freq_grid(h: int, w: int):
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    return fy, fx


def _bin_index(r: np.ndarray, cfg: WatermarkConfig) -> np.ndarray:
    """Continuous radial chip coordinate (chip 0 starts at r_min)."""
    return (r - cfg.r_min) / cfg.ring_width


def _perceptual_mask(y: np.ndarray) -> np.ndarray:
    """Smooth texture-adaptive gain in ~[0.45, 1.8] with mean ~1.

    The wide blur (sigma ~ 24 px) keeps the mask from smearing the ring structure in the
    frequency domain, but on its own it projects a textured object's gain ~70 px into the
    flat area next to it (the "sky ripple" found in the image-quality review).  The gain is
    therefore capped by a narrow-blur (sigma 6 px) view of the same texture map: flat pixels
    more than a few pixels from texture stay at the floor, thin edges keep their gain.
    """
    if _ndimage is None:  # pragma: no cover
        return np.ones_like(y)
    mu = _ndimage.uniform_filter(y, size=7, mode="reflect")
    var = _ndimage.uniform_filter(y * y, size=7, mode="reflect") - mu * mu
    std = np.sqrt(np.maximum(var, 0.0))
    raw = np.clip(_MASK_FLOOR + std / 0.06, _MASK_FLOOR, 2.5)
    gain = _ndimage.gaussian_filter(raw, sigma=24, mode="reflect")
    local = _ndimage.gaussian_filter(raw, sigma=6, mode="reflect")
    gain = np.minimum(gain, local + _MASK_CAP_MARGIN)
    gain = gain / max(gain.mean(), 1e-6)
    return np.clip(gain, _MASK_FLOOR, 1.8)


_MASK_FLOOR = 0.45
_MASK_CAP_MARGIN = 0.10


def image_statistics(image: np.ndarray) -> dict:
    """Cheap content statistics used by :func:`recommended_strength` (one FFT, one local-std pass)."""
    y = to_luma(np.asarray(image, dtype=np.float64))
    h, w = y.shape
    F = np.abs(np.fft.fft2(y - y.mean())) ** 2
    fy, fx = _freq_grid(h, w)
    r = np.sqrt(fx * fx + fy * fy)
    tot = float(F[r > 0].sum()) + _EPS
    band = float(F[(r >= 0.05) & (r <= 0.36)].sum()) / tot
    flat = 0.0
    if _ndimage is not None:
        mu = _ndimage.uniform_filter(y, size=7, mode="reflect")
        var = _ndimage.uniform_filter(y * y, size=7, mode="reflect") - mu * mu
        flat = float((np.sqrt(np.maximum(var, 0.0)) < 2.0 / 255.0).mean())
    return {"min_side": int(min(h, w)), "band_energy_fraction": band, "flat_fraction": flat}


def recommended_strength(image: np.ndarray, base: float = 1.0) -> tuple[float, dict]:
    """Content-adaptive strength (policy from the image-quality evaluation on ComfyUI renders):
    texture-rich images take x1.5 (measured invisible even at 4x zoom), images below 768 /
    640 px take x1.5 / x2 to offset the resolution penalty, everything else keeps ``base``."""
    st = image_statistics(image)
    factor = 1.0
    if st["band_energy_fraction"] > 0.15:
        factor = 1.5
    if st["min_side"] < 640:
        factor = max(factor, 2.0)
    elif st["min_side"] < 768:
        factor = max(factor, 1.5)
    st["factor"] = factor
    return base * factor, st


# ----------------------------------------------------------------------------
# Embedding
# ----------------------------------------------------------------------------
_ALPHA_RADIAL = 0.10     # log-magnitude modulation of the radial sync chip (x strength)
_ALPHA_ANGULAR = 0.07    # log-magnitude amplitude per angular harmonic chip (x strength)
_FLOOR_STD = 1.0 / 255.0  # spatial std of the keyed additive floor (x strength)
_TILT = 0.0              # amplitude ~ (0.2 / r)**_TILT; 0 = flat (tilting cost ~2 dB PSNR for no decoding gain)
_TILT_RANGE = (0.8, 1.6)


def _ring_tilt(cfg: WatermarkConfig) -> np.ndarray:
    """(n_bins,) relative amplitude per ring."""
    e = cfg.ring_edges()
    rc = 0.5 * (e[:-1] + e[1:])
    return np.clip((0.2 / rc) ** _TILT, *_TILT_RANGE)


def _polar_grid(h: int, w: int, aspect: float = 1.0):
    fy, fx = _freq_grid(h, w)
    fy = fy * aspect
    r = np.sqrt(fx * fx + fy * fy)
    theta = np.arctan2(fy, fx)
    return r, theta


def embed(image: np.ndarray, cfg: WatermarkConfig, payload: int = 0) -> np.ndarray:
    """Embed ``payload`` into ``image`` (HxWx3 float in [0,1]); returns a new array.

    Only the luminance is modified; the same delta is added to R, G and B so
    chroma is preserved.
    """
    img = np.asarray(image, dtype=np.float64)
    if img.ndim != 3 or img.shape[-1] not in (1, 3, 4):
        raise ValueError("image must be HxWxC with C in {1,3,4}")
    alpha_ch = img[..., 3:] if img.shape[-1] == 4 else None
    rgb = img[..., :3] if img.shape[-1] >= 3 else np.repeat(img[..., :1], 3, axis=-1)
    h, w = rgb.shape[:2]
    if min(h, w) < 64:
        raise ValueError("image too small to watermark (min side 64 px)")

    ks = KeySchedule.from_config(cfg)
    bits = _coded_bits(cfg, payload)
    chips = ks.chip_values(bits)                 # (n_bins, n_harm)

    y = to_luma(rgb)
    r, theta = _polar_grid(h, w)
    kf = _bin_index(r, cfg)
    k = np.floor(kf).astype(np.int64)
    inband = (k >= 0) & (k < ks.n_bins)
    kk = k[inband]
    th = theta[inband]

    tilt = _ring_tilt(cfg)[kk]
    alpha_r = _ALPHA_RADIAL * cfg.strength * tilt
    alpha_a = _ALPHA_ANGULAR * cfg.strength * tilt
    s_vals = alpha_r * ks.radial[kk]
    for hi, harm in enumerate(HARMONICS):
        s_vals = s_vals + alpha_a * chips[kk, hi] * np.cos(harm * th + ks.phases[kk, hi])
    s_map = np.zeros((h, w))
    s_map[inband] = s_vals
    gain = np.exp(s_map)

    F = np.fft.fft2(y)
    Fm = F * gain
    y_marked = np.real(np.fft.ifft2(Fm))
    delta = y_marked - y
    if cfg.perceptual_mask:
        # Mask only the multiplicative part (it scales with local host energy and is what
        # becomes visible when texture gain leaks into flat areas).
        delta = delta * _perceptual_mask(y)

    # Keyed additive floor (band-limited, same radial/angular shaping) so flat regions still
    # carry the mark after 8-bit quantisation.  Deliberately not masked: it is a uniform
    # ~1/255-std grain that is what flat regions decode from.
    if cfg.noise_floor:
        nrng = np.random.Generator(np.random.PCG64(ks.noise_seed))
        noise = nrng.standard_normal((h, w))
        Nf = np.fft.fft2(noise) * inband * gain
        n_sp = np.real(np.fft.ifft2(Nf))
        n_std = float(n_sp.std()) + _EPS
        delta = delta + n_sp * (_FLOOR_STD * cfg.strength / n_std)

    out = np.clip(rgb + delta[..., None], 0.0, 1.0)
    if alpha_ch is not None:
        out = np.concatenate([out, alpha_ch], axis=-1)
    return out.astype(np.float32 if image.dtype == np.float32 else np.float64)


# ----------------------------------------------------------------------------
# Detection
# ----------------------------------------------------------------------------
@dataclass
class DetectionResult:
    detected: bool
    z_score: float                    # combined presence z (radial sync + coherent angular sync)
    p_value: float                    # Gumbel tail probability of the score under the wrong-key null
    z_radial: float
    z_angular: float
    threshold: float
    scale: float                      # estimated size of the analysed image relative to the marked original
    rotation_deg: float               # estimated rotation (mod 180) of the analysed image
    flipped: bool                     # mirror hypothesis chosen
    payload: int
    payload_hex: str
    crc_ok: bool
    bit_confidence: float             # min over payload blocks of the ML decoding margin (z-like)
    bit_confidences: list = field(default_factory=list)
    expected_match: Optional[bool] = None
    aspect: float = 1.0
    n_bins_used: int = 0
    key_fingerprint: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["scheme"] = SCHEME_ID
        return d


_OVERSAMPLE = 4          # fine radial grid = ring_width / _OVERSAMPLE
_ROT_STEP_DEG = 2.0      # rotation hypothesis step (harmonic 22 tolerates ~+-4 deg)


def _tukey(n: int, alpha: float) -> np.ndarray:
    x = np.linspace(0, 1, n)
    wdw = np.ones(n)
    edge = alpha / 2
    lo = x < edge
    hi = x > 1 - edge
    wdw[lo] = 0.5 * (1 + np.cos(np.pi * (2 * x[lo] / alpha - 1)))
    wdw[hi] = 0.5 * (1 + np.cos(np.pi * (2 * x[hi] / alpha - 2 / alpha + 1)))
    return wdw


def _fine_polar_energy(y: np.ndarray, cfg: WatermarkConfig, aspect: float = 1.0):
    """Accumulate DFT energy on a fine (radius x sector) polar grid.

    Returns (S, C, r_step): S[m, j] = sum of |F|^2, C[m, j] = coefficient count
    for fine radial cell m and angular sector j (sector 0 starts at theta=-pi).
    """
    h, w = y.shape
    y = y - y.mean()
    ty = _tukey(h, 0.1)[:, None]
    tx = _tukey(w, 0.1)[None, :]
    F = np.fft.fft2(y * ty * tx)
    E = np.abs(F) ** 2
    fy, fx = _freq_grid(h, w)
    fy = fy * aspect
    # Exclude DC/axes and the 1/8-cycle lattice lines where JPEG blocking leaks.
    ax_y = np.abs(fy - np.round(fy * 8) / 8) < 1.5 / h
    ax_x = np.abs(fx - np.round(fx * 8) / 8) < 1.5 / w
    valid = ~(ax_y | ax_x)
    r = np.sqrt(fx * fx + fy * fy)
    theta = np.arctan2(fy, fx)
    valid &= r > 0.01
    r_step = cfg.ring_width / _OVERSAMPLE
    m = np.floor(r / r_step).astype(np.int64)
    nm = int(math.ceil(0.75 / r_step)) + 1
    valid &= m < nm
    j = np.floor((theta + np.pi) / (2 * np.pi) * _SECTORS).astype(np.int64) % _SECTORS
    idx = (m * _SECTORS + j)[valid]
    S = np.bincount(idx, weights=E[valid], minlength=nm * _SECTORS).reshape(nm, _SECTORS)
    C = np.bincount(idx, minlength=nm * _SECTORS).reshape(nm, _SECTORS).astype(np.float64)
    return S, C, r_step


def _interval_sums(cs: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """cs: (n+1, ...) cumulative sums along axis 0; lo/hi: fractional positions.
    Returns sums over [lo, hi) with linear interpolation at the ends."""
    n = cs.shape[0] - 1
    lo = np.clip(lo, 0, n)
    hi = np.clip(hi, 0, n)

    def _at(x):
        i0 = np.floor(x).astype(np.int64)
        i0 = np.minimum(i0, n - 1)
        wgt = (x - i0)[..., None] if cs.ndim > 1 else (x - i0)
        return cs[i0] * (1 - wgt) + cs[i0 + 1] * wgt

    return _at(hi) - _at(lo)


def _features(S: np.ndarray, C: np.ndarray, r_step: float, cfg: WatermarkConfig, scales: np.ndarray):
    """Per-scale features.

    Returns (radial (n_bins, n_s), spec (n_bins, n_harm, n_s) complex, used (n_s,)).
    radial: detrended, robust-normalised mean log-power per ring.
    spec: complex angular Fourier coefficient of the ring's log sector energy at
          HARMONICS, referenced to theta=0 and whitened per ring.
    """
    edges = cfg.ring_edges()
    nb = cfg.n_bins
    nm = S.shape[0]
    s_tot = S.sum(axis=1)
    c_tot = C.sum(axis=1)
    prof = np.full(nm, np.nan)
    ok = c_tot >= 6
    prof[ok] = np.log(s_tot[ok] / c_tot[ok] + 1e-9)
    rr = (np.arange(nm) + 0.5) * r_step
    x = np.log(rr)
    xm, xs = x[ok].mean(), max(x[ok].std(), 1e-6)
    coeff = np.polyfit((x[ok] - xm) / xs, prof[ok], 3)
    res = prof - np.polyval(coeff, (x - xm) / xs)
    mad = np.nanmedian(np.abs(res - np.nanmedian(res)))
    res = res / max(1.4826 * mad, 1e-6)
    resf = np.where(np.isfinite(res), res, 0.0)
    okf = ok.astype(np.float64)

    cs_res = np.concatenate([[0.0], np.cumsum(resf)])
    cs_ok = np.concatenate([[0.0], np.cumsum(okf)])
    cs_S = np.concatenate([np.zeros((1, _SECTORS)), np.cumsum(S, axis=0)], axis=0)
    cs_C = np.concatenate([np.zeros((1, _SECTORS)), np.cumsum(C, axis=0)], axis=0)

    lo = edges[:-1][:, None] / scales[None, :] / r_step      # (nb, n_s)
    hi = edges[1:][:, None] / scales[None, :] / r_step

    se = _interval_sums(cs_res, lo, hi)
    sn = _interval_sums(cs_ok, lo, hi)
    ring_ok = sn >= 0.5 * _OVERSAMPLE
    radial = np.where(ring_ok, se / np.maximum(sn, 1e-9), 0.0)
    used = ring_ok.sum(axis=0)

    Ssum = _interval_sums(cs_S, lo, hi)                       # (nb, n_s, sectors)
    Csum = _interval_sums(cs_C, lo, hi)
    with np.errstate(divide="ignore", invalid="ignore"):
        Ebar = Ssum / Csum
    sec_ok = Csum >= 1.0
    L = np.where(sec_ok, np.log(np.where(sec_ok, Ebar, 1.0) + 1e-12), 0.0)
    cnt = sec_ok.sum(axis=-1, keepdims=True)
    ring_mean = L.sum(axis=-1, keepdims=True) / np.maximum(cnt, 1)
    L = np.where(sec_ok, L - ring_mean, 0.0)
    # Per-ring whitening: rings with strong natural anisotropy are down-weighted.
    ring_std = np.sqrt((L * L).sum(axis=-1, keepdims=True) / np.maximum(cnt, 1))
    floor = np.median(ring_std[ring_std > 0]) if np.any(ring_std > 0) else 1.0
    L = L / np.maximum(ring_std, 0.5 * floor)
    spec = np.fft.rfft(L, axis=-1) / _SECTORS                 # (nb, n_s, sectors//2+1)
    # Sector 0 is centred at theta = -pi + pi/SECTORS; refer phases to theta = 0.
    hs = np.array(HARMONICS)
    ref = np.exp(-1j * hs * (-np.pi + np.pi / _SECTORS))
    spec = spec[..., list(HARMONICS)] * ref                   # (nb, n_s, n_harm)
    spec = np.where(ring_ok[..., None], spec, 0.0)
    return radial, np.transpose(spec, (0, 2, 1)), used


def _rotation_scores(G: np.ndarray, Gf: np.ndarray, rot: np.ndarray) -> np.ndarray:
    """G / Gf: (..., n_harm, n_s) complex keyed harmonic sums for the unflipped /
    mirrored spectrum; returns (..., n_s, n_rot, 2) real coherent scores."""
    hs = np.array(HARMONICS, dtype=np.float64)
    ph = np.exp(-1j * hs[:, None] * rot[None, :])             # (n_harm, n_rot)
    a = np.einsum("...hs,hr->...sr", G, ph).real
    b = np.einsum("...hs,hr->...sr", Gf, ph).real
    return np.stack([a, b], axis=-1)


def detect(
    image: np.ndarray,
    cfg: WatermarkConfig,
    expected_payload: Optional[int] = None,
    scale_range: tuple[float, float] = (0.4, 2.5),
    aspect_search: bool = False,
    z_threshold: float = 5.0,
    n_null: int = 96,
) -> DetectionResult:
    """Blind detection.  ``image`` is HxWxC or HxW float in [0,1] (any size)."""
    img = np.asarray(image, dtype=np.float64)
    y = to_luma(img)
    notes = []
    pre_scale = 1.0
    while max(y.shape) > 3072:           # bound FFT cost; 2x box downscale is a known scale factor
        y = _box_down2(y)
        pre_scale *= 0.5
        notes.append("downscaled x0.5 for analysis")
    if min(y.shape) < 48:
        return DetectionResult(False, 0.0, 1.0, 0.0, 0.0, z_threshold, 1.0, 0.0, False, 0, "", False, 0.0,
                               notes="image too small")

    ks = KeySchedule.from_config(cfg)
    nbits = cfg.coded_bits
    nb, nh = ks.n_bins, ks.n_harm
    v_rad = ks.radial / math.sqrt(nb)
    w_sync = ks.sync_weights()                                # (nb, nh)
    e_phase = np.exp(-1j * ks.phases)                         # (nb, nh)

    s_lo, s_hi = scale_range
    log_step = max(cfg.ring_width / (4.0 * cfg.r_max), 1e-3)
    n_s = int(math.ceil(math.log(s_hi / s_lo) / log_step)) + 1
    scales = np.exp(np.linspace(math.log(s_lo), math.log(s_hi), n_s))
    rot = np.deg2rad(np.arange(0.0, 180.0, _ROT_STEP_DEG))

    aspects = [1.0]
    if aspect_search:
        aspects = [float(a) for a in np.exp(np.linspace(math.log(0.8), math.log(1.25), 9))]

    fp = cfg.key_fingerprint()
    null_ks = [KeySchedule.from_config(WatermarkConfig(
        secret=f"{_NULL_PREFIX}{fp}::{i}", payload_bits=cfg.payload_bits, r_min=cfg.r_min, r_max=cfg.r_max,
        ring_width=cfg.ring_width, strength=cfg.strength)) for i in range(n_null)]
    Vr0 = np.stack([k.radial for k in null_ks]) / math.sqrt(nb)                       # (n_null, nb)
    W0 = np.stack([k.sync_weights() * np.exp(-1j * k.phases) for k in null_ks])       # (n_null, nb, nh)

    best = None
    null_best = np.full(n_null, -np.inf)
    for aspect in aspects:
        S, C, r_step = _fine_polar_energy(y, cfg, aspect=aspect)
        radial, spec, used = _features(S, C, r_step, cfg, scales)   # spec (nb, nh, n_s)
        # --- radial sync ---
        r_true = v_rad @ radial                                       # (n_s,)
        r_null = Vr0 @ radial                                         # (n_null, n_s)
        sr = float(r_null.std()) + 1e-9
        # --- coherent angular sync over (scale, rotation, flip) ---
        specf = np.conj(spec)                                         # mirrored image hypothesis
        G = np.einsum("kh,khs->hs", w_sync * e_phase, spec)           # (nh, n_s)
        Gf = np.einsum("kh,khs->hs", w_sync * e_phase, specf)
        a_true = _rotation_scores(G, Gf, rot)                         # (n_s, n_rot, 2)
        G0 = np.einsum("nkh,khs->nhs", W0, spec)                      # (n_null, nh, n_s)
        G0f = np.einsum("nkh,khs->nhs", W0, specf)
        a_null = _rotation_scores(G0, G0f, rot)                       # (n_null, n_s, n_rot, 2)
        sa = float(a_null.std()) + 1e-9
        score = r_true[:, None, None] / sr + a_true / sa
        score_null = r_null[:, :, None, None] / sr + a_null / sa
        j = int(np.argmax(score))
        js, jr, jf = np.unravel_index(j, score.shape)
        if best is None or score[js, jr, jf] > best["score"]:
            # chip statistics at the chosen hypothesis
            sp = spec[:, :, js]
            if jf == 1:
                sp = np.conj(sp)
            hs = np.array(HARMONICS, dtype=np.float64)
            t = (sp * e_phase * np.exp(-1j * hs * rot[jr])[None, :]).real   # (nb, nh)
            bits01, conf = ks.decode(t.reshape(-1))
            best = dict(score=float(score[js, jr, jf]), scale=float(scales[js]), rot=float(np.rad2deg(rot[jr])),
                        flip=bool(jf == 1), aspect=aspect, zr=float(r_true[js] / sr),
                        za=float(a_true[js, jr, jf] / sa), bits01=bits01, conf=conf, used=int(used[js]))
        null_best = np.maximum(null_best, score_null.reshape(n_null, -1).max(axis=1))

    mu0, sd0 = float(null_best.mean()), float(null_best.std() + 1e-9)
    z = (best["score"] - mu0) / sd0
    p = _gumbel_p(null_best, best["score"])
    payload, crc_ok = _decode_bits(cfg, best["bits01"])
    conf = np.array(best["conf"], dtype=np.float64)
    detected = bool(z >= z_threshold)
    scale = best["scale"] / pre_scale
    match = None
    if expected_payload is not None and cfg.payload_bits > 0:
        match = bool(detected and crc_ok and (payload == (expected_payload & ((1 << cfg.payload_bits) - 1))))
    return DetectionResult(
        detected=detected, z_score=float(z), p_value=float(p), z_radial=best["zr"], z_angular=best["za"],
        threshold=z_threshold, scale=float(scale), rotation_deg=best["rot"], flipped=best["flip"],
        payload=int(payload), payload_hex=payload_to_hex(payload, cfg.payload_bits), crc_ok=bool(crc_ok),
        bit_confidence=float(conf.min()) if len(conf) else 0.0, bit_confidences=[float(c) for c in conf],
        expected_match=match, aspect=float(best["aspect"]), n_bins_used=best["used"], key_fingerprint=fp,
        notes="; ".join(notes),
    )


def _gumbel_p(null_max: np.ndarray, score: float) -> float:
    """Tail probability of ``score`` under the wrong-key null.

    The null samples are maxima over the scale/rotation/flip search, so their
    distribution is extreme-value shaped, not Gaussian; a Gumbel fit (method of
    moments) extrapolates its tail far more honestly than a normal z-score.
    """
    m, s = float(np.mean(null_max)), float(np.std(null_max)) + 1e-9
    beta = s * math.sqrt(6.0) / math.pi
    mu = m - 0.5772156649 * beta
    x = (score - mu) / beta
    if x > 700:
        return 0.0
    return float(-math.expm1(-math.exp(-x)))


def _box_down2(y: np.ndarray) -> np.ndarray:
    h, w = y.shape
    y = y[: h - h % 2, : w - w % 2]
    return 0.25 * (y[0::2, 0::2] + y[1::2, 0::2] + y[0::2, 1::2] + y[1::2, 1::2])
