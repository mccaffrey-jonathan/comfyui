"""Read and summarise Content Credentials from image files/bytes."""
from __future__ import annotations

import io
import json
import os
from typing import Any, Optional

from .manifest import IPTC_DST_PREFIX, MIME


def _mime_for(path_or_name: str) -> str:
    ext = os.path.splitext(path_or_name)[1].lower().lstrip(".")
    return MIME.get(ext, "")


def read_manifest(path: Optional[str] = None, data: Optional[bytes] = None, mime: str = "",
                  trust_anchors_pem: Optional[str] = None) -> dict:
    """Return a dict with keys: has_manifest, validation_state, validation_results, active_manifest, store."""
    import c2pa

    if data is None:
        with open(path, "rb") as fh:
            data = fh.read()
    mime = mime or (_mime_for(path) if path else "") or ""
    context = None
    if trust_anchors_pem:
        try:
            settings = c2pa.Settings.from_dict({"verify": {"verify_cert_anchors": True},
                                                "trust": {"user_anchors": trust_anchors_pem}})
            context = c2pa.Context(settings)
        except Exception:  # pragma: no cover - settings API differences
            context = None
    stream = io.BytesIO(data)
    try:
        reader = c2pa.Reader.try_create(mime or None, stream, context=context) if mime else c2pa.Reader.try_create(stream, context=context)
    except Exception as exc:
        return {"has_manifest": False, "error": str(exc)}
    if reader is None:
        return {"has_manifest": False}
    try:
        store = json.loads(reader.json())
        state = reader.get_validation_state()
        results = reader.get_validation_results()
    finally:
        try:
            reader.close()
        except Exception:  # pragma: no cover
            pass
    active = store.get("manifests", {}).get(store.get("active_manifest"), {})
    return {"has_manifest": True, "validation_state": state, "validation_results": results,
            "active_manifest": active, "store": store}


def _iter_actions(active: dict):
    for a in active.get("assertions", []):
        if str(a.get("label", "")).startswith("c2pa.actions"):
            for act in a.get("data", {}).get("actions", []):
                yield act


def summarize(info: dict) -> dict:
    """Extract the facts a compliance check cares about."""
    if not info.get("has_manifest"):
        return {"has_manifest": False, "ai_generated": None, "error": info.get("error")}
    active = info.get("active_manifest", {})
    dsts = [act.get("digitalSourceType", "") for act in _iter_actions(active) if act.get("digitalSourceType")]
    ai_types = {"trainedAlgorithmicMedia", "compositeWithTrainedAlgorithmicMedia", "compositeSynthetic"}
    ai_generated = any(d.replace(IPTC_DST_PREFIX, "") in ai_types for d in dsts)
    agents = []
    for act in _iter_actions(active):
        sa = act.get("softwareAgent")
        if isinstance(sa, dict):
            agents.append(sa.get("name", "") + (f" {sa['version']}" if sa.get("version") else ""))
        elif isinstance(sa, str):
            agents.append(sa)
    generation = next((a.get("data") for a in active.get("assertions", []) if a.get("label") == "org.comfyui.generation"), None)
    soft = [a.get("data") for a in active.get("assertions", []) if a.get("label") == "c2pa.soft-binding"]
    private = next((a.get("data") for a in active.get("assertions", []) if a.get("label") == "org.comfyui.private"), None)
    failures = []
    vr = info.get("validation_results") or {}
    for entry in (vr.get("activeManifest", {}) or {}).get("failure", []) or []:
        failures.append(entry.get("code"))
    sig = active.get("signature_info", {}) or {}
    return {
        "has_manifest": True,
        "validation_state": info.get("validation_state"),
        "failures": failures,
        "trusted": info.get("validation_state") == "Trusted",
        "ai_generated": ai_generated,
        "digital_source_types": [d.replace(IPTC_DST_PREFIX, "") for d in dsts],
        "software_agents": agents,
        "claim_generator": active.get("claim_generator") or active.get("claim_generator_info"),
        "signer": {"issuer": sig.get("issuer"), "common_name": sig.get("common_name"), "time": sig.get("time"),
                   "alg": sig.get("alg")},
        "title": active.get("title"),
        "label": active.get("label"),
        "generation": generation,
        "soft_bindings": soft,
        "has_private_assertion": private is not None,
        "ingredients": [i.get("title") for i in active.get("ingredients", [])],
    }
