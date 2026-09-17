# SPDX-License-Identifier: Apache-2.0
"""Fallback secret redaction (same logic as durable_watermark.keys) for installs without the watermark pack."""
from __future__ import annotations

import copy

SENSITIVE_FIELDS = {
    "DurableWatermarkKey": ("secret",),
    "C2PASaveImage": ("private_passphrase",),
    "C2PADecryptPrivateAssertion": ("private_passphrase",),
    "C2PASigner": ("private_key",),
}
_REDACTED = "<redacted>"


def _is_literal_secret(v) -> bool:
    return isinstance(v, str) and bool(v.strip()) and not v.strip().startswith(("env:", "file:"))


def sensitive_literals(prompt) -> set:
    found = set()
    if not isinstance(prompt, dict):
        return found
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        for f in SENSITIVE_FIELDS.get(node.get("class_type"), ()):
            v = node.get("inputs", {}).get(f)
            if _is_literal_secret(v) and not (f == "private_key" and "-----BEGIN" not in v):
                found.add(v)
    return found


def redact_prompt(prompt):
    if not isinstance(prompt, dict):
        return prompt
    out = copy.deepcopy(prompt)
    for node in out.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {})
        for f in SENSITIVE_FIELDS.get(node.get("class_type"), ()):
            v = inputs.get(f)
            if _is_literal_secret(v) and not (f == "private_key" and "-----BEGIN" not in v):
                inputs[f] = _REDACTED
    return out


def redact_values(obj, secrets):
    secrets = {s for s in (secrets or ()) if isinstance(s, str) and s}
    if not secrets:
        return copy.deepcopy(obj)

    def walk(o):
        if isinstance(o, str):
            return _REDACTED if o in secrets else o
        if isinstance(o, list):
            return [walk(x) for x in o]
        if isinstance(o, dict):
            return {k: walk(v) for k, v in o.items()}
        return o

    return walk(obj)


def redact_extra_pnginfo(extra, prompt):
    return redact_values(extra, sensitive_literals(prompt))
