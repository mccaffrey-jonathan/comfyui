"""C2PA Content Credentials helpers for ComfyUI (signing, manifests, verification, private assertions)."""
from .manifest import (  # noqa: F401
    DIGITAL_SOURCE_TYPES,
    IPTC_DST_PREFIX,
    ManifestOptions,
    build_manifest,
    sign_image_bytes,
)
from .signing import SignerConfig, SignerError, load_signer_config, make_signer  # noqa: F401
from .certs import generate_test_chain  # noqa: F401
from .crypto_box import decrypt_json, encrypt_json  # noqa: F401
from .verify import read_manifest, summarize  # noqa: F401

__version__ = "0.1.0"
