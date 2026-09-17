# SPDX-License-Identifier: Apache-2.0
"""Encrypted private assertion payloads (AES-256-GCM, key from a passphrase via HKDF-SHA256).

C2PA manifests are *signed*, not encrypted: everything in them is public.  A
provider may still need to keep generation details (full prompt, tenant / user
identifiers, internal job IDs) confidential while proving provenance.  This
module lets the save node place such details in an ``org.comfyui.private``
assertion as ciphertext that only the holder of the provider key can open.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from typing import Any

_INFO = b"comfyui-content-credentials/private-assertion/v1"
_LEGACY_SALT = b"comfyui-c2pa-private-v1"
_SCRYPT = dict(n=2 ** 15, r=8, p=1)   # ~40 ms and 32 MB per derivation: slows offline passphrase guessing


def _derive_key(passphrase: str, salt: bytes, kdf: str = "scrypt") -> bytes:
    if kdf == "scrypt":
        return hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, dklen=32, maxmem=64 * 1024 * 1024, **_SCRYPT)
    if kdf == "HKDF-SHA256":  # boxes written by version 0.1.0
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF

        return HKDF(algorithm=hashes.SHA256(), length=32, salt=_LEGACY_SALT, info=_INFO).derive(passphrase.encode("utf-8"))
    raise ValueError(f"unsupported private-assertion kdf {kdf!r}")


def key_id(passphrase: str, salt: bytes) -> str:
    """Identifier of the key that opens a box.  Derived from the scrypt output, so confirming a
    passphrase guess costs a full scrypt per guess (the value is public in the manifest)."""
    key = _derive_key(passphrase, salt)
    return hmac.new(key, b"key-id", hashlib.sha256).hexdigest()[:16]


def encrypt_json(obj: Any, passphrase: str, aad: bytes = b"") -> dict:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt = os.urandom(16)
    key = _derive_key(passphrase, salt)
    nonce = os.urandom(12)
    pt = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ct = AESGCM(key).encrypt(nonce, pt, aad or None)
    return {
        "alg": "A256GCM",
        "kdf": "scrypt",
        "kdf_params": {"n": _SCRYPT["n"], "r": _SCRYPT["r"], "p": _SCRYPT["p"]},
        "salt": base64.b64encode(salt).decode("ascii"),
        "key_id": hmac.new(key, b"key-id", hashlib.sha256).hexdigest()[:16],
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ct).decode("ascii"),
        "aad": base64.b64encode(aad).decode("ascii") if aad else "",
    }


def decrypt_json(box: dict, passphrase: str) -> Any:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if box.get("alg") != "A256GCM":
        raise ValueError("unsupported private-assertion algorithm")
    salt = base64.b64decode(box["salt"]) if box.get("salt") else b""
    key = _derive_key(passphrase, salt, box.get("kdf", "scrypt"))
    nonce = base64.b64decode(box["nonce"])
    ct = base64.b64decode(box["ciphertext"])
    aad = base64.b64decode(box["aad"]) if box.get("aad") else None
    pt = AESGCM(key).decrypt(nonce, ct, aad)
    return json.loads(pt.decode("utf-8"))
