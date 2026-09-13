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
import json
import os
from typing import Any

_INFO = b"comfyui-content-credentials/private-assertion/v1"
_SALT = b"comfyui-c2pa-private-v1"


def _derive_key(passphrase: str) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    return HKDF(algorithm=hashes.SHA256(), length=32, salt=_SALT, info=_INFO).derive(passphrase.encode("utf-8"))


def key_id(passphrase: str) -> str:
    return hashlib.sha256(_INFO + b"|" + passphrase.encode("utf-8")).hexdigest()[:16]


def encrypt_json(obj: Any, passphrase: str, aad: bytes = b"") -> dict:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = _derive_key(passphrase)
    nonce = os.urandom(12)
    pt = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ct = AESGCM(key).encrypt(nonce, pt, aad or None)
    return {
        "alg": "A256GCM",
        "kdf": "HKDF-SHA256",
        "key_id": key_id(passphrase),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ct).decode("ascii"),
        "aad": base64.b64encode(aad).decode("ascii") if aad else "",
    }


def decrypt_json(box: dict, passphrase: str) -> Any:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if box.get("alg") != "A256GCM":
        raise ValueError("unsupported private-assertion algorithm")
    key = _derive_key(passphrase)
    nonce = base64.b64decode(box["nonce"])
    ct = base64.b64decode(box["ciphertext"])
    aad = base64.b64decode(box["aad"]) if box.get("aad") else None
    pt = AESGCM(key).decrypt(nonce, ct, aad)
    return json.loads(pt.decode("utf-8"))
