"""
Secret / payload resolution for the durable watermark.

Where the private value comes from (first hit wins):

1. The node widget, if it is non-empty.  Special forms:
     ``env:NAME``   -> the environment variable NAME
     ``file:PATH``  -> the (stripped) contents of PATH
   A literal string is accepted but discouraged, because ComfyUI stores every
   widget value of the workflow inside saved PNG metadata.
2. ``COMFYUI_WATERMARK_SECRET`` environment variable.
3. ``COMFYUI_WATERMARK_SECRET_FILE`` environment variable (path).
4. ``<pack>/config/watermark_secret.txt`` (git-ignored).
5. ``secret`` in ``<pack>/config/watermark.json`` (git-ignored).

Inference providers can set ``COMFYUI_WATERMARK_ENFORCE=1`` (or
``"enforce": true`` in ``watermark.json``): the server-side secret, payload and
strength then override whatever a workflow specifies, so tenants cannot
disable or re-key the provider's mark.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger("durable_watermark")

PACK_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(PACK_DIR, "config")
CONFIG_JSON = os.path.join(CONFIG_DIR, "watermark.json")
SECRET_FILE = os.path.join(CONFIG_DIR, "watermark_secret.txt")

ENV_SECRET = "COMFYUI_WATERMARK_SECRET"
ENV_SECRET_FILE = "COMFYUI_WATERMARK_SECRET_FILE"
ENV_PAYLOAD = "COMFYUI_WATERMARK_PAYLOAD"
ENV_STRENGTH = "COMFYUI_WATERMARK_STRENGTH"
ENV_ENFORCE = "COMFYUI_WATERMARK_ENFORCE"


class SecretError(RuntimeError):
    pass


def _read_file(path: str) -> str:
    with open(os.path.expanduser(path), "r", encoding="utf-8") as fh:
        return fh.read().strip()


def load_server_config() -> dict:
    """Server-side defaults from config/watermark.json (may be absent)."""
    if not os.path.exists(CONFIG_JSON):
        return {}
    try:
        with open(CONFIG_JSON, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception as exc:  # pragma: no cover
        log.warning("durable_watermark: cannot read %s: %s", CONFIG_JSON, exc)
        return {}


def enforce_server_settings() -> bool:
    if os.environ.get(ENV_ENFORCE, "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    return bool(load_server_config().get("enforce", False))


def expand_reference(value: Optional[str]) -> str:
    """Expand ``env:`` / ``file:`` references; return literal otherwise."""
    v = (value or "").strip()
    if v.startswith("env:"):
        name = v[4:].strip()
        got = os.environ.get(name)
        if got is None or got == "":
            raise SecretError(f"environment variable {name!r} is not set")
        return got.strip()
    if v.startswith("file:"):
        path = v[5:].strip()
        try:
            return _read_file(path)
        except OSError as exc:
            raise SecretError(f"cannot read secret file {path!r}: {exc}") from exc
    return v


def resolve_secret(widget_value: Optional[str] = None, *, allow_missing: bool = False) -> str:
    """Return the private watermark secret (see module docstring for precedence)."""
    enforced = enforce_server_settings()
    if not enforced:
        v = expand_reference(widget_value)
        if v:
            if not (widget_value or "").strip().startswith(("env:", "file:")):
                log.warning(
                    "durable_watermark: a literal secret was typed into a node widget. "
                    "ComfyUI saves widget values into output PNG metadata; prefer 'env:NAME' or 'file:PATH'."
                )
            return v
    env = os.environ.get(ENV_SECRET, "").strip()
    if env:
        return env
    env_file = os.environ.get(ENV_SECRET_FILE, "").strip()
    if env_file:
        return _read_file(env_file)
    if os.path.exists(SECRET_FILE):
        v = _read_file(SECRET_FILE)
        if v:
            return v
    cfg = load_server_config()
    v = str(cfg.get("secret", "") or "").strip()
    if v:
        return expand_reference(v)
    if allow_missing:
        return ""
    raise SecretError(
        "No watermark secret configured. Set the node's 'secret' to 'env:NAME' or 'file:PATH', "
        f"or export {ENV_SECRET}, or create {SECRET_FILE}."
    )


def resolve_payload(widget_value: Optional[str] = None) -> str:
    """Return the payload *string* (parsed later by payload_from_string)."""
    if enforce_server_settings():
        cfg = load_server_config()
        env = os.environ.get(ENV_PAYLOAD)
        if env is not None and env.strip():
            return env.strip()
        if cfg.get("payload") is not None:
            return str(cfg["payload"])
    v = expand_reference(widget_value)
    if v:
        return v
    env = os.environ.get(ENV_PAYLOAD, "").strip()
    if env:
        return env
    cfg = load_server_config()
    if cfg.get("payload") is not None:
        return str(cfg["payload"])
    return ""


def resolve_strength(widget_value: float) -> float:
    if enforce_server_settings():
        env = os.environ.get(ENV_STRENGTH, "").strip()
        if env:
            return float(env)
        cfg = load_server_config()
        if cfg.get("strength") is not None:
            return float(cfg["strength"])
    return float(widget_value)


@dataclass
class ResolvedKey:
    secret: str
    payload_text: str
    strength: float
    enforced: bool


def resolve(widget_secret: str, widget_payload: str, widget_strength: float) -> ResolvedKey:
    return ResolvedKey(
        secret=resolve_secret(widget_secret),
        payload_text=resolve_payload(widget_payload),
        strength=resolve_strength(widget_strength),
        enforced=enforce_server_settings(),
    )


def redact_prompt(prompt, node_class_names=("DurableWatermarkKey",), field_names=("secret",)):
    """Return a deep copy of a ComfyUI prompt dict with watermark secrets blanked.

    Used by save nodes so a literal secret typed into a widget never lands in
    output metadata.  ``env:``/``file:`` references are kept (they are not secret).
    """
    import copy

    if not isinstance(prompt, dict):
        return prompt
    out = copy.deepcopy(prompt)
    for node in out.values():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") in node_class_names:
            inputs = node.get("inputs", {})
            for f in field_names:
                v = inputs.get(f)
                if isinstance(v, str) and v and not v.startswith(("env:", "file:")):
                    inputs[f] = "<redacted>"
    return out
